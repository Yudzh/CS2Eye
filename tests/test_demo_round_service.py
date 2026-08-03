from cs2eye.models.demo import DemoMapResult
from cs2eye.services.demo_round_service import (
    ParsedRound, normalize_end_reason, normalize_rounds, round_data_status,
)


def map_result(a=13, b=9):
    return DemoMapResult(
        demo_file_id=1, team_a_id=10, team_a_name="Spirit", team_a_score=a,
        team_b_id=20, team_b_name="NAVI", team_b_score=b,
        rounds_count=a + b, result_source="demo_parser", metadata_status="complete",
    )


def mr12_rounds(a_wins=13, b_wins=9):
    winners = ["Spirit"] * a_wins + ["NAVI"] * b_wins
    parsed = []
    score_a = score_b = 0
    for index, winner in enumerate(winners, 1):
        first = index <= 12
        t_name, ct_name = ("Spirit", "NAVI") if first else ("NAVI", "Spirit")
        if winner == "Spirit": score_a += 1
        else: score_b += 1
        parsed.append(ParsedRound(
            raw_round_index=index, winner_side="T" if winner == t_name else "CT",
            t_team_name=t_name, ct_team_name=ct_name, end_reason="target_bombed",
            raw_scores_after={"Spirit": score_a, "NAVI": score_b},
        ))
    return parsed


def test_mr12_rounds_have_sides_halves_scores_and_complete_status():
    result = map_result()
    rounds, warnings = normalize_rounds(mr12_rounds(), result)
    assert warnings == []
    assert [item.round_number for item in rounds] == list(range(1, 23))
    assert (rounds[0].team_a_side, rounds[0].team_b_side) == ("T", "CT")
    assert (rounds[12].team_a_side, rounds[12].team_b_side) == ("CT", "T")
    assert rounds[11].half == "first_half"
    assert rounds[12].half == "second_half"
    assert (rounds[-1].team_a_score_after, rounds[-1].team_b_score_after) == (13, 9)
    assert round_data_status(rounds, result)[0] == "complete"


def test_warmup_restart_and_duplicate_are_skipped():
    result = map_result(1, 0)
    parsed = [
        ParsedRound(0, "T", "Spirit", "NAVI", is_warmup=True),
        ParsedRound(0, "T", "Spirit", "NAVI", is_restart=True),
        ParsedRound(1, "T", "Spirit", "NAVI", end_reason="target_bombed", raw_scores_after={"Spirit": 1, "NAVI": 0}),
        ParsedRound(1, "T", "Spirit", "NAVI", end_reason="target_bombed", raw_scores_after={"Spirit": 1, "NAVI": 0}),
    ]
    rounds, warnings = normalize_rounds(parsed, result)
    assert len(rounds) == 1
    assert {"warmup_round_skipped", "restart_round_skipped", "duplicate_round_event"}.issubset(warnings)


def test_unknown_winner_and_reason_are_reported():
    rounds, warnings = normalize_rounds([ParsedRound(1, None, "Spirit", "NAVI", end_reason="odd", is_complete=False)], map_result(0, 0))
    assert rounds == []
    assert "incomplete_round_skipped" in warnings
    assert normalize_end_reason("odd") == "unknown"


def test_overtime_is_separate_from_regulation_halves():
    result = map_result(16, 13)
    rounds, _ = normalize_rounds(mr12_rounds(16, 13), result)
    assert rounds[24].phase == "overtime"
    assert rounds[24].half == "overtime_first_half"
    assert rounds[24].regulation_round_number is None
    assert rounds[24].overtime_number == 1


def test_demoparser_end_reason_strings_are_normalized():
    assert normalize_end_reason("bomb_exploded") == "target_bombed"
    assert normalize_end_reason("ct_killed") == "cts_eliminated"
    assert normalize_end_reason("t_killed") == "terrorists_eliminated"
    assert normalize_end_reason("time_ran_out") == "target_saved"


def test_repeated_raw_number_with_new_score_is_not_a_duplicate():
    result = map_result(0, 2)
    rounds, warnings = normalize_rounds([
        ParsedRound(1, "CT", "Spirit", "NAVI", raw_scores_after={"Spirit": 0, "NAVI": 1}, end_reason="t_killed"),
        ParsedRound(1, "CT", "Spirit", "NAVI", raw_scores_after={"Spirit": 0, "NAVI": 2}, end_reason="t_killed"),
    ], result)
    assert len(rounds) == 2
    assert "duplicate_round_event" not in warnings
    assert rounds[-1].team_b_score_after == 2


def test_missing_winner_is_recovered_from_single_score_increment():
    result = map_result(1, 0)
    rounds, warnings = normalize_rounds([
        ParsedRound(3, None, "Spirit", "NAVI", raw_scores_after={"Spirit": 1, "NAVI": 0}, is_complete=False, end_reason="ct_killed"),
    ], result)
    assert "incomplete_round_skipped" not in warnings
    assert rounds[0].winner_team_name == "Spirit"
    assert rounds[0].winner_side == "T"


def test_service_round_without_team_score_state_is_skipped():
    rounds, warnings = normalize_rounds([
        ParsedRound(1, "T", "Spirit", "NAVI", end_reason="ct_killed"),
    ], map_result(0, 0))
    assert rounds == []
    assert "incomplete_round_skipped" in warnings


def test_score_reset_discards_knife_segment_and_restarts_numbering():
    result = map_result(0, 1)
    rounds, warnings = normalize_rounds([
        ParsedRound(1, "T", "Spirit", "NAVI", raw_scores_after={"Spirit": 1, "NAVI": 0}, end_reason="ct_killed"),
        ParsedRound(1, "CT", "Spirit", "NAVI", raw_scores_after={"Spirit": 0, "NAVI": 1}, end_reason="t_killed"),
    ], result)
    assert len(rounds) == 1
    assert rounds[0].round_number == 1
    assert rounds[0].winner_team_name == "NAVI"
    assert "restart_round_skipped" in warnings


def test_pre_increment_slot_scores_survive_halftime_side_swap():
    result = map_result(3, 2)
    parsed = [
        ParsedRound(1, "CT", "Spirit", "NAVI", raw_scores_after={"Spirit": 0, "NAVI": 0}, end_reason="t_killed"),
        ParsedRound(2, "T", "Spirit", "NAVI", raw_scores_after={"Spirit": 0, "NAVI": 1}, end_reason="ct_killed"),
        ParsedRound(1, "CT", "NAVI", "Spirit", raw_scores_after={"NAVI": 1, "Spirit": 1}, end_reason="t_killed"),
        ParsedRound(2, "CT", "NAVI", "Spirit", raw_scores_after={"NAVI": 2, "Spirit": 1}, end_reason="t_killed"),
        ParsedRound(3, "T", "NAVI", "Spirit", raw_scores_after={"NAVI": 2, "Spirit": 2}, end_reason="ct_killed"),
    ]
    rounds, warnings = normalize_rounds(parsed, result)
    assert len(rounds) == 5
    assert not any(item.startswith("round_score_mismatch") for item in warnings)
    assert "restart_round_skipped" not in warnings
    assert (rounds[-1].team_a_score_after, rounds[-1].team_b_score_after) == (3, 2)
    assert round_data_status(rounds, result)[0] == "complete"


def test_knife_round_is_discarded_when_official_sides_swap():
    result = map_result(1, 1)
    parsed = [
        ParsedRound(1, "T", "Spirit", "NAVI", raw_scores_after={"Spirit": 1, "NAVI": 0}, end_reason="ct_killed"),
        ParsedRound(1, "T", "NAVI", "Spirit", raw_scores_after={"NAVI": 1, "Spirit": 0}, end_reason="ct_killed"),
        ParsedRound(2, "CT", "NAVI", "Spirit", raw_scores_after={"NAVI": 1, "Spirit": 0}, end_reason="t_killed"),
    ]
    rounds, warnings = normalize_rounds(parsed, result)
    assert len(rounds) == 2
    assert (rounds[-1].team_a_score_after, rounds[-1].team_b_score_after) == (1, 1)
    assert "restart_round_skipped" in warnings


def test_continuation_demo_keeps_initial_score_and_real_round_numbers():
    result = map_result(13, 6)
    parsed = [
        ParsedRound(1, "T", "Spirit", "NAVI", raw_scores_after={"Spirit": 12, "NAVI": 6}, end_reason="ct_killed"),
        ParsedRound(2, "T", "Spirit", "NAVI", raw_scores_after={"Spirit": 13, "NAVI": 6}, end_reason="ct_killed"),
    ]
    rounds, warnings = normalize_rounds(parsed, result)
    assert warnings == []
    assert [item.round_number for item in rounds] == [18, 19]
    assert (rounds[0].team_a_score_before, rounds[0].team_b_score_before) == (11, 6)
    assert (rounds[-1].team_a_score_after, rounds[-1].team_b_score_after) == (13, 6)
    assert round_data_status(rounds, result) == ("partial", [])
