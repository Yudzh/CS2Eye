import asyncio
from dataclasses import dataclass
from uuid import uuid4

from cs2eye.api.schemas.demos import DemoParseFileResult, DemoParseResponse
from cs2eye.core.config import settings
from cs2eye.db.session import AsyncSessionLocal
from cs2eye.services.demo_parse_service import DemoParseService


@dataclass
class DemoParseJob:
    job_id: str
    status: str = "queued"
    processed_files: int = 0
    total_files: int = 0
    parsed_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    current_filename: str | None = None
    error: str | None = None
    result: DemoParseResponse | None = None


class DemoParseJobManager:
    def __init__(self) -> None:
        self.jobs: dict[str, DemoParseJob] = {}
        self.tasks: set[asyncio.Task[None]] = set()
        self.parse_lock = asyncio.Lock()

    def start(
        self,
        *,
        tournament_name: str | None = None,
        year: int | None = None,
        replace_existing: bool = True,
    ) -> DemoParseJob:
        active = next(
            (job for job in self.jobs.values() if job.status in {"queued", "running"}),
            None,
        )
        if active is not None:
            return active
        job = DemoParseJob(job_id=str(uuid4()))
        self.jobs[job.job_id] = job
        task = asyncio.create_task(self._run(
            job, tournament_name=tournament_name, year=year,
            replace_existing=replace_existing,
        ))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return job

    def start_for_files(
        self, demo_file_ids: list[int], *, replace_existing: bool = True,
        delete_after_successful_parse: bool | None = None,
    ) -> DemoParseJob:
        job = DemoParseJob(job_id=str(uuid4()), total_files=len(demo_file_ids))
        self.jobs[job.job_id] = job
        task = asyncio.create_task(self._run(
            job, tournament_name=None, year=None,
            replace_existing=replace_existing, demo_file_ids=demo_file_ids,
            delete_after_successful_parse=delete_after_successful_parse,
        ))
        self.tasks.add(task); task.add_done_callback(self.tasks.discard)
        return job

    def get(self, job_id: str) -> DemoParseJob | None:
        return self.jobs.get(job_id)

    async def _run(
        self,
        job: DemoParseJob,
        *,
        tournament_name: str | None,
        year: int | None,
        replace_existing: bool,
        demo_file_ids: list[int] | None = None,
        delete_after_successful_parse: bool | None = None,
    ) -> None:
        job.status = "queued"

        async def progress(
            processed: int, total: int, result: DemoParseFileResult | None,
        ) -> None:
            job.processed_files = processed
            job.total_files = total
            if result is None:
                return
            job.current_filename = result.filename
            job.parsed_count += int(result.status == "parsed")
            job.skipped_count += int(result.status == "skipped")
            job.failed_count += int(result.status == "failed")

        try:
            async with self.parse_lock:
                job.status = "running"
                async with AsyncSessionLocal() as session:
                    service = DemoParseService(
                        session, settings.demo_storage_root,
                        settings.demo_delete_after_successful_parse
                        if delete_after_successful_parse is None
                        else delete_after_successful_parse,
                    )
                    if demo_file_ids is not None:
                        result = await service.parse_ids(
                            demo_file_ids, replace_existing=replace_existing,
                            progress_callback=progress,
                        )
                    elif tournament_name is None or year is None:
                        result = await service.parse_all(
                            replace_existing=replace_existing,
                            progress_callback=progress,
                        )
                    else:
                        result = await service.parse_many(
                            tournament_name, year, replace_existing,
                            progress_callback=progress,
                        )
            job.result = result
            job.total_files = result.total_files
            job.processed_files = result.total_files
            job.current_filename = None
            job.status = "completed"
        except Exception as error:
            job.error = str(error)
            job.current_filename = None
            job.status = "failed"


demo_parse_job_manager = DemoParseJobManager()
