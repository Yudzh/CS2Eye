"""Export local AI reports into Git; import them transactionally during release."""
import argparse
import asyncio
import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import DateTime, select, text

from cs2eye.api.schemas.match_analysis_context import MatchAnalysisContext
from cs2eye.api.schemas.match_explanation_plan_v2 import MatchExplanationPlanV2
from cs2eye.api.schemas.match_llm_analysis_v3 import MatchLLMAnalysisV3
from cs2eye.core.config import settings
from cs2eye.db.session import AsyncSessionLocal, engine
from cs2eye.models.ai_report_import import AIReportImport
from cs2eye.models.match import Match, Tournament
from cs2eye.models.match_llm_analysis_run import MatchLLMAnalysisRun as Run
from cs2eye.models.team import Team
from cs2eye.services.match_llm_analysis_run_service import _compatible_v2_plan_snapshot


SCHEMA = "cs2eye.ai_report.v1"
EXCLUDED = {"id", "source_run_id", "match_id", "tournament_id", "team_a_id", "team_b_id"}
FIELDS = {column.name for column in Run.__table__.columns} - EXCLUDED


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      default=lambda item: item.isoformat() if isinstance(item, (date, datetime)) else str(item))


def digest(document):
    return hashlib.sha256(canonical(document).encode()).hexdigest()


def validate(document):
    if document.get("schema") != SCHEMA or set(document["run"]) != FIELDS:
        raise ValueError("Unsupported or incomplete AI report artifact")
    UUID(document["origin"])
    run = document["run"]
    if run["status"] != "completed" or run["analysis_schema_version"] != "match_llm_analysis.v3":
        raise ValueError("Only completed v3 AI reports can be published")
    if not all(run[key] for key in ("schema_valid", "business_valid", "grounding_valid")):
        raise ValueError("AI report failed validation; refusing publication")
    MatchAnalysisContext.model_validate(run["context_snapshot"])
    MatchLLMAnalysisV3.model_validate(run["analysis_snapshot"])
    if run["explanation_plan_snapshot"] is not None:
        plan = _compatible_v2_plan_snapshot(run["explanation_plan_snapshot"], run["context_snapshot"])
        # Early v2 plans predate the two display-name fields. Validate a detached
        # compatible copy, while preserving the original archived JSON byte-for-byte.
        for side in ("team_a", "team_b"):
            plan["conclusion"].setdefault(f"{side}_name", run["context_snapshot"]["teams"][side]["name"])
        MatchExplanationPlanV2.model_validate(plan)
    for key in ("as_of", "created_at", "completed_at"):
        timestamp = datetime.fromisoformat(run[key])
        if timestamp.tzinfo is None:
            raise ValueError(f"Report timestamp {key} has no timezone")


async def export_run(session, run, directory=None):
    if run.status != "completed" or run.analysis_schema_version != "match_llm_analysis.v3":
        return None
    directory = Path(directory or settings.ai_report_export_dir)
    directory.mkdir(parents=True, exist_ok=True)
    origin_file = directory / ".origin"
    try:
        with origin_file.open("x") as file:
            file.write(str(uuid4()))
    except FileExistsError:
        pass
    match = await session.get(Match, run.match_id) if run.match_id is not None else None
    tournament_id = run.tournament_id or (match.tournament_id if match else None)
    tournament = await session.get(Tournament, tournament_id) if tournament_id is not None else None
    a, b = await session.get(Team, run.team_a_id), await session.get(Team, run.team_b_id)
    if (match is not None and tournament is None) or a is None or b is None:
        raise ValueError("Cannot publish AI report without identified tournament and teams")
    document = json.loads(canonical({
        "schema": SCHEMA, "origin": origin_file.read_text().strip(),
        "source_run_id": run.id, "source_parent_id": run.source_run_id,
        "tournament": {"name": tournament.name, "year": tournament.year} if tournament else None,
        "team_a": {"bo3_id": a.bo3_id, "name": a.name},
        "team_b": {"bo3_id": b.bo3_id, "name": b.name},
        "match": {"date": match.match_date, "format": match.format, "round_number": match.round_number} if match else None,
        "run": {key: getattr(run, key) for key in FIELDS},
    }))
    validate(document)
    key = digest(document)
    target = directory / f"{key}.json"
    if not target.exists():
        temporary = directory / f".{key}.{uuid4().hex}.tmp"
        temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
        temporary.replace(target)
    return target


async def import_reports(session, directory=None):
    directory = Path(directory or settings.ai_report_export_dir)
    if not directory.is_dir():
        raise ValueError(f"AI report release directory missing: {directory}")
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(text("SELECT pg_advisory_xact_lock(2026, 8052)"))
    documents = []
    # Validate every file before importing any of them.
    for path in sorted(directory.glob("*.json")):
        document = json.loads(path.read_text())
        validate(document)
        key = digest(document)
        if path.stem != key:
            raise ValueError(f"AI report content does not match filename: {path.name}")
        documents.append((key, document))
    report = {"files": len(documents), "imported": 0, "existing": 0}
    for key, document in documents:
        if await session.get(AIReportImport, key) is not None:
            report["existing"] += 1
            continue
        previous = await session.scalar(select(AIReportImport).where(
            AIReportImport.source_origin == document["origin"],
            AIReportImport.source_run_id == document["source_run_id"]))
        if previous is not None:
            raise ValueError("A published AI report was modified; generate a new version instead")
        event = document["tournament"]
        tournament = ((await session.scalars(select(Tournament).where(
            Tournament.name == event["name"], Tournament.year == event["year"]))).one_or_none() if event else None)
        a = (await session.scalars(select(Team).where(Team.bo3_id == document["team_a"]["bo3_id"]))).one_or_none()
        b = (await session.scalars(select(Team).where(Team.bo3_id == document["team_b"]["bo3_id"]))).one_or_none()
        if (event and tournament is None) or a is None or b is None:
            raise ValueError(f"Missing server tournament or teams for report {key}")
        identity = document["match"]
        match = None
        if identity is not None:
            if tournament is None:
                raise ValueError("Match report has no tournament identity")
            query = select(Match).where(Match.tournament_id == tournament.id,
                Match.team_a_id == a.id, Match.team_b_id == b.id,
                Match.match_date == date.fromisoformat(identity["date"]), Match.format == identity["format"])
            if identity["round_number"] is not None:
                query = query.where(Match.round_number == identity["round_number"])
            matches = list((await session.scalars(query)).all())
            if len(matches) != 1:
                raise ValueError(f"Expected exactly one server match for AI report {key}; found {len(matches)}")
            match = matches[0]
        match_id = match.id if match else None
        values = document["run"].copy()
        for column in Run.__table__.columns:
            if column.name in values and values[column.name] is not None and isinstance(column.type, DateTime):
                values[column.name] = datetime.fromisoformat(values[column.name])
        # Reconcile reports already included in the original database migration.
        candidates = (await session.scalars(select(Run).where(Run.match_id == match_id,
            Run.team_a_id == a.id, Run.team_b_id == b.id, Run.created_at == values["created_at"],
            Run.model == values["model"], Run.prompt_version == values["prompt_version"]))).all()
        existing = next((row for row in candidates if row.context_snapshot == values["context_snapshot"]
                         and row.analysis_snapshot == values["analysis_snapshot"]), None)
        if candidates and existing is None:
            raise ValueError("A server report with the same identity has different content")
        if existing is None:
            existing = Run(match_id=match_id, tournament_id=tournament.id if tournament else None,
                           team_a_id=a.id, team_b_id=b.id, **values)
            session.add(existing)
            await session.flush()
            report["imported"] += 1
        else:
            report["existing"] += 1
        session.add(AIReportImport(digest=key, source_origin=document["origin"],
            source_run_id=document["source_run_id"], report_run_id=existing.id))
        await session.flush()
    # Restore lineage using source identities, never local numeric IDs as server IDs.
    for key, document in documents:
        if document["source_parent_id"] is not None:
            parent = await session.scalar(select(AIReportImport).where(
                AIReportImport.source_origin == document["origin"],
                AIReportImport.source_run_id == document["source_parent_id"]))
            imported = await session.get(AIReportImport, key)
            row = await session.get(Run, imported.report_run_id)
            if parent is not None and row.source_run_id is None:
                row.source_run_id = parent.report_run_id
    await session.flush()
    return report


async def main(action):
    try:
        async with AsyncSessionLocal() as session:
            if action == "export":
                rows = (await session.scalars(select(Run).where(Run.status == "completed",
                    Run.analysis_schema_version == "match_llm_analysis.v3"))).all()
                exported = [await export_run(session, row) for row in rows]
                print(f"AI reports prepared for release: {len(exported)}")
            else:
                result = await import_reports(session)
                await session.commit()
                print("AI report import: " + json.dumps(result))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["export", "import"])
    asyncio.run(main(parser.parse_args().action))
