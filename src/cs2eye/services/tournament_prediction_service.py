from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.models.match import Match, Tournament
from cs2eye.models.prediction import TournamentMatchPrediction, TournamentPredictionRun
from cs2eye.models.team import Team
from cs2eye.analytics.win_probability_config import MIN_PREDICTION_CONFIDENCE
from cs2eye.services.matchup_service import MatchupService
from cs2eye.services.win_probability_service import active_model, predict_win_probability


STAGE_ORDER = {"group": 0, "swiss": 0, "round_of_32": 1, "round_of_16": 2, "quarterfinal": 3, "semifinal": 4, "final": 5, "unknown": 0}
Predictor = Callable[..., Awaitable[dict]]
Comparator = Callable[..., Awaitable[dict]]


class TournamentPredictionError(ValueError):
    pass


class TournamentPredictionService:
    def __init__(self, session: AsyncSession, predictor: Predictor = predict_win_probability,
                 comparator: Comparator | None = None) -> None:
        self.session = session
        self.predictor = predictor
        self.comparator = comparator or MatchupService(session).calculate

    async def generate(self, tournament_id: int) -> TournamentPredictionRun:
        tournament = await self.session.get(Tournament, tournament_id)
        if tournament is None:
            raise TournamentPredictionError("Турнир не найден.")
        matches = list((await self.session.scalars(select(Match).where(
            Match.tournament_id == tournament_id,
        ).order_by(Match.round_number, Match.match_date, Match.bracket_position, Match.id))).all())
        if not matches:
            raise TournamentPredictionError("В турнире нет серий для прогнозирования.")
        by_id = {item.id: item for item in matches}
        transitions: set[tuple[int, str]] = set()
        for source in matches:
            if source.next_match_id is not None:
                if source.next_match_id not in by_id or source.next_match_slot not in {"team_a", "team_b"}:
                    raise TournamentPredictionError(
                        f"Для серии #{source.id} укажите корректные следующий матч и слот."
                    )
                transition = (source.next_match_id, source.next_match_slot)
                if transition in transitions:
                    raise TournamentPredictionError("Два матча не могут передавать победителя в один слот.")
                target = by_id[source.next_match_id]
                source_order = (source.round_number or 0, STAGE_ORDER.get(source.stage, 0))
                target_order = (target.round_number or 0, STAGE_ORDER.get(target.stage, 0))
                if target_order <= source_order:
                    raise TournamentPredictionError("Переход сетки должен вести в более позднюю playoff-стадию.")
                transitions.add(transition)
        artifact = await active_model(self.session)
        now = datetime.now(UTC)
        await self.session.execute(update(TournamentPredictionRun).where(
            TournamentPredictionRun.tournament_id == tournament_id,
            TournamentPredictionRun.outdated.is_(False),
        ).values(outdated=True))
        await self.session.execute(update(TournamentMatchPrediction).where(
            TournamentMatchPrediction.tournament_id == tournament_id,
            TournamentMatchPrediction.invalidated_at.is_(None),
        ).values(invalidated_at=now))
        run = TournamentPredictionRun(
            tournament_id=tournament_id, model_version=artifact.model_version if artifact else None,
            status="running", outdated=False,
            model_status=("experimental" if artifact.forced_active else "active") if artifact else None,
            quality_gate_passed=artifact.quality_gate_passed if artifact else None,
        )
        self.session.add(run)
        await self.session.flush()

        incoming: dict[tuple[int, str], int | None] = {}
        statuses: list[str] = []
        ordered = sorted(matches, key=lambda item: (
            item.round_number if item.round_number is not None else STAGE_ORDER.get(item.stage, 0),
            STAGE_ORDER.get(item.stage, 0), item.bracket_position or item.id,
        ))
        for match in ordered:
            team_a = match.team_a_id if match.team_a_id is not None else incoming.get((match.id, "team_a"))
            team_b = match.team_b_id if match.team_b_id is not None else incoming.get((match.id, "team_b"))
            projected = match.team_a_id is None or match.team_b_id is None
            status = "insufficient_data"
            winner: int | None = None
            probability_a = probability_b = score_a = score_b = confidence = reliability = None
            prediction_basis = "win_probability"
            model_version = artifact.model_version if artifact else None
            if match.status == "completed" and match.winner_team_id is not None:
                status = "actual_result"
            elif team_a is not None and team_b is not None:
                result = await self.predictor(
                    self.session, a=team_a, b=team_b, format=match.format if match.format in {"bo1", "bo3", "bo5"} else "bo3",
                    mode="pre_veto", series_id=None if projected else match.id,
                )
                status = result["prediction_status"]
                model_version = result.get("model_version")
                if run.model_version is None and model_version:
                    run.model_version = model_version
                if result.get("model_status"):
                    run.model_status = result["model_status"]
                    run.quality_gate_passed = result.get("quality_gate_passed")
                if status == "available":
                    probability_a = Decimal(str(result["team_a"]["probability"]))
                    probability_b = Decimal(str(result["team_b"]["probability"]))
                    confidence = Decimal(str(result.get("confidence", 0)))
                    reliability = confidence
                    winner = team_a if probability_a > probability_b else team_b if probability_b > probability_a else None
                elif status == "model_not_trained":
                    matchup = await self.comparator(
                        team_a, team_b,
                        match.format if match.format in {"bo1", "bo3", "bo5"} else "bo3",
                        "pre_veto", None, None if projected else match.id,
                    )
                    reliability_value = float(matchup.get("reliability", 0))
                    if matchup.get("status") != "insufficient_data" and reliability_value >= MIN_PREDICTION_CONFIDENCE:
                        score_a = Decimal(str(matchup["team_a"]["score"]))
                        score_b = Decimal(str(matchup["team_b"]["score"]))
                        confidence = reliability = Decimal(str(reliability_value))
                        winner = team_a if score_a > score_b else team_b if score_b > score_a else None
                        status = "comparison_fallback" if winner is not None else "insufficient_data"
                        model_version = matchup.get("model_version")
                        prediction_basis = "matchup_score"
                if run.model_version is None and model_version:
                    run.model_version = model_version
            prediction = TournamentMatchPrediction(
                prediction_run_id=run.id, tournament_id=tournament_id,
                source_match_id=None if projected else match.id,
                round_number=match.round_number, round_label=match.round_label, stage=match.stage,
                bracket_section=match.bracket_section, bracket_position=match.bracket_position,
                format=match.format, team_a_id=team_a, team_b_id=team_b,
                team_a_probability=probability_a, team_b_probability=probability_b,
                team_a_score=score_a, team_b_score=score_b,
                predicted_winner_id=winner, confidence=confidence, reliability=reliability,
                prediction_type="projected_match" if projected else "actual_match",
                prediction_basis=prediction_basis, status=status, model_version=model_version,
            )
            self.session.add(prediction)
            statuses.append(status)
            advancing = match.winner_team_id if match.status == "completed" and match.winner_team_id else winner
            if match.next_match_id is not None:
                incoming[(match.next_match_id, match.next_match_slot)] = advancing
        run.status = "succeeded" if statuses and all(value in {"available", "comparison_fallback", "actual_result"} for value in statuses) else "partial"
        await self.session.flush()
        return run

    async def latest(self, tournament_id: int) -> dict | None:
        run = (await self.session.scalars(select(TournamentPredictionRun).where(
            TournamentPredictionRun.tournament_id == tournament_id,
        ).order_by(TournamentPredictionRun.created_at.desc(), TournamentPredictionRun.id.desc()))).first()
        if run is None:
            return None
        rows = list((await self.session.scalars(select(TournamentMatchPrediction).where(
            TournamentMatchPrediction.prediction_run_id == run.id,
        ).order_by(TournamentMatchPrediction.round_number, TournamentMatchPrediction.stage,
                   TournamentMatchPrediction.bracket_position, TournamentMatchPrediction.id))).all())
        team_ids = {value for row in rows for value in (row.team_a_id, row.team_b_id, row.predicted_winner_id) if value is not None}
        teams = {team.id: team.name for team in (await self.session.scalars(select(Team).where(Team.id.in_(team_ids)))).all()} if team_ids else {}
        return {"tournament_id": tournament_id, "prediction_run_id": run.id, "generated_at": run.created_at,
                "model_version": run.model_version, "model_status": run.model_status,
                "quality_gate_passed": run.quality_gate_passed, "status": run.status, "outdated": run.outdated,
                "matches": [{"id": row.id, "source_match_id": row.source_match_id,
                    "round_number": row.round_number, "round_label": row.round_label, "stage": row.stage,
                    "bracket_section": row.bracket_section, "bracket_position": row.bracket_position, "format": row.format,
                    "team_a": {"id": row.team_a_id, "name": teams.get(row.team_a_id)},
                    "team_b": {"id": row.team_b_id, "name": teams.get(row.team_b_id)},
                    "team_a_probability": float(row.team_a_probability) if row.team_a_probability is not None else None,
                    "team_b_probability": float(row.team_b_probability) if row.team_b_probability is not None else None,
                    "team_a_score": float(row.team_a_score) if row.team_a_score is not None else None,
                    "team_b_score": float(row.team_b_score) if row.team_b_score is not None else None,
                    "predicted_winner_id": row.predicted_winner_id, "predicted_winner_name": teams.get(row.predicted_winner_id),
                    "confidence": float(row.confidence) if row.confidence is not None else None,
                    "reliability": float(row.reliability) if row.reliability is not None else None,
                    "prediction_type": row.prediction_type, "prediction_basis": row.prediction_basis,
                    "status": row.status, "model_version": row.model_version,
                    "created_at": row.created_at, "invalidated_at": row.invalidated_at} for row in rows]}


async def invalidate_tournament_predictions(session: AsyncSession, tournament_id: int | None) -> None:
    if tournament_id is None:
        return
    now = datetime.now(UTC)
    await session.execute(update(TournamentPredictionRun).where(
        TournamentPredictionRun.tournament_id == tournament_id,
        TournamentPredictionRun.outdated.is_(False),
    ).values(outdated=True))
    await session.execute(update(TournamentMatchPrediction).where(
        TournamentMatchPrediction.tournament_id == tournament_id,
        TournamentMatchPrediction.invalidated_at.is_(None),
    ).values(invalidated_at=now))
