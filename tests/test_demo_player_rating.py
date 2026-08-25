from decimal import Decimal
from io import BytesIO

import pytest
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy import func, select

from cs2eye.db.base import Base
from cs2eye.models.demo import DemoParseRun, DemoPlayerStat
from cs2eye.models.demo_file import DemoFile
from cs2eye.models.team import Player, Team
from cs2eye.services.demo_player_link_service import link_demo_player
from cs2eye.services.demo_parser_service import (
    DamageEvent, DeathEvent, Demoparser2Adapter, ParsedDemoPlayerStat,
    PlayerRef, RoundSnapshot,
    aggregate_player_events,
    completed_rounds_count, is_gameplay_round_end_row, is_restart_round_row, is_valid_round_row,
)
from cs2eye.services.demo_parser_service import _rows
from cs2eye.services.player_internal_rating_service import (
    INTERNAL_RATING_VERSION, calculate_internal_rating, calculate_rating_sample,
    recalculate_player_internal_rating,
)
from cs2eye.services.demo_parse_service import DemoParseService
from cs2eye.services.demo_storage_service import DemoStorageService
from cs2eye.services.demo_team_link_service import opponent_rank_group, resolve_demo_opponents


def player(steam_id: str, nickname: str, team: int) -> PlayerRef:
    return PlayerRef(steam_id, nickname, f"Team {team}", team)


def test_restart_round_rows_are_not_gameplay_boundaries() -> None:
    assert is_restart_round_row({"is_game_restart": True, "winner": 2})
    assert is_restart_round_row({"round_win_reason": 15, "winner": 3})
    assert is_restart_round_row({"reason": "game_commencing"})
    assert not is_restart_round_row({"round_win_reason": 8, "winner": 3})
    assert not is_gameplay_round_end_row({"tick": 1, "winner": float("nan")})
    assert is_gameplay_round_end_row({"tick": 100, "winner": "CT"})


def test_adr_and_kast_and_team_damage() -> None:
    a = player("1", "Alpha", 2)
    b = player("2", "Bravo", 3)
    teammate = player("3", "Ally", 2)
    snapshots = [
        RoundSnapshot(1, [(a, True), (b, False), (teammate, True)]),
        RoundSnapshot(2, [(a, False), (b, True), (teammate, True)]),
    ]
    deaths = [
        DeathEvent(1, b, a, teammate),
        DeathEvent(2, a, b, None),
    ]
    damages = [
        DamageEvent(1, a, b, 100),
        DamageEvent(2, a, teammate, 80),  # team damage is excluded
    ]
    stats = {item.nickname: item for item in aggregate_player_events(
        snapshots, deaths, damages,
    )}
    assert stats["Alpha"].adr == Decimal("50.0000")
    assert stats["Alpha"].kast_rounds == 1
    assert stats["Alpha"].kast_percent == Decimal("50.0000")
    assert stats["Ally"].assists == 1


def test_demoparser_rows_accepts_plain_and_nested_lists() -> None:
    assert _rows([{"tick": 10}, {"tick": 20}]) == [{"tick": 10}, {"tick": 20}]
    assert _rows([[{"tick": 10}], [{"tick": 20}]]) == [{"tick": 10}, {"tick": 20}]


def test_trade_counts_for_kast() -> None:
    victim = player("1", "Victim", 2)
    killer = player("2", "Killer", 3)
    trader = player("3", "Trader", 2)
    snapshot = RoundSnapshot(1, [(victim, False), (killer, False), (trader, True)])
    deaths = [
        DeathEvent(1, victim, killer, None),
        DeathEvent(1, killer, trader, None),
    ]
    stats = {item.nickname: item for item in aggregate_player_events([snapshot], deaths, [])}
    assert stats["Victim"].kast_percent == Decimal("100.0000")


def test_demo_rating_formula_and_limits() -> None:
    rating = calculate_internal_rating(
        rounds_played=20, kills=20, deaths=10, assists=5,
        adr=Decimal("100"), kast_percent=Decimal("75"),
    )
    expected = (
        Decimal("0.35") + Decimal("0.025") + Decimal("0.10")
        + Decimal("0.20") + Decimal("0.1125")
    ) * Decimal("10")
    assert rating == expected.quantize(Decimal("0.0001"))
    assert Decimal("4") < rating < Decimal("9")
    strong = calculate_internal_rating(
        rounds_played=20, kills=30, deaths=8, assists=8,
        adr=Decimal("130"), kast_percent=Decimal("90"),
    )
    weak = calculate_internal_rating(
        rounds_played=20, kills=5, deaths=19, assists=1,
        adr=Decimal("30"), kast_percent=Decimal("30"),
    )
    assert strong > rating > weak
    assert calculate_internal_rating(
        rounds_played=1, kills=100, deaths=0, assists=100,
        adr=Decimal("10000"), kast_percent=Decimal("100"),
    ) == Decimal("10.0000")
    assert calculate_internal_rating(
        rounds_played=1, kills=0, deaths=100, assists=0,
        adr=Decimal("0"), kast_percent=Decimal("0"),
    ) == Decimal("0.0000")


def test_warmup_and_technical_rounds_are_invalid() -> None:
    assert is_valid_round_row({"is_warmup_period": False, "is_technical_timeout": False})
    assert not is_valid_round_row({"is_warmup_period": True})
    assert not is_valid_round_row({"is_technical_timeout": True})


def test_completed_rounds_count_deduplicates_repeated_round_end() -> None:
    assert completed_rounds_count([
        {"tick": 100, "total_rounds_played": 1},
        {"tick": 101, "total_rounds_played": 1},
        {"tick": 200, "total_rounds_played": 2},
    ]) == 2


@pytest.mark.parametrize(("rank", "group"), [
    (1, "top_15"), (15, "top_15"),
    (16, "top_16_30"), (30, "top_16_30"),
    (31, "outside_top_30"), (None, "unknown"),
])
def test_opponent_rank_boundaries(rank, group) -> None:
    assert opponent_rank_group(rank) == group


def test_rating_samples_are_independent_and_weighted() -> None:
    rows = [
        (1, Decimal("7.5000"), 20, "top_15"),
        (2, Decimal("6.8000"), 30, "top_16_30"),
        (3, Decimal("9.0000"), 10, "outside_top_30"),
        (4, Decimal("5.0000"), 10, "unknown"),
    ]
    overall = calculate_rating_sample(rows)
    top15 = calculate_rating_sample(rows, "top_15")
    top16 = calculate_rating_sample(rows, "top_16_30")
    assert overall.rating == Decimal("7.0571")
    assert (overall.maps_count, overall.rounds_count) == (4, 70)
    assert (top15.rating, top15.maps_count, top15.rounds_count) == (
        Decimal("7.5000"), 1, 20,
    )
    assert (top16.rating, top16.maps_count, top16.rounds_count) == (
        Decimal("6.8000"), 1, 30,
    )
    assert calculate_rating_sample(rows, "missing").rating is None


def test_demoparser_adapter_normalizes_events(monkeypatch, tmp_path) -> None:
    class Frame:
        def __init__(self, rows):
            self.rows = rows

        def to_dicts(self):
            return self.rows

    class Parser:
        def __init__(self, path):
            assert path.endswith("fixture.dem")

        def parse_ticks(self, props, *, ticks=None, **kwargs):
            assert ticks == [100]
            return Frame([
                {"tick": 100, "steamid": "1", "name": "A", "team_num": 2, "team_name": "Alpha", "is_alive": True},
                {"tick": 100, "steamid": "2", "name": "B", "team_num": 3, "team_name": "Bravo", "is_alive": False},
            ])

        def parse_event(self, name, **kwargs):
            common = {"total_rounds_played": 1, "is_warmup_period": False, "is_technical_timeout": False}
            if name == "round_end":
                return Frame([{"tick": 100, **common}])
            if name == "player_death":
                return Frame([
                    {**common, "tick": 90, "user_steamid": "2", "user_name": "B", "user_team_num": 3, "attacker_steamid": "1", "attacker_name": "A", "attacker_team_num": 2},
                    {**common, "tick": 95, "noreplay": True, "user_steamid": "1", "user_name": "A", "user_team_num": 2, "attacker_steamid": "2", "attacker_name": "B", "attacker_team_num": 3},
                ])
            return Frame([{**common, "user_steamid": "2", "user_name": "B", "user_team_num": 3, "attacker_steamid": "1", "attacker_name": "A", "attacker_team_num": 2, "dmg_health": 90}])

    monkeypatch.setattr("cs2eye.services.demo_parser_service.DemoParser", Parser)
    stats = {item.nickname: item for item in Demoparser2Adapter().parse(tmp_path / "fixture.dem")}
    assert stats["A"].kills == 1
    assert stats["A"].adr == Decimal("90.0000")
    assert stats["B"].deaths == 1


def test_demoparser_adapter_extracts_team_rounds_total(monkeypatch, tmp_path) -> None:
    class Frame:
        def __init__(self, rows):
            self.rows = rows

        def to_dicts(self):
            return self.rows

    class Parser:
        def __init__(self, _path):
            pass

        def parse_header(self):
            return {"map_name": "de_mirage"}

        def parse_event(self, name, **_kwargs):
            if name == "round_end":
                return Frame([{
                    "tick": 100, "total_rounds_played": 22,
                    "is_warmup_period": False, "is_technical_timeout": False,
                }])
            return Frame([])

        def parse_ticks(self, props, *, ticks=None, **_kwargs):
            if "team_rounds_total" in props:
                return Frame([
                    {"tick": 100, "team_num": 2, "team_clan_name": "Spirit", "team_rounds_total": 13, "team_score_overtime": 0},
                    {"tick": 100, "team_num": 3, "team_clan_name": "NAVI", "team_rounds_total": 9, "team_score_overtime": 0},
                ])
            return Frame([])

    monkeypatch.setattr("cs2eye.services.demo_parser_service.DemoParser", Parser)
    parsed = Demoparser2Adapter().parse(tmp_path / "fixture.dem")
    assert parsed.map_result.raw_map_name == "de_mirage"
    assert (parsed.map_result.team_a_name, parsed.map_result.team_a_score) == ("Spirit", 13)
    assert (parsed.map_result.team_b_name, parsed.map_result.team_b_score) == ("NAVI", 9)
    assert parsed.map_result.parser_rounds_count is None


def test_bomb_event_after_round_end_stays_with_started_round(monkeypatch, tmp_path) -> None:
    class Frame:
        def __init__(self, rows):
            self.rows = rows

        def to_dicts(self):
            return self.rows

    common = {"is_warmup_period": False, "is_technical_timeout": False}

    class Parser:
        def __init__(self, _path):
            pass

        def parse_header(self):
            return {"map_name": "de_mirage"}

        def parse_event(self, name, **_kwargs):
            if name == "round_start":
                return Frame([
                    {"tick": 10, "total_rounds_played": 0, **common},
                    {"tick": 110, "total_rounds_played": 1, **common},
                ])
            if name == "round_end":
                return Frame([
                    {"tick": 100, "total_rounds_played": 1, "winner": 2, "round_win_reason": 9, **common},
                    {"tick": 200, "total_rounds_played": 2, "winner": 3, "round_win_reason": 8, **common},
                ])
            if name == "bomb_planted":
                return Frame([{"tick": 80, "total_rounds_played": 0, **common}])
            if name == "bomb_exploded":
                return Frame([{"tick": 105, "total_rounds_played": 1, **common}])
            return Frame([])

        def parse_ticks(self, _props, *, ticks=None, **_kwargs):
            rows = []
            for tick, t_score, ct_score in [(100, 1, 0), (200, 1, 1)]:
                rows.extend([
                    {"tick": tick, "team_num": 2, "team_clan_name": "Alpha", "team_rounds_total": t_score, "team_score_overtime": 0},
                    {"tick": tick, "team_num": 3, "team_clan_name": "Bravo", "team_rounds_total": ct_score, "team_score_overtime": 0},
                ])
            return Frame(rows)

    monkeypatch.setattr("cs2eye.services.demo_parser_service.DemoParser", Parser)
    rounds = Demoparser2Adapter().parse(tmp_path / "fixture.dem").rounds
    assert (rounds[0].bomb_planted, rounds[0].bomb_exploded) == (True, True)
    assert (rounds[1].bomb_planted, rounds[1].bomb_exploded) == (False, False)


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


async def test_player_linking_rules(db_session) -> None:
    exact = Player(bo3_id=1, bo3_slug="donk", nickname="donk", steam_id="7656")
    nickname = Player(bo3_id=2, bo3_slug="zywoo", nickname="ZywOo")
    aliased = Player(bo3_id=5, bo3_slug="naf", nickname="NAF")
    slaxz = Player(bo3_id=6, bo3_slug="slaxz", nickname="slaxz")
    vsm = Player(bo3_id=7, bo3_slug="vsm", nickname="vsm")
    duplicate_a = Player(bo3_id=3, bo3_slug="same-a", nickname="same")
    duplicate_b = Player(bo3_id=4, bo3_slug="same-b", nickname=" SAME ")
    db_session.add_all([exact, nickname, aliased, slaxz, vsm, duplicate_a, duplicate_b])
    await db_session.commit()
    assert await link_demo_player(db_session, "7656", "anything") is exact
    assert await link_demo_player(db_session, "999", "  zywoo ") is nickname
    assert nickname.steam_id == "999"
    assert await link_demo_player(db_session, None, "NAF-FLY") is aliased
    assert await link_demo_player(db_session, "76561198064353169", "slaxz-") is slaxz
    assert slaxz.steam_id == "76561198064353169"
    assert await link_demo_player(db_session, "76561198011732823", "v$m") is vsm
    assert vsm.steam_id == "76561198011732823"
    assert await link_demo_player(db_session, None, "same") is None
    assert await link_demo_player(db_session, None, "unknown") is None


async def test_players_get_groups_from_different_demo_opponents(db_session) -> None:
    navi = Team(bo3_id=101, bo3_slug="navi", name="NAVI", current_rank=3)
    astralis = Team(bo3_id=102, bo3_slug="astralis", name="Astralis", current_rank=22)
    db_session.add_all([navi, astralis])
    await db_session.commit()
    stats = [
        ParsedDemoPlayerStat("1", "NAVI player", "NAVI", 10, 1, 1, 1, 10, Decimal("1"), 1, Decimal("10"), Decimal("5")),
        ParsedDemoPlayerStat("2", "Astralis player", "Astralis", 10, 1, 1, 1, 10, Decimal("1"), 1, Decimal("10"), Decimal("5")),
    ]
    snapshots, diagnostics = await resolve_demo_opponents(db_session, stats)
    assert diagnostics == []
    assert snapshots[stats[0].identity_key].opponent_rank_group == "top_16_30"
    assert snapshots[stats[1].identity_key].opponent_rank_group == "top_15"
    old_snapshot = snapshots[stats[0].identity_key]
    astralis.current_rank = 10
    await db_session.commit()
    refreshed, _ = await resolve_demo_opponents(db_session, stats)
    assert old_snapshot.opponent_rank == 22
    assert old_snapshot.opponent_rank_group == "top_16_30"
    assert refreshed[stats[0].identity_key].opponent_rank == 10
    assert refreshed[stats[0].identity_key].opponent_rank_group == "top_15"


async def test_demo_team_suffixes_match_short_database_names(db_session) -> None:
    faze = Team(bo3_id=201, bo3_slug="faze", name="Faze", current_rank=5)
    g2 = Team(bo3_id=202, bo3_slug="g2", name="G2", current_rank=12)
    db_session.add_all([faze, g2])
    await db_session.commit()
    stats = [
        ParsedDemoPlayerStat("1", "frozen", "FaZe Clan", 10, 1, 1, 1, 10, Decimal("1"), 1, Decimal("10"), Decimal("5")),
        ParsedDemoPlayerStat("2", "m0NESY", "G2 Esports CS2", 10, 1, 1, 1, 10, Decimal("1"), 1, Decimal("10"), Decimal("5")),
    ]

    snapshots, diagnostics = await resolve_demo_opponents(db_session, stats)

    assert diagnostics == []
    assert snapshots[stats[0].identity_key].demo_team_id == faze.id
    assert snapshots[stats[0].identity_key].opponent_team_id == g2.id
    assert snapshots[stats[1].identity_key].demo_team_id == g2.id
    assert snapshots[stats[1].identity_key].opponent_team_id == faze.id


async def test_aggregate_rating_is_weighted_and_ignores_failed(db_session) -> None:
    player_row = Player(bo3_id=10, bo3_slug="p", nickname="P")
    db_session.add(player_row)
    await db_session.flush()
    demo_a = DemoFile(
        tournament_name="Cup", tournament_slug="cup", match_date=__import__("datetime").date(2026, 1, 1),
        original_filename="a.dem", storage_path="a.dem", file_size_bytes=1, sha256="a" * 64,
    )
    demo_b = DemoFile(
        tournament_name="Cup", tournament_slug="cup", match_date=__import__("datetime").date(2026, 1, 2),
        original_filename="b.dem", storage_path="b.dem", file_size_bytes=1, sha256="b" * 64,
    )
    demo_c = DemoFile(
        tournament_name="Cup", tournament_slug="cup", match_date=__import__("datetime").date(2026, 1, 3),
        original_filename="c.dem", storage_path="c.dem", file_size_bytes=1, sha256="c" * 64,
    )
    db_session.add_all([demo_a, demo_b, demo_c])
    await db_session.flush()
    run_a = DemoParseRun(demo_file_id=demo_a.id, status="success", parser_name="test", parser_version="1")
    run_b = DemoParseRun(demo_file_id=demo_b.id, status="success", parser_name="test", parser_version="1")
    run_c = DemoParseRun(demo_file_id=demo_c.id, status="failed", parser_name="test", parser_version="1")
    db_session.add_all([run_a, run_b, run_c])
    await db_session.flush()
    for demo, run, rounds, rating in (
        (demo_a, run_a, 20, "7.5000"),
        (demo_b, run_b, 30, "6.8000"),
        (demo_c, run_c, 10, "10.0000"),
    ):
        db_session.add(DemoPlayerStat(
            demo_file_id=demo.id, parse_run_id=run.id, player_id=player_row.id,
            steam_id="1", identity_key="steam:1", nickname="P", team_name=None,
            rounds_played=rounds, kills=1, deaths=1, assists=1, total_damage=1,
            adr=Decimal("1"), kast_rounds=1, kast_percent=Decimal("1"),
            internal_rating=Decimal(rating),
            internal_rating_version=INTERNAL_RATING_VERSION,
        ))
    await db_session.commit()
    await recalculate_player_internal_rating(db_session, player_row.id)
    assert player_row.internal_rating == Decimal("7.0800")
    assert player_row.internal_rating_maps_count == 2
    assert player_row.internal_rating_rounds_count == 50
    assert player_row.internal_rating_version == INTERNAL_RATING_VERSION
    assert player_row.internal_rating_top15 is None
    assert player_row.internal_rating_top15_maps_count == 0
    assert player_row.internal_rating_top16_30 is None


async def test_reparse_replaces_stats_without_duplicates(db_session, tmp_path) -> None:
    player_row = Player(
        bo3_id=20, bo3_slug="linked", nickname="Linked",
        bo3_rating=Decimal("7.4200"), player_strength=74,
    )
    demo = DemoFile(
        tournament_name="Cup", tournament_slug="cup", match_date=__import__("datetime").date(2026, 2, 1),
        original_filename="map.dem", storage_path="demos/tournaments/cup/2026/2026-02-01/map.dem", file_size_bytes=1, sha256="c" * 64,
    )
    db_session.add_all([player_row, demo])
    await db_session.commit()
    service = DemoParseService(db_session, tmp_path)

    class Parser:
        parser_name = "test"
        parser_version = "1"
        kills = 10

        def parse(self, path):
            return [ParsedDemoPlayerStat(
                steam_id="20", nickname="Linked", team_name="Team",
                rounds_played=10, kills=self.kills, deaths=5, assists=2,
                total_damage=800, adr=Decimal("80"), kast_rounds=7,
                kast_percent=Decimal("70"), internal_rating=Decimal("7.0000"),
            )]

    parser = Parser()
    service.parser = parser
    first, _ = await service.parse_one(demo, False)
    parser.kills = 15
    second, _ = await service.parse_one(demo, True)
    count = await db_session.scalar(select(func.count(DemoPlayerStat.id)))
    saved = (await db_session.execute(select(DemoPlayerStat))).scalar_one()
    assert first.status == second.status == "parsed"
    assert count == 1
    assert saved.kills == 15
    assert saved.internal_rating_version == INTERNAL_RATING_VERSION
    assert player_row.bo3_rating == Decimal("7.4200")
    assert player_row.player_strength == 74

    stored_path = tmp_path / demo.storage_path
    stored_path.parent.mkdir(parents=True)
    stored_path.write_bytes(b"old")
    upload_result = await DemoStorageService(db_session, tmp_path, 100).upload(
        "Cup", "online", demo.match_date,
        [UploadFile(BytesIO(b"new"), filename="map.dem")],
    )
    assert upload_result.files[0].status == "replaced"
    assert await db_session.scalar(select(func.count(DemoPlayerStat.id))) == 0
    run = (await db_session.execute(select(DemoParseRun))).scalar_one()
    assert run.status == "pending"


async def test_parse_failure_is_not_masked_by_missing_greenlet(db_session, tmp_path) -> None:
    demo = DemoFile(
        tournament_name="Cup", tournament_slug="cup", match_date=__import__("datetime").date(2026, 2, 2),
        original_filename="broken.dem", storage_path="broken.dem", file_size_bytes=1, sha256="f" * 64,
    )
    db_session.add(demo)
    await db_session.commit()
    service = DemoParseService(db_session, tmp_path)

    class BrokenParser:
        parser_name = "test"
        parser_version = "1"

        def parse(self, path):
            raise RuntimeError("real parser failure")

    service.parser = BrokenParser()
    result, _ = await service.parse_one(demo, False)
    assert result.status == "failed"
    assert result.filename == "broken.dem"
    assert result.error == "real parser failure"
    run = (await db_session.execute(select(DemoParseRun))).scalar_one()
    assert run.error_message == "real parser failure"


async def test_batch_reloads_next_demo_after_previous_rollback(db_session, tmp_path) -> None:
    demos = [DemoFile(
        tournament_name="Cup", tournament_slug="cup", match_date=__import__("datetime").date(2026, 2, day),
        original_filename=name, storage_path=name, file_size_bytes=1, sha256=letter * 64,
    ) for day, name, letter in ((3, "broken.dem", "a"), (4, "good.dem", "b"))]
    db_session.add_all(demos)
    await db_session.commit()
    service = DemoParseService(db_session, tmp_path)

    class MixedParser:
        parser_name = "test"
        parser_version = "1"

        def parse(self, path):
            if path.name == "broken.dem":
                raise RuntimeError("first demo failed")
            return [ParsedDemoPlayerStat(
                steam_id="30", nickname="Good", team_name="Team",
                rounds_played=10, kills=10, deaths=5, assists=2,
                total_damage=800, adr=Decimal("80"), kast_rounds=7,
                kast_percent=Decimal("70"), internal_rating=Decimal("7"),
            )]

    service.parser = MixedParser()
    result = await service._parse_demos(
        demos, False, tournament_name="Cup", year=2026,
    )
    assert result.failed_count == 1
    assert result.parsed_count == 1
    assert [item.error for item in result.files] == ["first demo failed", None]


async def test_batch_parses_files_concurrently(db_session, tmp_path) -> None:
    import threading

    demos = [DemoFile(
        tournament_name="Cup", tournament_slug="cup",
        match_date=__import__("datetime").date(2026, 3, day),
        original_filename=f"parallel-{day}.dem", storage_path=f"parallel-{day}.dem",
        file_size_bytes=1, sha256=str(day) * 64,
    ) for day in (1, 2)]
    db_session.add_all(demos)
    await db_session.commit()
    service = DemoParseService(db_session, tmp_path, parse_concurrency=2)
    both_started = threading.Barrier(2, timeout=2)

    class ConcurrentParser:
        parser_name = "test"
        parser_version = "1"

        def parse(self, path):
            both_started.wait()
            identity = path.stem[-1]
            return [ParsedDemoPlayerStat(
                steam_id=identity, nickname=f"Player {identity}", team_name="Team",
                rounds_played=10, kills=10, deaths=5, assists=2,
                total_damage=800, adr=Decimal("80"), kast_rounds=7,
                kast_percent=Decimal("70"), internal_rating=Decimal("7"),
            )]

    service.parser = ConcurrentParser()
    result = await service._parse_demos(
        demos, False, tournament_name="Cup", year=2026,
    )

    assert result.parsed_count == 2
    assert result.failed_count == 0


async def test_parse_all_aborts_before_touching_runs_when_storage_is_missing(
    db_session, tmp_path,
) -> None:
    demo = DemoFile(
        tournament_name="Cup", tournament_slug="cup",
        match_date=__import__("datetime").date(2026, 2, 1),
        original_filename="missing.dem", storage_path="demos/missing.dem",
        file_size_bytes=1, sha256="d" * 64,
    )
    db_session.add(demo)
    await db_session.flush()
    run = DemoParseRun(
        demo_file_id=demo.id, status="success",
        parser_name="test", parser_version="1",
    )
    db_session.add(run)
    await db_session.commit()

    with pytest.raises(FileNotFoundError, match="Массовый парсинг не запущен"):
        await DemoParseService(db_session, tmp_path).parse_all()

    await db_session.refresh(run)
    assert run.status == "success"


async def test_parse_all_skips_intentionally_deleted_success(
    db_session, tmp_path,
) -> None:
    from datetime import UTC, datetime
    demo = DemoFile(
        tournament_name="Cup", tournament_slug="cup",
        match_date=__import__("datetime").date(2026, 2, 1),
        original_filename="cleaned.dem", storage_path="demos/cleaned.dem",
        file_size_bytes=123, sha256="e" * 64,
        source_deleted_at=datetime.now(UTC),
    )
    db_session.add(demo)
    await db_session.flush()
    db_session.add(DemoParseRun(
        demo_file_id=demo.id, status="success",
        parser_name="test", parser_version="1",
    ))
    await db_session.commit()

    result = await DemoParseService(db_session, tmp_path).parse_all()

    assert result.total_files == 0
    assert result.failed_count == 0


async def test_reparse_intentionally_deleted_source_preserves_results(
    db_session, tmp_path,
) -> None:
    from datetime import UTC, datetime
    demo = DemoFile(
        tournament_name="Cup", tournament_slug="cup",
        match_date=__import__("datetime").date(2026, 2, 1),
        original_filename="cleaned.dem", storage_path="demos/cleaned.dem",
        file_size_bytes=123, sha256="e" * 64,
        source_deleted_at=datetime.now(UTC),
    )
    db_session.add(demo)
    await db_session.flush()
    run = DemoParseRun(
        demo_file_id=demo.id, status="success",
        parser_name="test", parser_version="1",
    )
    db_session.add(run)
    await db_session.flush()
    db_session.add(DemoPlayerStat(
        demo_file_id=demo.id, parse_run_id=run.id,
        nickname="Saved", identity_key="saved",
        rounds_played=1, kills=1, deaths=0, assists=0, total_damage=100,
        adr=Decimal("100"), kast_rounds=1, kast_percent=Decimal("100"),
        internal_rating=Decimal("10"), internal_rating_version=INTERNAL_RATING_VERSION,
        opponent_rank_group="unknown", opponent_rank_source="unknown",
    ))
    await db_session.commit()

    result, _ = await DemoParseService(db_session, tmp_path).parse_one(demo, True)

    assert result.error == "source_demo_deleted_reupload_required"
    assert await db_session.scalar(select(func.count(DemoPlayerStat.id))) == 1
