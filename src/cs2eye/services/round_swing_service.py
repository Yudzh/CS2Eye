from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.analytics.round_swing.core import (
    FEATURE_SCHEMA_VERSION, ROUND_SWING_MODEL_VERSION, ROUND_WIN_MODEL_VERSION,
    RoundState, RoundWinProbabilityModel, TrainingExample, attribution_v1,
    calibration_metrics, robust_swing_score, temporal_group_split,
)
from cs2eye.models.demo import (
    DemoBombEvent, DemoDamageEvent, DemoKill, DemoMapResult, DemoPlayerStat,
    DemoRound, DemoRoundSwingEvent, DemoUtilityEvent, RoundWinModelArtifact,
)
from cs2eye.models.demo_file import DemoFile


def _tick_interval(round_row: DemoRound) -> float | None:
    if (round_row.started_at_tick is None or round_row.ended_at_tick is None
            or round_row.duration_seconds is None or round_row.ended_at_tick <= round_row.started_at_tick):
        return None
    return float(round_row.duration_seconds) / (round_row.ended_at_tick - round_row.started_at_tick)


def _time_remaining(round_row: DemoRound, tick: int) -> float | None:
    interval = _tick_interval(round_row)
    if interval is None or round_row.ended_at_tick is None: return None
    return max(0.0, (round_row.ended_at_tick - tick) * interval)


def build_round_transitions(round_row: DemoRound, map_name: str, kills: list[DemoKill],
                            bomb_events: list[DemoBombEvent]) -> list[tuple[DemoKill, RoundState, RoundState, dict]]:
    alive = {"T": 5, "CT": 5}; planted = False; plant_tick = None; output = []
    timeline = sorted([*(('bomb', row.tick, row) for row in bomb_events), *(('kill', row.tick, row) for row in kills)], key=lambda item: (item[1], item[0] != "bomb"))
    for kind, tick, row in timeline:
        if kind == "bomb":
            if row.event_kind == "planted": planted, plant_tick = True, tick
            elif row.event_kind in {"defused", "exploded"}: planted = False
            continue
        kill: DemoKill = row
        if kill.is_teamkill or kill.is_suicide or kill.attacker_side not in {"T", "CT"} or kill.victim_side not in {"T", "CT"}: continue
        remaining = _time_remaining(round_row, tick)
        equipment_t = round_row.team_a_equipment_value if round_row.team_a_side == "T" else round_row.team_b_equipment_value
        equipment_ct = round_row.team_a_equipment_value if round_row.team_a_side == "CT" else round_row.team_b_equipment_value
        before = RoundState(map_name, alive["T"], alive["CT"], "planted" if planted else "not_planted", equipment_t, equipment_ct, remaining)
        alive[kill.victim_side] = max(0, alive[kill.victim_side] - 1)
        after = RoundState(map_name, alive["T"], alive["CT"], before.bomb_state, equipment_t, equipment_ct, remaining)
        contexts = {"opening": bool(kill.is_opening_kill), "trade": bool(kill.is_trade_kill),
                    "clutch": before.alive_t == 1 if kill.attacker_side == "T" else before.alive_ct == 1,
                    "postplant": planted, "retake": planted and kill.attacker_side == "CT"}
        output.append((kill, before, after, contexts))
    return output


async def active_model(session: AsyncSession) -> RoundWinModelArtifact | None:
    return (await session.execute(select(RoundWinModelArtifact).where(
        RoundWinModelArtifact.model_version == ROUND_WIN_MODEL_VERSION,
        RoundWinModelArtifact.is_active.is_(True)))).scalar_one_or_none()


async def recalculate_demo_swing(session: AsyncSession, demo_file_id: int) -> str:
    result = (await session.execute(select(DemoMapResult).where(DemoMapResult.demo_file_id == demo_file_id))).scalar_one_or_none()
    if result is None: return "invalid"
    artifact = await active_model(session)
    await session.execute(delete(DemoRoundSwingEvent).where(DemoRoundSwingEvent.demo_file_id == demo_file_id))
    if artifact is None:
        result.round_swing_status = "model_not_trained"; return result.round_swing_status
    model = RoundWinProbabilityModel(artifact.artifact)
    rounds = list((await session.execute(select(DemoRound).where(DemoRound.demo_file_id == demo_file_id, DemoRound.is_complete.is_(True)))).scalars())
    kills = list((await session.execute(select(DemoKill).where(DemoKill.demo_file_id == demo_file_id).order_by(DemoKill.tick))).scalars())
    bombs = list((await session.execute(select(DemoBombEvent).where(DemoBombEvent.demo_file_id == demo_file_id))).scalars())
    damages = list((await session.execute(select(DemoDamageEvent).where(DemoDamageEvent.demo_file_id == demo_file_id))).scalars())
    transitions = [item for rnd in rounds for item in build_round_transitions(rnd, result.map_name or "unknown", [k for k in kills if k.round_id == rnd.id], [b for b in bombs if b.round_id == rnd.id])]
    probabilities = model.predict_batch([state for _, before, after, _ in transitions for state in (before, after)])
    for index, (kill, before, after, contexts) in enumerate(transitions):
        p_before, p_after = probabilities[index*2:index*2+2]
        event_t = p_after - p_before; oriented = event_t if kill.attacker_side == "T" else -event_t
        relevant = [d for d in damages if d.round_id == kill.round_id and d.victim_identity_key == kill.victim_identity_key and d.tick <= kill.tick]
        damage = defaultdict(int)
        for row in relevant: damage[row.attacker_identity_key] += row.health_damage
        flash = (await session.execute(select(DemoUtilityEvent).where(
            DemoUtilityEvent.round_id == kill.round_id, DemoUtilityEvent.event_kind == "flash_assist",
            DemoUtilityEvent.tick == kill.tick, DemoUtilityEvent.target_identity_key == kill.victim_identity_key))).scalar_one_or_none()
        credits = attribution_v1(oriented, kill.attacker_identity_key or "world", kill.victim_identity_key,
                                 damage_by_player=dict(damage), flash_assister_key=flash.player_identity_key if flash else None)
        serialized = []
        for credit in credits:
            side = kill.victim_side if credit.role == "victim_non_additive" else kill.attacker_side
            serialized.append({**credit.__dict__, "side": side})
        confidence = .9 if bombs or not round_row_bomb_uncertain(rounds, kill.round_id) else .75
        session.add(DemoRoundSwingEvent(demo_file_id=demo_file_id, round_id=kill.round_id, kill_id=kill.id,
            model_version=ROUND_SWING_MODEL_VERSION, state_before=before.payload(), state_after=after.payload(),
            probability_t_before=Decimal(str(p_before)), probability_t_after=Decimal(str(p_after)), event_swing=Decimal(str(oriented)),
            credited_player_id=kill.attacker_player_id, credited_identity_key=kill.attacker_identity_key,
            attribution={"policy":"v1","credits":serialized,"team_total_roles":["killer","damage_assist","flash_assist"]}, contexts=contexts, confidence=Decimal(str(confidence))))
    result.round_swing_status = "complete" if transitions else "partial"
    return result.round_swing_status


def round_row_bomb_uncertain(rounds: list[DemoRound], round_id: int) -> bool:
    row = next((item for item in rounds if item.id == round_id), None)
    return bool(row and row.bomb_planted)


async def build_training_examples(session: AsyncSession) -> list[TrainingExample]:
    rows = (await session.execute(select(DemoRound, DemoMapResult, DemoFile).join(DemoMapResult, DemoMapResult.id == DemoRound.demo_map_result_id).join(DemoFile, DemoFile.id == DemoRound.demo_file_id).where(DemoRound.is_complete.is_(True)).order_by(DemoFile.match_date, DemoFile.id, DemoRound.round_number))).all()
    examples = []
    for rnd, result, demo in rows:
        kills = list((await session.execute(select(DemoKill).where(DemoKill.round_id == rnd.id))).scalars())
        bombs = list((await session.execute(select(DemoBombEvent).where(DemoBombEvent.round_id == rnd.id))).scalars())
        for _, before, after, _ in build_round_transitions(rnd, result.map_name or "unknown", kills, bombs):
            for state in (before, after): examples.append(TrainingExample(str(demo.match_id or demo.id), float(demo.match_date.toordinal() if demo.match_date else demo.id), state, int(rnd.winner_side == "T")))
    return examples


async def train_round_win_model(session: AsyncSession) -> dict:
    examples = await build_training_examples(session)
    train, validation = temporal_group_split(examples)
    model, train_metrics = RoundWinProbabilityModel.train(train)
    validation_metrics = calibration_metrics(model.predict_batch([x.state for x in validation]), [x.t_won for x in validation])
    old = await active_model(session)
    if old: await session.delete(old)
    normalization = {"method":"median_mad_clipped_z","median":0.0,"mad":1.0}
    row = RoundWinModelArtifact(model_version=ROUND_WIN_MODEL_VERSION, feature_schema_version=FEATURE_SCHEMA_VERSION,
        trained_at=datetime.now(UTC), training_matches=len({x.match_key for x in train}), training_rounds=len(train), validation_rounds=len(validation),
        artifact=model.artifact, metrics={"train":train_metrics,"validation":validation_metrics}, normalization=normalization, is_active=True)
    session.add(row); await session.flush()
    return {"model_version":ROUND_WIN_MODEL_VERSION,"training_states":len(train),"validation_states":len(validation),"metrics":row.metrics}


def aggregate_player_swing(events: list[DemoRoundSwingEvent], player_key: str, rounds: int, distribution: list[float] | None = None) -> dict | None:
    credits = []
    for event in events:
        for credit in event.attribution.get("credits", []):
            if credit.get("identity_key") == player_key: credits.append((float(credit["credited_swing"]), event, credit.get("side")))
    if not credits or rounds <= 0: return None
    total = sum(value for value, _, _ in credits); raw = total * 100 / rounds; reliability = rounds / (rounds + 100)
    adjusted = raw * reliability
    def context(name):
        selected = [value for value, event, _ in credits if event.contexts.get(name)]
        return sum(selected)*100/rounds if selected else None
    def side(name):
        selected = [value for value, _, event_side in credits if event_side == name]
        return sum(selected)*100/rounds if selected else None
    return {"score":robust_swing_score(adjusted, distribution or [adjusted]),"raw_per_round":round(raw,4),"adjusted_per_round":round(adjusted,4),
            "confidence":round(reliability,4),"rounds":rounds,"ct":side("CT"),"t":side("T"),
            "opening":context("opening"),"trade":context("trade"),"clutch":context("clutch"),"postplant":context("postplant"),"retake":context("retake")}


async def player_round_swing(session: AsyncSession, player_id: int) -> dict:
    stats = list((await session.execute(select(DemoPlayerStat).where(DemoPlayerStat.player_id == player_id))).scalars())
    if not stats: return {"status":"not_calculated"}
    keys = {row.identity_key for row in stats}; demo_ids = {row.demo_file_id for row in stats}
    events = list((await session.execute(select(DemoRoundSwingEvent).where(DemoRoundSwingEvent.demo_file_id.in_(demo_ids)))).scalars())
    if not events:
        statuses = list((await session.execute(select(DemoMapResult.round_swing_status).where(DemoMapResult.demo_file_id.in_(demo_ids)))).scalars())
        return {"status":"model_not_trained" if "model_not_trained" in statuses else "not_calculated"}
    rounds = sum(row.rounds_played for row in stats)
    values = [aggregate_player_swing(events, key, rounds) for key in keys]
    value = next((item for item in values if item), None)
    return {"status":"complete", **(value or {})}


async def roster_swing_profile(session: AsyncSession, player_ids: list[int]) -> dict:
    players = [{"player_id": player_id, **await player_round_swing(session, player_id)} for player_id in player_ids]
    available = [item for item in players if item.get("status") == "complete" and item.get("adjusted_per_round") is not None]
    if not available: return {"status":"not_calculated","players":players,"sample":{"players":0,"rounds":0},"confidence":0.0}
    ordered = sorted(available, key=lambda item: item["adjusted_per_round"], reverse=True)
    def avg(key, rows=available):
        values=[item[key] for item in rows if item.get(key) is not None]
        return round(sum(values)/len(values),4) if values else None
    return {"status":"complete" if len(available)==len(player_ids) else "partial","avg_swing":avg("adjusted_per_round"),
            "top2_swing":avg("adjusted_per_round",ordered[:2]),"bottom2_swing":avg("adjusted_per_round",ordered[-2:]),
            "ct_swing":avg("ct"),"t_swing":avg("t"),"opening_swing":avg("opening"),"clutch_swing":avg("clutch"),
            "sample":{"players":len(available),"rounds":sum(item.get("rounds",0) for item in available)},
            "confidence":round(sum(item.get("confidence",0) for item in available)/len(available),4),"players":players}
