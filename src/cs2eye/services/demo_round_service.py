from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.demo import DemoMapResult, DemoRound, DemoTeamSideStat
from cs2eye.services.demo_team_resolver import normalize_team_name

SIDES = {2: "T", 3: "CT", "2": "T", "3": "CT", "T": "T", "CT": "CT"}
END_REASON_ALIASES = {
    0: "target_bombed", 1: "target_bombed", 7: "bomb_defused",
    8: "terrorists_eliminated", 9: "cts_eliminated", 10: "draw",
    11: "hostages_rescued", 12: "target_saved", 14: "terrorists_escaped",
    15: "game_commencing",
    "target_bombed": "target_bombed", "bomb_defused": "bomb_defused",
    "terrorists_eliminated": "terrorists_eliminated", "cts_eliminated": "cts_eliminated",
    "target_saved": "target_saved", "hostages_rescued": "hostages_rescued",
    "terrorists_escaped": "terrorists_escaped", "game_commencing": "game_commencing",
    "draw": "draw",
    "bomb_exploded": "target_bombed", "ct_killed": "cts_eliminated",
    "t_killed": "terrorists_eliminated", "time_ran_out": "target_saved",
}


def normalize_end_reason(value: object) -> str:
    if isinstance(value, str):
        key = value.strip().casefold().replace(" ", "_")
        if key.isdigit():
            return END_REASON_ALIASES.get(int(key), "unknown")
        return END_REASON_ALIASES.get(key, "unknown")
    return END_REASON_ALIASES.get(value, "unknown")


@dataclass
class ParsedRound:
    raw_round_index: int | None
    winner_side: str | int | None
    t_team_name: str | None
    ct_team_name: str | None
    end_reason: object = None
    raw_scores_after: dict[str, int] = field(default_factory=dict)
    is_warmup: bool = False
    is_restart: bool = False
    is_complete: bool = True
    started_at_tick: int | None = None
    ended_at_tick: int | None = None
    duration_seconds: Decimal | None = None


@dataclass
class NormalizedRound:
    round_number: int
    regulation_round_number: int | None
    overtime_number: int | None
    overtime_round_number: int | None
    phase: str
    half: str
    team_a_side: str
    team_b_side: str
    winner_team_id: int | None
    winner_team_name: str | None
    winner_side: str
    end_reason: str
    team_a_score_before: int
    team_b_score_before: int
    team_a_score_after: int
    team_b_score_after: int
    started_at_tick: int | None
    ended_at_tick: int | None
    duration_seconds: Decimal | None
    is_complete: bool
    issues: list[str] = field(default_factory=list)


def _same_team(left: str | None, right: str | None) -> bool:
    return bool(normalize_team_name(left) and normalize_team_name(left) == normalize_team_name(right))


def normalize_rounds(parsed: list[ParsedRound], result: DemoMapResult) -> tuple[list[NormalizedRound], list[str]]:
    output: list[NormalizedRound] = []
    warnings: list[str] = []
    seen: set[tuple[object, ...]] = set()
    score_a = score_b = 0
    previous_sides: tuple[str, str] | None = None
    side_swap_seen = False
    for raw in parsed:
        if raw.is_warmup:
            warnings.append("warmup_round_skipped")
            continue
        if raw.is_restart:
            warnings.append("restart_round_skipped")
            warnings.append(f"restart_round_skipped:raw_round={raw.raw_round_index}:tick={raw.ended_at_tick}")
            continue
        a_side = "T" if _same_team(raw.t_team_name, result.team_a_name) else "CT" if _same_team(raw.ct_team_name, result.team_a_name) else "unknown"
        b_side = "T" if _same_team(raw.t_team_name, result.team_b_name) else "CT" if _same_team(raw.ct_team_name, result.team_b_name) else "unknown"
        raw_a = next((value for name, value in raw.raw_scores_after.items() if _same_team(name, result.team_a_name)), None)
        raw_b = next((value for name, value in raw.raw_scores_after.items() if _same_team(name, result.team_b_name)), None)
        if raw_a is None or raw_b is None:
            warnings.append("incomplete_round_skipped")
            warnings.append(f"incomplete_round_skipped:raw_round={raw.raw_round_index}:tick={raw.ended_at_tick}")
            continue
        current_sides = (a_side, b_side)
        sides_swapped = previous_sides is not None and current_sides == previous_sides[::-1]
        score_regressed = raw_a < score_a or raw_b < score_b
        early_side_swap_restart = (
            sides_swapped and len(output) <= 1
            and raw_a + raw_b <= score_a + score_b
        )
        if output and (score_regressed or early_side_swap_restart) and (
            not side_swap_seen or early_side_swap_restart
        ):
            discarded = len(output)
            warnings.extend([
                "restart_round_skipped",
                f"restart_round_skipped:score_reset_at_raw_round={raw.raw_round_index}:discarded={discarded}",
            ])
            output.clear()
            seen.clear()
            score_a = score_b = 0
            side_swap_seen = False
        else:
            side_swap_seen = side_swap_seen or sides_swapped
        signature = (
            raw.raw_round_index, raw.winner_side, normalize_team_name(raw.t_team_name),
            normalize_team_name(raw.ct_team_name), raw_a, raw_b,
        )
        if signature in seen:
            warnings.append("duplicate_round_event")
            warnings.append(f"duplicate_round_event:raw_round={raw.raw_round_index}:tick={raw.ended_at_tick}")
            continue
        seen.add(signature)
        side = SIDES.get(raw.winner_side, "unknown")
        winner_name = raw.t_team_name if side == "T" else raw.ct_team_name if side == "CT" else None
        # Some demos omit winner on a valid round_end. A single +1 score
        # transition is sufficient to recover the winner without guessing.
        if side == "unknown" or not raw.is_complete:
            if raw_a == score_a + 1 and raw_b == score_b:
                winner_name, side = result.team_a_name, a_side
            elif raw_b == score_b + 1 and raw_a == score_a:
                winner_name, side = result.team_b_name, b_side
        if side == "unknown" or not winner_name:
            warnings.append("incomplete_round_skipped")
            warnings.append(f"incomplete_round_skipped:raw_round={raw.raw_round_index}:tick={raw.ended_at_tick}")
            continue
        issues: list[str] = []
        if "unknown" in {a_side, b_side} or a_side == b_side:
            issues.append("unknown_round_side")
        winner_id = result.team_a_id if _same_team(winner_name, result.team_a_name) else result.team_b_id if _same_team(winner_name, result.team_b_name) else None
        if not winner_name or not (_same_team(winner_name, result.team_a_name) or _same_team(winner_name, result.team_b_name)):
            issues.append("unknown_round_winner")
        complete = not any(code in issues for code in ("unknown_round_side", "unknown_round_winner"))
        if not output and raw_a + raw_b > 1:
            # A continuation demo (commonly suffixed p2) starts with the score
            # accumulated in the missing first recording. At round_end the raw
            # score already includes the current winner, so recover the score
            # before this round and keep the real map round number.
            score_a, score_b = raw_a, raw_b
            if _same_team(winner_name, result.team_a_name):
                score_a = max(0, score_a - 1)
            elif _same_team(winner_name, result.team_b_name):
                score_b = max(0, score_b - 1)
        before_a, before_b = score_a, score_b
        if complete and _same_team(winner_name, result.team_a_name): score_a += 1
        elif complete and _same_team(winner_name, result.team_b_name): score_b += 1
        # demoparser2 may expose team_rounds_total either immediately before or
        # after the round increment. After a side swap those counters can also
        # remain attached to the T/CT slots rather than to the clan names. The
        # total is stable in both cases, while winner_side is the authoritative
        # source for assigning the point to a team.
        raw_total = raw_a + raw_b
        if raw_total not in {before_a + before_b, score_a + score_b}:
            issues.append("round_score_mismatch")
            warnings.append(
                f"round_score_mismatch:round={len(output) + 1}:"
                f"raw={raw_a}:{raw_b}:calculated={score_a}:{score_b}"
            )
        number = score_a + score_b
        phase = "overtime" if number > 24 else "regulation"
        if phase == "regulation":
            half = "first_half" if number <= 12 else "second_half"
            regulation_number, overtime_number, overtime_round = number, None, None
        else:
            ot_index = number - 25
            overtime_number, overtime_round = ot_index // 6 + 1, ot_index % 6 + 1
            half = "overtime_first_half" if overtime_round <= 3 else "overtime_second_half"
            regulation_number = None
        reason = normalize_end_reason(raw.end_reason)
        if reason == "unknown": issues.append("unknown_end_reason")
        warnings.extend(issues)
        output.append(NormalizedRound(number, regulation_number, overtime_number, overtime_round, phase, half, a_side, b_side, winner_id, winner_name, side, reason, before_a, before_b, score_a, score_b, raw.started_at_tick, raw.ended_at_tick, raw.duration_seconds, complete, issues))
        previous_sides = current_sides
    return output, list(dict.fromkeys(warnings))


def round_data_status(rounds: list[NormalizedRound], result: DemoMapResult) -> tuple[str, list[str]]:
    warnings: list[str] = []
    blocking = {"unknown_round_side", "unknown_round_winner", "round_score_mismatch", "invalid_score_transition"}
    valid = [item for item in rounds if item.is_complete and not blocking.intersection(item.issues)]
    if (
        valid and valid[0].round_number > 1
        and (valid[-1].team_a_score_after, valid[-1].team_b_score_after)
        == (result.team_a_score, result.team_b_score)
    ):
        return "partial", []
    wins_a = sum(_same_team(item.winner_team_name, result.team_a_name) for item in valid)
    wins_b = sum(_same_team(item.winner_team_name, result.team_b_name) for item in valid)
    if len(valid) != result.rounds_count:
        warnings.extend([
            "round_count_mismatch",
            f"round_count_mismatch:parsed={len(valid)}:expected={result.rounds_count}",
        ])
    if (wins_a, wins_b) != (result.team_a_score, result.team_b_score):
        warnings.extend([
            "final_score_mismatch",
            f"final_score_mismatch:parsed={wins_a}:{wins_b}:expected={result.team_a_score}:{result.team_b_score}",
        ])
    if any(item.team_a_side == "unknown" or item.team_b_side == "unknown" for item in rounds): warnings.append("unknown_round_side")
    if not rounds: return "partial", warnings
    return ("complete" if not warnings else "needs_review"), warnings


async def replace_rounds(session: AsyncSession, result: DemoMapResult, rounds: list[NormalizedRound]) -> None:
    await session.execute(delete(DemoRound).where(DemoRound.demo_file_id == result.demo_file_id))
    session.add_all([DemoRound(
        demo_file_id=result.demo_file_id, demo_map_result_id=result.id,
        round_number=item.round_number, regulation_round_number=item.regulation_round_number,
        overtime_number=item.overtime_number, overtime_round_number=item.overtime_round_number,
        phase=item.phase, half=item.half, team_a_side=item.team_a_side, team_b_side=item.team_b_side,
        winner_team_id=item.winner_team_id, winner_team_name=item.winner_team_name, winner_side=item.winner_side,
        end_reason=item.end_reason, team_a_score_before=item.team_a_score_before, team_b_score_before=item.team_b_score_before,
        team_a_score_after=item.team_a_score_after, team_b_score_after=item.team_b_score_after,
        started_at_tick=item.started_at_tick, ended_at_tick=item.ended_at_tick, duration_seconds=item.duration_seconds,
        is_warmup=False, is_restart=False,
        is_complete=item.is_complete and not {"unknown_round_side", "unknown_round_winner", "round_score_mismatch", "invalid_score_transition"}.intersection(item.issues),
    ) for item in rounds])


def _rate(won: int, played: int) -> Decimal | None:
    return (Decimal(won) * 100 / Decimal(played)).quantize(Decimal("0.0001")) if played else None


async def recalculate_demo_team_side_stats(session: AsyncSession, result: DemoMapResult) -> list[DemoTeamSideStat]:
    await session.execute(delete(DemoTeamSideStat).where(DemoTeamSideStat.demo_file_id == result.demo_file_id))
    rounds = list((await session.execute(select(DemoRound).where(DemoRound.demo_file_id == result.demo_file_id, DemoRound.is_complete.is_(True)).order_by(DemoRound.round_number))).scalars().all())
    stats: list[DemoTeamSideStat] = []
    for key in ("a", "b"):
        name, team_id = getattr(result, f"team_{key}_name"), getattr(result, f"team_{key}_id")
        values = {side: [item for item in rounds if getattr(item, f"team_{key}_side") == side] for side in ("CT", "T")}
        won = {side: sum(_same_team(item.winner_team_name, name) for item in items) for side, items in values.items()}
        first = [item for item in rounds if item.half == "first_half"]
        second = [item for item in rounds if item.half == "second_half"]
        overtime = [item for item in rounds if item.phase == "overtime"]
        total_won = sum(_same_team(item.winner_team_name, name) for item in rounds)
        stat = DemoTeamSideStat(
            demo_file_id=result.demo_file_id, demo_map_result_id=result.id, team_id=team_id, team_name=name or f"Team {key.upper()}",
            ct_rounds_played=len(values["CT"]), ct_rounds_won=won["CT"], ct_rounds_lost=len(values["CT"])-won["CT"], ct_win_rate=_rate(won["CT"], len(values["CT"])),
            t_rounds_played=len(values["T"]), t_rounds_won=won["T"], t_rounds_lost=len(values["T"])-won["T"], t_win_rate=_rate(won["T"], len(values["T"])),
            first_half_rounds_played=len(first), first_half_rounds_won=sum(_same_team(item.winner_team_name, name) for item in first),
            second_half_rounds_played=len(second), second_half_rounds_won=sum(_same_team(item.winner_team_name, name) for item in second),
            overtime_rounds_played=len(overtime), overtime_rounds_won=sum(_same_team(item.winner_team_name, name) for item in overtime),
            total_rounds_played=len(rounds), total_rounds_won=total_won, total_rounds_lost=len(rounds)-total_won,
        )
        session.add(stat); stats.append(stat)
    result.rounds_parsed_count = len(rounds)
    consistent = (
        len(rounds) == result.rounds_count
        and len(stats) == 2
        and stats[0].total_rounds_won == result.team_a_score
        and stats[1].total_rounds_won == result.team_b_score
        and all(item.team_a_side != "unknown" and item.team_b_side != "unknown" for item in rounds)
    )
    result.round_data_status = "complete" if consistent else "needs_review" if rounds else "partial"
    return stats
