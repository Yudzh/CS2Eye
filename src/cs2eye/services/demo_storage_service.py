from __future__ import annotations

import hashlib
import os
import re
import tempfile
import unicodedata
import zipfile
from collections import defaultdict
from datetime import date, datetime, UTC
from pathlib import Path, PurePosixPath

import rarfile
from fastapi import UploadFile
from sqlalchemy import delete, extract, select
from sqlalchemy.ext.asyncio import AsyncSession

from cs2eye.api.schemas.demos import (
    DemoDateGroup, DemoListFile, DemoListResponse, DemoTournamentOption,
    DemoUploadFileResult, DemoUploadResponse,
)
from cs2eye.models.demo_file import DemoFile
from cs2eye.models.demo import DemoParseRun, DemoPlayerStat
from cs2eye.services.player_internal_rating_service import recalculate_player_internal_rating


CHUNK_SIZE = 1024 * 1024
ARCHIVE_SUFFIXES = {".zip", ".rar"}


def make_tournament_slug(value: str) -> str:
    """Turn a tournament display name into a stable, path-safe slug."""
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value)
    return re.sub(r"-+", "-", slug).strip("-")


def validate_demo_filename(filename: str | None) -> str:
    if not filename:
        raise ValueError("A filename is required.")
    if "/" in filename or "\\" in filename or filename in {".", ".."}:
        raise ValueError("Invalid demo filename.")
    if Path(filename).name != filename or ".." in Path(filename).parts:
        raise ValueError("Invalid demo filename.")
    if Path(filename).suffix.lower() != ".dem":
        raise ValueError("Only .dem files are supported.")
    return filename


def archive_member_basename(filename: str) -> str:
    """Return a member basename without ever trusting its directory path."""
    return PurePosixPath(filename.replace("\\", "/")).name


class DemoStorageService:
    def __init__(
        self, session: AsyncSession, storage_root: str | Path,
        max_file_size_bytes: int, archive_max_depth: int = 5,
    ) -> None:
        self.session = session
        self.storage_root = Path(storage_root)
        self.max_file_size_bytes = max_file_size_bytes
        self.archive_max_depth = archive_max_depth

    async def upload(
        self, tournament_name: str, match_date: date, files: list[UploadFile],
    ) -> DemoUploadResponse:
        name = tournament_name
        slug = make_tournament_slug(name)
        results: list[DemoUploadFileResult] = []
        for upload in files:
            filename = upload.filename or ""
            if Path(filename).suffix.lower() in ARCHIVE_SUFFIXES:
                results.extend(
                    await self._upload_archive(name, slug, match_date, upload, 1),
                )
            else:
                results.append(await self._upload_one(name, slug, match_date, upload))
        counts = {status: sum(item.status == status for item in results) for status in (
            "created", "replaced", "unchanged", "failed",
        )}
        return DemoUploadResponse(
            tournament_name=name, tournament_slug=slug, match_date=match_date,
            total_files=len(results), created_count=counts["created"],
            replaced_count=counts["replaced"], unchanged_count=counts["unchanged"],
            failed_count=counts["failed"], files=results,
        )

    async def _upload_archive(
        self, tournament_name: str, slug: str, match_date: date,
        upload: UploadFile, depth: int,
    ) -> list[DemoUploadFileResult]:
        archive_name = upload.filename or "archive"
        archive_suffix = Path(archive_name).suffix.lower()
        if depth > self.archive_max_depth:
            await upload.close()
            return [DemoUploadFileResult(
                filename=archive_name, status="failed",
                error="Archive nesting depth limit exceeded.",
            )]
        results: list[DemoUploadFileResult] = []
        try:
            await upload.seek(0)
            archive_factory = (
                zipfile.ZipFile if archive_suffix == ".zip" else rarfile.RarFile
            )
            with archive_factory(upload.file) as archive:
                for member in archive.infolist():
                    if member.is_dir():
                        continue
                    basename = archive_member_basename(member.filename)
                    suffix = Path(basename).suffix.lower()
                    if suffix != ".dem" and suffix not in ARCHIVE_SUFFIXES:
                        continue
                    is_encrypted = (
                        bool(member.flag_bits & 0x1)
                        if isinstance(member, zipfile.ZipInfo)
                        else member.needs_password()
                    )
                    if is_encrypted:
                        results.append(DemoUploadFileResult(
                            filename=basename or member.filename, status="failed",
                            error="Encrypted archive members are not supported.",
                        ))
                        continue
                    if member.file_size > self.max_file_size_bytes:
                        results.append(DemoUploadFileResult(
                            filename=basename or member.filename, status="failed",
                            error="Archive member exceeds the configured size limit.",
                        ))
                        continue
                    if suffix == ".dem":
                        member_file = archive.open(member)
                        results.append(await self._upload_one(
                            tournament_name, slug, match_date,
                            UploadFile(member_file, filename=basename),
                        ))
                        continue
                    nested_file = tempfile.SpooledTemporaryFile(
                        max_size=min(self.max_file_size_bytes, 8 * 1024 * 1024),
                    )
                    try:
                        with archive.open(member) as source:
                            copied = 0
                            while chunk := source.read(CHUNK_SIZE):
                                copied += len(chunk)
                                if copied > self.max_file_size_bytes:
                                    raise ValueError(
                                        "Nested archive exceeds the configured size limit.",
                                    )
                                nested_file.write(chunk)
                        nested_file.seek(0)
                        results.extend(await self._upload_archive(
                            tournament_name, slug, match_date,
                            UploadFile(nested_file, filename=basename), depth + 1,
                        ))
                    except Exception:
                        nested_file.close()
                        raise
        except (zipfile.BadZipFile, rarfile.Error, OSError, ValueError) as error:
            results.append(DemoUploadFileResult(
                filename=archive_name, status="failed",
                error=f"Cannot read {archive_suffix.upper()} archive: {error}",
            ))
        finally:
            await upload.close()
        if not results:
            results.append(DemoUploadFileResult(
                filename=archive_name, status="failed",
                error="The archive contains no supported .dem files.",
            ))
        return results

    async def _upload_one(
        self, tournament_name: str, slug: str, match_date: date, upload: UploadFile,
    ) -> DemoUploadFileResult:
        filename = upload.filename or ""
        temp_path: Path | None = None
        backup_path: Path | None = None
        final_path: Path | None = None
        moved_to_final = False
        try:
            filename = validate_demo_filename(upload.filename)
            relative_path = Path(
                "demos", "tournaments", slug, str(match_date.year),
                match_date.isoformat(), filename,
            )
            final_path = self.storage_root / relative_path
            final_path.parent.mkdir(parents=True, exist_ok=True)
            descriptor, raw_temp_path = tempfile.mkstemp(
                prefix=f".{filename}.", suffix=".upload", dir=final_path.parent,
            )
            temp_path = Path(raw_temp_path)
            digest = hashlib.sha256()
            size = 0
            with os.fdopen(descriptor, "wb") as output:
                while chunk := await upload.read(CHUNK_SIZE):
                    size += len(chunk)
                    if size > self.max_file_size_bytes:
                        raise ValueError("Demo file exceeds the configured size limit.")
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            if size == 0:
                raise ValueError("Demo file must not be empty.")
            sha256 = digest.hexdigest()
            existing = (
                await self.session.execute(select(DemoFile).where(
                    DemoFile.tournament_slug == slug,
                    DemoFile.match_date == match_date,
                    DemoFile.original_filename == filename,
                ))
            ).scalar_one_or_none()
            if existing and existing.sha256 == sha256 and final_path.is_file():
                temp_path.unlink(missing_ok=True)
                return self._result(existing, "unchanged")

            status = "replaced" if existing else "created"
            if final_path.is_file():
                backup_descriptor, raw_backup_path = tempfile.mkstemp(
                    prefix=f".{filename}.", suffix=".backup", dir=final_path.parent,
                )
                os.close(backup_descriptor)
                backup_path = Path(raw_backup_path)
                backup_path.unlink()
                os.link(final_path, backup_path)
            os.replace(temp_path, final_path)
            temp_path = None
            moved_to_final = True
            now = datetime.now(UTC)
            invalidated_player_ids: set[int] = set()
            if existing:
                invalidated_player_ids = set((
                    await self.session.execute(select(DemoPlayerStat.player_id).where(
                        DemoPlayerStat.demo_file_id == existing.id,
                        DemoPlayerStat.player_id.is_not(None),
                    ))
                ).scalars().all())
                await self.session.execute(delete(DemoPlayerStat).where(
                    DemoPlayerStat.demo_file_id == existing.id,
                ))
                parse_run = (
                    await self.session.execute(select(DemoParseRun).where(
                        DemoParseRun.demo_file_id == existing.id,
                    ))
                ).scalar_one_or_none()
                if parse_run is not None:
                    parse_run.status = "pending"
                    parse_run.error_message = None
                    parse_run.finished_at = None
                existing.tournament_name = tournament_name
                existing.storage_path = relative_path.as_posix()
                existing.file_size_bytes = size
                existing.sha256 = sha256
                existing.updated_at = now
                record = existing
            else:
                record = DemoFile(
                    tournament_name=tournament_name, tournament_slug=slug,
                    match_date=match_date, original_filename=filename,
                    storage_path=relative_path.as_posix(), file_size_bytes=size,
                    sha256=sha256, uploaded_at=now, updated_at=now,
                )
                self.session.add(record)
            for player_id in invalidated_player_ids:
                await recalculate_player_internal_rating(
                    self.session, player_id, commit=False,
                )
            await self.session.commit()
            await self.session.refresh(record)
            if backup_path is not None:
                backup_path.unlink(missing_ok=True)
                backup_path = None
            return self._result(record, status)
        except Exception as error:
            await self.session.rollback()
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            if moved_to_final and final_path is not None:
                if backup_path is not None:
                    os.replace(backup_path, final_path)
                    backup_path = None
                else:
                    final_path.unlink(missing_ok=True)
            if backup_path is not None:
                backup_path.unlink(missing_ok=True)
            return DemoUploadFileResult(
                filename=filename, status="failed", error=str(error) or "Upload failed.",
            )
        finally:
            await upload.close()

    @staticmethod
    def _result(record: DemoFile, status: str) -> DemoUploadFileResult:
        return DemoUploadFileResult(
            id=record.id, filename=record.original_filename, status=status,
            storage_path=record.storage_path, file_size_bytes=record.file_size_bytes,
            sha256=record.sha256,
        )

    async def list(self, tournament_name: str, year: int) -> DemoListResponse:
        name = tournament_name
        slug = make_tournament_slug(name)
        records = (
            await self.session.execute(
                select(DemoFile).where(
                    DemoFile.tournament_slug == slug,
                    extract("year", DemoFile.match_date) == year,
                ).order_by(DemoFile.match_date.desc(), DemoFile.original_filename.asc())
            )
        ).scalars().all()
        groups: dict[date, list[DemoListFile]] = defaultdict(list)
        parse_statuses = {
            demo_file_id: status for demo_file_id, status in (
                await self.session.execute(select(
                    DemoParseRun.demo_file_id, DemoParseRun.status,
                ).where(DemoParseRun.demo_file_id.in_([item.id for item in records])))
            ).all()
        } if records else {}
        for record in records:
            groups[record.match_date].append(DemoListFile(
                id=record.id, filename=record.original_filename,
                storage_path=record.storage_path, file_size_bytes=record.file_size_bytes,
                sha256=record.sha256, uploaded_at=record.uploaded_at,
                updated_at=record.updated_at,
                parse_status=parse_statuses.get(record.id, "pending"),
            ))
        dates = [DemoDateGroup(match_date=day, files=groups[day]) for day in sorted(groups, reverse=True)]
        display_name = records[0].tournament_name if records else name
        return DemoListResponse(
            tournament_name=display_name, tournament_slug=slug, year=year,
            total_files=len(records), dates=dates,
        )

    async def list_tournaments(self) -> list[DemoTournamentOption]:
        rows = (
            await self.session.execute(select(
                DemoFile.tournament_slug, DemoFile.tournament_name,
            ).order_by(DemoFile.tournament_name))
        ).all()
        names_by_slug: dict[str, str] = {}
        for slug, name in rows:
            names_by_slug.setdefault(slug, name)
        return [
            DemoTournamentOption(name=name, slug=slug)
            for slug, name in names_by_slug.items()
        ]
