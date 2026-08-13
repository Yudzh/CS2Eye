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
    robust_swing_score_from_reference,
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
    flashes = list((await session.execute(select(DemoUtilityEvent).where(
        DemoUtilityEvent.demo_file_id == demo_file_id,
        DemoUtilityEvent.event_kind == "flash_assist",
    ))).scalars())
    flash_by_event = {(row.round_id, row.tick, row.target_identity_key): row for row in flashes}
    transitions = [item for rnd in rounds for item in build_round_transitions(rnd, result.map_name or "unknown", [k for k in kills if k.round_id == rnd.id], [b for b in bombs if b.round_id == rnd.id])]
    probabilities = model.predict_batch([state for _, before, after, _ in transitions for state in (before, after)])
    for index, (kill, before, after, contexts) in enumerate(transitions):
        p_before, p_after = probabilities[index*2:index*2+2]
        event_t = p_after - p_before; oriented = event_t if kill.attacker_side == "T" else -event_t
        relevant = [d for d in damages if d.round_id == kill.round_id and d.victim_identity_key == kill.victim_identity_key and d.tick <= kill.tick]
        damage = defaultdict(int)
        for row in relevant: damage[row.attacker_identity_key] += row.health_damage
        flash = flash_by_event.get((kill.round_id, kill.tick, kill.victim_identity_key))
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


async def recalculate_all_swing(session: AsyncSession) -> dict:
    demo_ids = list((await session.execute(
        select(DemoMapResult.demo_file_id).where(
            DemoMapResult.round_data_status == "complete",
            DemoMapResult.combat_data_status.in_(("complete", "needs_review")),
        ).order_by(DemoMapResult.demo_file_id)
    )).scalars())
    counts: dict[str, int] = defaultdict(int)
    for demo_id in demo_ids:
        counts[await recalculate_demo_swing(session, demo_id)] += 1
        await session.flush()
    return {"demos":len(demo_ids),"statuses":dict(counts),"model_version":ROUND_SWING_MODEL_VERSION}


def round_row_bomb_uncertain(rounds: list[DemoRound], round_id: int) -> bool:
    row = next((item for item in rounds if item.id == round_id), None)
    return bool(row and row.bomb_planted)


async def build_training_examples(session: AsyncSession) -> list[TrainingExample]:
    round_rows = (await session.execute(
        select(DemoRound, DemoMapResult, DemoFile)
        .join(DemoMapResult, DemoMapResult.id == DemoRound.demo_map_result_id)
        .join(DemoFile, DemoFile.id == DemoRound.demo_file_id)
        .where(DemoRound.is_complete.is_(True))
        .order_by(DemoFile.match_date, DemoFile.id, DemoRound.round_number)
    )).all()
    round_ids = [round_row.id for round_row, _, _ in round_rows]
    kills = list((await session.execute(
        select(DemoKill).where(DemoKill.round_id.in_(round_ids))
        .order_by(DemoKill.round_id, DemoKill.tick, DemoKill.id)
    )).scalars()) if round_ids else []
    bombs = list((await session.execute(
        select(DemoBombEvent).where(DemoBombEvent.round_id.in_(round_ids))
        .order_by(DemoBombEvent.round_id, DemoBombEvent.tick, DemoBombEvent.id)
    )).scalars()) if round_ids else []
    return assemble_training_examples(round_rows, kills, bombs)


def assemble_training_examples(
    round_rows: list[tuple[DemoRound, DemoMapResult, DemoFile]],
    kills: list[DemoKill], bombs: list[DemoBombEvent],
) -> list[TrainingExample]:
    """Pure in-memory assembly shared by bulk loading and semantic fixtures."""
    kills_by_round: dict[int, list[DemoKill]] = defaultdict(list)
    bombs_by_round: dict[int, list[DemoBombEvent]] = defaultdict(list)
    for kill in kills: kills_by_round[kill.round_id].append(kill)
    for bomb in bombs: bombs_by_round[bomb.round_id].append(bomb)
    examples: list[TrainingExample] = []
    for round_row, result, demo in round_rows:
        transitions = build_round_transitions(
            round_row, result.map_name or "unknown",
            kills_by_round[round_row.id], bombs_by_round[round_row.id],
        )
        target = int(round_row.winner_side == "T")
        # Prefix namespaces: match id 42 and standalone demo id 42 are not the
        # same group. The old unprefixed fallback could accidentally merge them.
        match_key = f"match:{demo.match_id}" if demo.match_id is not None else f"demo:{demo.id}"
        chronology = float(demo.match_date.toordinal() if demo.match_date else demo.id)
        for _, before, after, _ in transitions:
            examples.append(TrainingExample(match_key, chronology, before, target))
            examples.append(TrainingExample(match_key, chronology, after, target))
    return examples


async def train_round_win_model(session: AsyncSession) -> dict:
    examples = await build_training_examples(session)
    train, validation = temporal_group_split(examples)
    model, train_metrics = RoundWinProbabilityModel.train(train)
    validation_metrics = calibration_metrics(model.predict_batch([x.state for x in validation]), [x.t_won for x in validation])
    old = await active_model(session)
    normalization = {"method":"median_mad_clipped_z","median":0.0,"mad":1.0}
    metadata = {
        "train": train_metrics, "validation": validation_metrics,
        "split": {
            "strategy": "temporal_match_group_80_20",
            "training_groups": len({x.match_key for x in train}),
            "validation_groups": len({x.match_key for x in validation}),
            "training_states": len(train), "validation_states": len(validation),
            "training_positive": sum(x.t_won for x in train),
            "training_negative": len(train)-sum(x.t_won for x in train),
            "validation_positive": sum(x.t_won for x in validation),
            "validation_negative": len(validation)-sum(x.t_won for x in validation),
            "training_chronology": [min(x.chronology for x in train), max(x.chronology for x in train)],
            "validation_chronology": [min(x.chronology for x in validation), max(x.chronology for x in validation)],
        },
    }
    values = dict(feature_schema_version=FEATURE_SCHEMA_VERSION, trained_at=datetime.now(UTC),
        training_matches=metadata["split"]["training_groups"], training_rounds=len(train), validation_rounds=len(validation),
        artifact=model.artifact, metrics=metadata, normalization=normalization, is_active=True)
    if old:
        for key, value in values.items(): setattr(old, key, value)
        row = old
    else:
        row = RoundWinModelArtifact(model_version=ROUND_WIN_MODEL_VERSION, **values)
        session.add(row)
    await session.flush()
    return {"model_version":ROUND_WIN_MODEL_VERSION, **metadata["split"], "metrics":row.metrics}


def aggregate_player_swing(events: list[DemoRoundSwingEvent], player_key: str | set[str], rounds: int,
                           normalization: dict | None = None) -> dict | None:
    player_keys={player_key} if isinstance(player_key,str) else player_key
    credits = []
    for event in events:
        for credit in event.attribution.get("credits", []):
            if credit.get("identity_key") in player_keys: credits.append((float(credit["credited_swing"]), event, credit.get("side")))
    if not credits or rounds <= 0: return None
    total = sum(value for value, _, _ in credits); raw = total * 100 / rounds; reliability = rounds / (rounds + 100)
    adjusted = raw * reliability
    def context(name):
        selected = [value for value, event, _ in credits if event.contexts.get(name)]
        return sum(selected)*100/rounds if selected else None
    def side(name):
        selected = [value for value, _, event_side in credits if event_side == name]
        return sum(selected)*100/rounds if selected else None
    return {"score":robust_swing_score_from_reference(adjusted,normalization),"raw_per_round":round(raw,4),"adjusted_per_round":round(adjusted,4),
            "total_swing":round(total*100,4),"positive_swing":round(sum(max(0,value) for value,_,_ in credits)*100,4),
            "negative_swing":round(sum(min(0,value) for value,_,_ in credits)*100,4),
            "confidence":round(reliability,4),"rounds":rounds,"ct":side("CT"),"t":side("T"),
            "opening":context("opening"),"trade":context("trade"),"clutch":context("clutch"),"postplant":context("postplant"),"retake":context("retake")}


def distribution_summary(values: list[float]) -> dict:
    import numpy as np
    data=np.asarray(values,dtype=float)
    if not len(data): return {"count":0}
    percentiles=np.percentile(data,[5,25,50,75,95])
    return {"count":len(values),"min":float(data.min()),"p5":float(percentiles[0]),
        "p25":float(percentiles[1]),"median":float(percentiles[2]),"p75":float(percentiles[3]),
        "p95":float(percentiles[4]),"max":float(data.max()),"mean":float(data.mean()),"std":float(data.std())}


async def refresh_swing_normalization(session: AsyncSession) -> dict:
    artifact=await active_model(session)
    if artifact is None: raise ValueError("Round Win model is not trained.")
    stats=list((await session.execute(select(DemoPlayerStat).where(
        DemoPlayerStat.player_id.is_not(None), DemoPlayerStat.rounds_played > 0))).scalars())
    events=list((await session.execute(select(DemoRoundSwingEvent).where(
        DemoRoundSwingEvent.model_version == ROUND_SWING_MODEL_VERSION))).scalars())
    by_player: dict[int, dict] = defaultdict(lambda:{"rounds":0,"keys":set(),"demo_ids":set()})
    for row in stats:
        value=by_player[row.player_id];value["rounds"]+=row.rounds_played
        value["keys"].add(row.identity_key);value["demo_ids"].add(row.demo_file_id)
    player_values=[]
    for value in by_player.values():
        selected=[event for event in events if event.demo_file_id in value["demo_ids"]]
        credits=[float(credit["credited_swing"]) for event in selected for credit in event.attribution.get("credits",[])
                 if credit.get("identity_key") in value["keys"]]
        if credits:
            raw=sum(credits)*100/value["rounds"];reliability=value["rounds"]/(value["rounds"]+100)
            player_values.append(raw*reliability)
    summary=distribution_summary(player_values);event_summary=distribution_summary([float(event.event_swing)*100 for event in events])
    median_value=summary["median"]
    deviations=[abs(value-median_value) for value in player_values]
    mad=float(__import__("statistics").median(deviations)) if deviations else 0.0
    artifact.normalization={"method":"median_mad_clipped_z","median":median_value,
        "mad":mad,"robust_scale":max(mad*1.4826,1e-6),"clip_z":3.0,
        "score_formula":"50 + clip((adjusted_per_round-median)/(1.4826*MAD),-3,3)*50/3",
        "player_distribution":summary,"event_swing_pp_distribution":event_summary}
    await session.flush();return artifact.normalization


async def round_swing_audit(session: AsyncSession) -> dict:
    import numpy as np
    artifact=await active_model(session)
    if artifact is None: raise ValueError("Round Win model is not trained.")
    stats=list((await session.execute(select(DemoPlayerStat).where(
        DemoPlayerStat.player_id.is_not(None),DemoPlayerStat.rounds_played>0))).scalars())
    events=list((await session.execute(select(DemoRoundSwingEvent).where(
        DemoRoundSwingEvent.model_version==ROUND_SWING_MODEL_VERSION))).scalars())
    grouped: dict[int,list[DemoPlayerStat]]=defaultdict(list)
    for row in stats:grouped[row.player_id].append(row)
    records=[]
    for player_id,rows in grouped.items():
        rounds=sum(row.rounds_played for row in rows);ids={row.demo_file_id for row in rows};keys={row.identity_key for row in rows}
        selected=[event for event in events if event.demo_file_id in ids]
        swing=aggregate_player_swing(selected,keys,rounds,artifact.normalization)
        if not swing:continue
        combat=[row.combat_data for row in rows if row.combat_data]
        opening_kills=sum(int(x.get("opening_kills",0)) for x in combat);opening_attempts=sum(int(x.get("opening_attempts",0)) for x in combat)
        clutch_wins=sum(int(x.get("clutch_wins",0)) for x in combat);clutch_opps=sum(int(x.get("clutch_opportunities",0)) for x in combat)
        trades=sum(int(x.get("trade_kills",0)) for x in combat);trade_opps=sum(int(x.get("trade_opportunities",0)) for x in combat)
        records.append({"player_id":player_id,"swing":swing["adjusted_per_round"],"kills_per_round":sum(row.kills for row in rows)/rounds,
            "adr":sum(float(row.adr)*row.rounds_played for row in rows)/rounds,
            "internal_rating":sum(float(row.internal_rating)*row.rounds_played for row in rows)/rounds,
            "opening_success":opening_kills/opening_attempts if opening_attempts else None,
            "clutch_rate":clutch_wins/clutch_opps if clutch_opps else None,
            "trade_rate":trades/trade_opps if trade_opps else None})
    def rankdata(values):
        order=np.argsort(values);ranks=np.empty(len(values),dtype=float);ranks[order]=np.arange(len(values),dtype=float)
        return ranks
    correlations={}
    for key in ("kills_per_round","adr","internal_rating","opening_success","clutch_rate","trade_rate"):
        pairs=[(row["swing"],row[key]) for row in records if row[key] is not None]
        x=np.asarray([p[0] for p in pairs]);y=np.asarray([p[1] for p in pairs])
        correlations[key]={"sample":len(pairs),"pearson":float(np.corrcoef(x,y)[0,1]),
            "spearman":float(np.corrcoef(rankdata(x),rankdata(y))[0,1])}
    def killer_side(event):
        return next((credit.get("side") for credit in event.attribution.get("credits",[]) if credit.get("role")!="victim_non_additive"),None)
    def p_before(event):return float(event.probability_t_before) if killer_side(event)=="T" else 1-float(event.probability_t_before)
    candidates={
        "opening_5v5":lambda e:e.contexts.get("opening") and e.state_before.get("alive_t")==5 and e.state_before.get("alive_ct")==5,
        "late_cleanup":lambda e:p_before(e)>=.9 and float(e.event_swing)<=.08,
        "clutch_1v2_to_1v1":lambda e:e.contexts.get("clutch") and ((killer_side(e)=="T" and e.state_before.get("alive_t")==1 and e.state_before.get("alive_ct")==2) or (killer_side(e)=="CT" and e.state_before.get("alive_ct")==1 and e.state_before.get("alive_t")==2)),
        "postplant":lambda e:e.contexts.get("postplant"),"retake":lambda e:e.contexts.get("retake"),
    }
    examples={}
    for name,predicate in candidates.items():
        event=next((item for item in events if predicate(item)),None)
        examples[name]=None if event is None else {"demo_file_id":event.demo_file_id,"kill_id":event.kill_id,
            "state_before":event.state_before,"p_team_before":p_before(event),"state_after":event.state_after,
            "p_team_after":p_before(event)+float(event.event_swing),"swing_pp":float(event.event_swing)*100,"contexts":event.contexts}
    probabilities=[float(value) for event in events for value in (event.probability_t_before,event.probability_t_after)]
    pathological={"probabilities":len(probabilities),"near_zero":sum(p<1e-6 for p in probabilities),
        "near_one":sum(p>1-1e-6 for p in probabilities),"negative_enemy_kill_swing":sum(float(e.event_swing)<0 for e in events),
        "ordinary_over_30pp":sum(float(e.event_swing)>.30 for e in events)}
    audit={"correlations":correlations,"sanity_examples":examples,"pathological":pathological}
    artifact.metrics={**artifact.metrics,"audit":audit};await session.flush();return audit


async def player_round_swing(session: AsyncSession, player_id: int) -> dict:
    stats = (await session.execute(
        select(DemoPlayerStat, DemoMapResult.map_name, DemoFile.match_date)
        .join(DemoMapResult, DemoMapResult.demo_file_id == DemoPlayerStat.demo_file_id)
        .join(DemoFile, DemoFile.id == DemoPlayerStat.demo_file_id)
        .where(DemoPlayerStat.player_id == player_id)
        .order_by(DemoFile.match_date.desc(), DemoFile.id.desc())
    )).all()
    if not stats: return {"status":"not_calculated","overall":None,"maps":{},"rank_scopes":{},"recent":{}}
    stat_rows=[row[0] for row in stats];keys = {row.identity_key for row in stat_rows};demo_ids = {row.demo_file_id for row in stat_rows}
    events = list((await session.execute(select(DemoRoundSwingEvent).where(DemoRoundSwingEvent.demo_file_id.in_(demo_ids)))).scalars())
    if not events:
        statuses = list((await session.execute(select(DemoMapResult.round_swing_status).where(DemoMapResult.demo_file_id.in_(demo_ids)))).scalars())
        status="model_not_trained" if "model_not_trained" in statuses else "not_calculated"
        return {"status":status,"overall":None,"maps":{},"rank_scopes":{},"recent":{}}
    artifact=await active_model(session);normalization=artifact.normalization if artifact else None
    def scope(selected_rows) -> dict | None:
        selected_stats=[row[0] for row in selected_rows]
        selected_ids={row.demo_file_id for row in selected_stats}
        selected_keys={row.identity_key for row in selected_stats}
        selected_events=[event for event in events if event.demo_file_id in selected_ids]
        return aggregate_player_swing(selected_events,selected_keys,sum(row.rounds_played for row in selected_stats),normalization)
    overall=scope(stats)
    maps={name:scope([row for row in stats if row[1]==name]) for name in sorted({row[1] for row in stats if row[1]})}
    rank_scopes={name:scope([row for row in stats if row[0].opponent_rank_group==group])
                 for name,group in (("top_15","top_15"),("top_16_30","top_16_30"))}
    recent={f"recent_{count}":scope(stats[:count]) for count in (5,10,20)}
    metadata={"round_win_model_version":artifact.model_version if artifact else None,
        "round_swing_model_version":ROUND_SWING_MODEL_VERSION,"trained_at":artifact.trained_at if artifact else None}
    return {"status":"complete" if overall else "partial",**(overall or {}),"overall":overall,
        "maps":maps,"rank_scopes":rank_scopes,"recent":recent,"model":metadata}


def compose_roster_swing_profile(players: list[dict], map_name: str | None = None) -> dict:
    scoped=[]
    for item in players:
        value=item.get("maps",{}).get(map_name) if map_name else item.get("overall")
        scoped.append({"player_id":item["player_id"],"status":"complete" if value else "not_calculated",**(value or {})})
    players=scoped
    available = [item for item in players if item.get("status") == "complete" and item.get("adjusted_per_round") is not None]
    if not available: return {"status":"not_calculated","source":"current_roster","players":players,"sample":{"players":0,"rounds":0},"confidence":0.0}
    ordered = sorted(available, key=lambda item: item["adjusted_per_round"], reverse=True)
    def avg(key, rows=available):
        values=[item[key] for item in rows if item.get(key) is not None]
        return round(sum(values)/len(values),4) if values else None
    total_rounds=sum(item.get("rounds",0) for item in available);confidence=sum(item.get("confidence",0) for item in available)/len(available)
    status="low_confidence" if total_rounds<100 or confidence<.5 else "complete" if len(available)==len(players) else "partial"
    return {"status":status,"source":"current_roster","avg_swing":avg("adjusted_per_round"),
            "avg_score":avg("score"),
            "top2_swing":avg("adjusted_per_round",ordered[:2]),"bottom2_swing":avg("adjusted_per_round",ordered[-2:]),
            "ct_swing":avg("ct"),"t_swing":avg("t"),"opening_swing":avg("opening"),"clutch_swing":avg("clutch"),
            "sample":{"players":len(available),"rounds":total_rounds},"confidence":round(confidence,4),"players":players}


async def roster_swing_profile(session: AsyncSession, player_ids: list[int], map_name: str | None = None) -> dict:
    players=[{"player_id":player_id,**await player_round_swing(session,player_id)} for player_id in player_ids]
    return compose_roster_swing_profile(players,map_name)
