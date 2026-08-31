from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from cs2eye.api.schemas.match_analysis_context import MatchAnalysisContext
from cs2eye.db.base import Base
from cs2eye.db.session import get_db_session
from cs2eye.main import create_app
from cs2eye.models.match import Match, Tournament
from cs2eye.models.team import (
    AnalystFactor,
    Player,
    Team,
    TeamRoster,
    TeamRosterMember,
)
from cs2eye.services.form_context_service import FormContextService
from cs2eye.services.match_analysis_context_builder import (
    MAX_KEY_EDGES,
    MAX_TOTAL_EVIDENCE,
    MatchAnalysisContextBuilder,
    edge_strength,
)
from tests.test_match_analysis_context import nullable_context_payload


TODAY = date.today()
AS_OF = datetime.combine(TODAY, datetime.min.time(), tzinfo=UTC)


@pytest.fixture
async def builder_db() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


async def seed_context(factory: async_sessionmaker[AsyncSession]) -> dict[str, int]:
    async with factory() as session:
        a = Team(id=1, bo3_id=101, bo3_slug="alpha", name="Alpha", current_rank=4, ranking_date=TODAY)
        b = Team(id=2, bo3_id=102, bo3_slug="bravo", name="Bravo", current_rank=9, ranking_date=TODAY)
        c = Team(id=3, bo3_id=103, bo3_slug="charlie", name="Charlie", current_rank=2, ranking_date=TODAY)
        tournament = Tournament(
            id=1, name="Current Cup", year=TODAY.year, tier="S", environment="lan",
            start_date=TODAY - timedelta(days=3), end_date=TODAY + timedelta(days=3),
            structure_type="single_elimination",
        )
        other = Tournament(
            id=2, name="Other Cup", year=TODAY.year, environment="online",
            structure_type="unknown",
        )
        session.add_all([a, b, c, tournament, other])
        await session.flush()
        ra = TeamRoster(
            team_id=1, fingerprint="a" * 64, is_current=True,
            active_from=TODAY - timedelta(days=30), source="manual", resolution_status="complete",
        )
        rb = TeamRoster(
            team_id=2, fingerprint="b" * 64, is_current=True,
            active_from=TODAY - timedelta(days=30), source="manual", resolution_status="complete",
        )
        session.add_all([ra, rb]); await session.flush()
        a.current_roster_id, b.current_roster_id = ra.id, rb.id
        pa = Player(id=11, bo3_id=201, bo3_slug="a-player", nickname="a-player", player_strength=80)
        pb = Player(id=12, bo3_id=202, bo3_slug="b-player", nickname="b-player", player_strength=70)
        session.add_all([pa, pb]); await session.flush()
        session.add_all([
            TeamRosterMember(roster_id=ra.id, player_id=pa.id, player_name_snapshot=pa.nickname, role_snapshot="rifler"),
            TeamRosterMember(roster_id=rb.id, player_id=pb.id, player_name_snapshot=pb.nickname, role_snapshot="awper"),
        ])
        history = Match(
            id=10, tournament_id=1, match_date=TODAY - timedelta(days=1),
            team_a_id=1, team_b_id=2, format="bo3", stage="quarterfinal",
            environment="lan", status="completed", resolution_status="resolved",
            team_a_maps_won=2, team_b_maps_won=1, winner_team_id=1,
        )
        target = Match(
            id=20, tournament_id=1, match_date=TODAY + timedelta(days=1),
            team_a_id=1, team_b_id=2, format="bo3", stage="semifinal",
            environment="lan", status="scheduled", resolution_status="resolved",
            is_playoff=True, is_elimination=True, round_number=2,
            round_label="Semifinal", bracket_section="main",
        )
        session.add_all([history, target])
        note = AnalystFactor(
            id=1, team_id=1, factor_type="positive", text="Prepared LAN roster.",
            category="roster", environment="lan", is_active=True,
            created_at=AS_OF - timedelta(days=1),
        )
        session.add(note)
        await session.commit()
        return {"roster_a": ra.id, "roster_b": rb.id}


def matchup_payload() -> dict:
    form = {
        "tournament_form_score": 70.0, "tournament_matches_count": 1,
        "tournament_reliability": .4, "recent_60d_adjusted_form_score": 68.0,
        "recent_60d_matches_count": 4, "recent_60d_reliability": .7,
        "strength_of_schedule_score": 65.0,
        "performance_vs_expectation_score": 58.0,
        "top5_matches_60d": 1, "top10_matches_60d": 2, "top30_matches_60d": 4,
    }
    return {
        "model_version": "matchup_v1",
        "team_a": {"id": 1, "name": "Alpha", "score": 54.0},
        "team_b": {"id": 2, "name": "Bravo", "score": 46.0},
        "reliability": .8,
        "confidence_level": "high",
        "factors": [{"key": "form_context", "score": 54.0, "confidence": .8, "sample": None}],
        "form_context": {"team_a_form_context": form, "team_b_form_context": form},
        "limitations": [],
    }


def fake_h2h() -> SimpleNamespace:
    metrics_a = SimpleNamespace(maps_won=3, h2h_rating=56.0, performance_score=58.0)
    metrics_b = SimpleNamespace(maps_won=2, h2h_rating=44.0, performance_score=42.0)
    org = SimpleNamespace(
        status="available", series_played=3, maps_played=5,
        team_a_series_won=2, team_b_series_won=1, team_a=metrics_a, team_b=metrics_b,
        confidence_score=70.0,
    )
    current = SimpleNamespace(
        status="current_rosters_never_met", series_played=0, maps_played=0,
        team_a_series_won=0, team_b_series_won=0,
        team_a=SimpleNamespace(maps_won=0, h2h_rating=None, performance_score=None),
        team_b=SimpleNamespace(maps_won=0, h2h_rating=None, performance_score=None),
        confidence_score=0.0,
    )
    return SimpleNamespace(
        organizations=org, current_rosters=current,
        roster_context=SimpleNamespace(history_applicability="low"),
    )


def install_full_service_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    import cs2eye.services.match_analysis_context_builder as module

    matchup = matchup_payload()

    async def prediction(*args, **kwargs):
        return {
            "prediction_status": "available", "model_version": "wp-v1",
            "quality_gate_passed": True,
            "team_a": {"probability": .57}, "team_b": {"probability": .43},
            "confidence": .8,
            "explanation": {"top_factors": [{
                "key": "team_strength_difference", "favors": "team_a",
                "impact_percentage_points": 4.2,
            }]},
            "matchup": matchup,
        }

    factor = SimpleNamespace(
        key="roster_quality", available=True, impact=4.0,
        normalized_score=70.0, confidence=.8, sample_size=5,
    )
    stability = SimpleNamespace(
        key="roster_stability", available=True, impact=2.0,
        normalized_score=75.0, confidence=.7, sample_size=12,
    )
    strength = SimpleNamespace(final_score=72.0, reliability=.8, factors=[factor, stability])

    class Comparison:
        def __init__(self, session, now=None): pass
        async def compare(self, a, b):
            return SimpleNamespace(
                team_a=SimpleNamespace(strength=strength),
                team_b=SimpleNamespace(strength=strength),
            )

    class Leadership:
        def __init__(self, session): pass
        async def team(self, team_id):
            return {
                "igl": {"score": 70.0, "reliability": .7, "sample": {"maps": 12}},
                "coach": {"score": 65.0, "reliability": .6, "sample": {"maps": 12}},
            }

    class Veto:
        def __init__(self, session, today=None): pass
        async def calculate(self, *args, **kwargs):
            return {
                "calculated_veto_model_version": "veto-v2",
                "maps": [{
                    "map": "mirage", "series_map_probability": .9, "confidence": .8,
                    "pick_by_team_a_probability": .7, "pick_by_team_b_probability": .1,
                    "decider_probability": .1,
                }],
            }

    class H2H:
        def __init__(self, session, today=None): pass
        async def compare(self, *args, **kwargs): return fake_h2h()

    async def compact_maps(self, *args, **kwargs):
        return [{
            "map": "mirage", "relevance": .9,
            "team_a": {"map_strength": 72.0, "reliability": .8, "sample_maps": 10},
            "team_b": {"map_strength": 66.0, "reliability": .75, "sample_maps": 8},
            "matchup_score_team_a": 55.0, "key_edges": [],
        }]

    monkeypatch.setattr(module, "predict_win_probability", prediction)
    monkeypatch.setattr(module, "TeamComparisonService", Comparison)
    monkeypatch.setattr(module, "LeadershipService", Leadership)
    monkeypatch.setattr(module, "CalculatedVetoService", Veto)
    monkeypatch.setattr(module, "TeamH2HService", H2H)
    monkeypatch.setattr(MatchAnalysisContextBuilder, "_map_matchups", compact_maps)


async def test_builder_creates_fully_populated_context(builder_db, monkeypatch) -> None:
    await seed_context(builder_db)
    install_full_service_fakes(monkeypatch)
    async with builder_db() as session:
        result = await MatchAnalysisContextBuilder(session).build(1, 2, as_of=AS_OF, match_id=20)
    assert isinstance(result, MatchAnalysisContext)
    assert result.match.id == 20
    assert result.prediction.team_a_probability == .57
    assert result.matchup.confidence_level == "high"
    assert result.matchup.factors[0].sample_size is None
    assert result.veto.source_type == "deterministic_analytics"
    assert result.veto.basis == "calculated_veto"
    assert result.map_matchups[0].map == "mirage"
    assert result.manual_context.team_a[0].text == "Prepared LAN roster."
    assert len(result.secondary_bets.he_kill_by_map) == 7
    assert all(item.confidence == "low" for item in result.secondary_bets.he_kill_by_map)
    assert result.betting_restrictions.restricted is False


async def test_navi_rule_does_not_change_prediction_or_matchup(builder_db, monkeypatch) -> None:
    await seed_context(builder_db)
    install_full_service_fakes(monkeypatch)
    async with builder_db() as session:
        team = await session.get(Team, 1)
        team.bo3_id = 787
        team.bo3_slug = "natus-vincere"
        await session.commit()
        result = await MatchAnalysisContextBuilder(session).build(1, 2, as_of=AS_OF, match_id=20)
    assert result.betting_restrictions.restricted is True
    assert result.betting_restrictions.rule == "navi_no_match_winner_bets"
    assert result.prediction.team_a_probability == .57
    assert result.matchup.team_a_score == 54.0


async def test_builder_without_match_keeps_match_specific_fields_null(builder_db, monkeypatch) -> None:
    await seed_context(builder_db)
    import cs2eye.services.match_analysis_context_builder as module
    class H2H:
        def __init__(self, session, today=None): pass
        async def compare(self, *args, **kwargs): return fake_h2h()
    monkeypatch.setattr(module, "TeamH2HService", H2H)
    async with builder_db() as session:
        result = await MatchAnalysisContextBuilder(session).build(
            1, 2, as_of=AS_OF - timedelta(days=1),
        )
    assert result.match.id is None
    assert result.match.format is None
    assert result.match.tournament.id is None
    assert result.prediction.status == "not_available"
    assert result.prediction.team_a_probability is None
    assert result.matchup.confidence_level is None


async def add_evidence_matches(factory, *, count: int = 12) -> None:
    async with factory() as session:
        for index in range(count):
            session.add(Match(
                id=100 + index,
                tournament_id=1 if index < 6 else 2,
                match_date=TODAY - timedelta(days=index + 1),
                team_a_id=1, team_b_id=3, format="bo3", stage="group",
                environment="lan", status="completed", resolution_status="resolved",
                team_a_maps_won=2 if index % 2 == 0 else 0,
                team_b_maps_won=0 if index % 2 == 0 else 2,
                winner_team_id=1 if index % 2 == 0 else 3,
            ))
        session.add(Match(
            id=999, tournament_id=1, match_date=TODAY + timedelta(days=1),
            team_a_id=1, team_b_id=3, format="bo3", stage="group",
            environment="lan", status="completed", resolution_status="resolved",
            team_a_maps_won=2, team_b_maps_won=0, winner_team_id=1,
        ))
        await session.commit()


async def test_recent_evidence_is_temporal_safe_and_limited(builder_db) -> None:
    await seed_context(builder_db); await add_evidence_matches(builder_db)
    async with builder_db() as session:
        rows = await FormContextService(session).recent_series_evidence(
            1, as_of=TODAY, tournament_id=1,
        )
    assert len(rows) <= MAX_TOTAL_EVIDENCE
    assert all(row["date"] < TODAY for row in rows)
    assert "series:999" not in {row["evidence_id"] for row in rows}


async def test_analyzed_match_is_excluded_from_evidence(builder_db) -> None:
    await seed_context(builder_db)
    async with builder_db() as session:
        rows = await FormContextService(session).recent_series_evidence(
            1, as_of=TODAY + timedelta(days=2), tournament_id=1, exclude_match_id=20,
        )
    assert "series:20" not in {row["evidence_id"] for row in rows}


async def test_current_tournament_has_evidence_priority(builder_db) -> None:
    await seed_context(builder_db); await add_evidence_matches(builder_db)
    async with builder_db() as session:
        rows = await FormContextService(session).recent_series_evidence(
            1, as_of=TODAY, tournament_id=1,
        )
    current = [row for row in rows if row["current_tournament"]]
    assert current
    assert rows[:len(current)] == current
    assert len(current) <= 5


async def test_large_performance_delta_is_selected(builder_db) -> None:
    await seed_context(builder_db); await add_evidence_matches(builder_db, count=12)
    async with builder_db() as session:
        rows = await FormContextService(session).recent_series_evidence(
            1, as_of=TODAY, tournament_id=None, other_limit=5,
        )
    deltas = [abs(row["performance_vs_expectation"]) for row in rows]
    assert deltas
    assert max(deltas) >= .4


def test_ml_unavailable_does_not_create_fifty_fifty() -> None:
    result = MatchAnalysisContextBuilder._prediction_context({
        "prediction_status": "model_not_trained", "model_version": None,
        "quality_gate_passed": False, "team_a": {"probability": None},
        "team_b": {"probability": None}, "confidence": 0,
    })
    assert result["team_a_probability"] is None
    assert result["team_b_probability"] is None


def test_h2h_scopes_remain_independent() -> None:
    result = MatchAnalysisContextBuilder._h2h_context(fake_h2h(), historical=False)
    assert result["organizations"]["maps_played"] == 5
    assert result["current_rosters"]["maps_played"] == 0
    assert result["organizations"]["team_a_rating"] == 56.0
    assert result["current_rosters"]["team_a_rating"] is None


async def test_manual_notes_are_filtered_by_as_of(builder_db) -> None:
    await seed_context(builder_db)
    async with builder_db() as session:
        session.add(AnalystFactor(
            id=2, team_id=1, factor_type="negative", text="Future note",
            category="form", environment="lan", is_active=True,
            created_at=AS_OF + timedelta(days=1),
        )); await session.commit()
        notes = await MatchAnalysisContextBuilder(session)._manual_notes(
            1, AS_OF, [], "lan", set(),
        )
    assert [note["text"] for note in notes] == ["Prepared LAN roster."]


def aggregate(**overrides):
    defaults = dict(
        ct_win_rate=.55, t_win_rate=.50, postplant_win_rate=.55, retake_win_rate=.50,
        combat_data={}, economy_data={}, utility_data={}, maps_played=10,
    )
    return SimpleNamespace(**{**defaults, **overrides})


def test_key_edges_are_compact_and_have_no_raw_payload() -> None:
    a = aggregate(
        ct_win_rate=.75, t_win_rate=.70, postplant_win_rate=.75, retake_win_rate=.70,
        combat_data={"opening": {"conversion_rate": .75}, "trade": {"trade_rate": .70}, "clutch": {"win_rate": .70}},
        economy_data={"pistol": {"win_rate": .70}, "force_vs_full_buy": {"win_rate": .70}, "full_buy_vs_full_buy": {"win_rate": .70}, "anti_eco": {"win_rate": .70}},
        utility_data={"impact": {"score": .70}},
    )
    b = aggregate()
    edges = MatchAnalysisContextBuilder._key_edges(
        "mirage", a, b, SimpleNamespace(reliability=.8), SimpleNamespace(reliability=.7),
    )
    assert len(edges) <= MAX_KEY_EDGES
    assert all(set(edge) == {"evidence_id", "metric", "favored_team", "strength", "reliability"} for edge in edges)


@pytest.mark.parametrize(("difference", "expected"), [
    (4.99, None), (5, "small"), (10, "moderate"), (20, "clear"),
])
def test_key_edge_thresholds(difference: float, expected: str | None) -> None:
    assert edge_strength(difference) == expected


def test_data_quality_rules_report_missing_data() -> None:
    result = MatchAnalysisContextBuilder._data_quality(
        ["prediction", "matchup", "teams.team_a.roster"], ["No H2H"], ["Historical snapshot excluded"],
    )
    assert result["overall_status"] == "insufficient"
    assert "prediction" in result["missing_sections"]


def test_data_quality_available_when_no_issues() -> None:
    assert MatchAnalysisContextBuilder._data_quality([], [], [])["overall_status"] == "available"


async def test_endpoint_returns_match_analysis_context_v1(builder_db, monkeypatch) -> None:
    context = MatchAnalysisContext.model_validate(nullable_context_payload())
    async def build(self, *args, **kwargs): return context
    monkeypatch.setattr(MatchAnalysisContextBuilder, "build", build)
    app = create_app()
    async def override():
        async with builder_db() as session: yield session
    app.dependency_overrides[get_db_session] = override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/analysis/match-analysis-context",
            params={"team_a_id": 1, "team_b_id": 2, "as_of": AS_OF.isoformat()},
        )
    assert response.status_code == 200
    assert response.json()["schema_version"] == "match_analysis_context.v1"
