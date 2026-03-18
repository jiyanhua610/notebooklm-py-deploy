"""FastAPI application for the NotebookLM PDF microservice."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import secrets
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .config import ServiceSettings
from .models import DownloadEntry, JobRecord, JobStatus, TERMINAL_STATUSES, utc_now
from .processor import NotebookLMPdfProcessor
from .store import JobStore, RedisJobStore

logger = logging.getLogger(__name__)


class CreateJobResponse(BaseModel):
    job_id: str
    status: str
    queue_position: int
    created_at: str


class JobResponse(BaseModel):
    job_id: str
    status: str
    queue_position: int | None = None
    download_url: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None


class HealthResponse(BaseModel):
    ok: bool
    queue_length: int
    active_job_id: str | None = None
    auth_configured: bool


def create_app(
    *,
    settings: ServiceSettings | None = None,
    store: JobStore | None = None,
    processor: NotebookLMPdfProcessor | Any | None = None,
) -> FastAPI:
    """Create the PDF service application."""

    service_settings = settings or ServiceSettings()
    service_settings.ensure_directories()
    service_store = store or RedisJobStore(
        service_settings.redis_url,
        prefix=service_settings.key_prefix,
        queue_name=service_settings.queue_name,
        job_ttl_seconds=service_settings.job_retention_seconds,
    )
    service_processor = processor or NotebookLMPdfProcessor(service_settings)

    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = service_settings
        app.state.store = service_store
        app.state.processor = service_processor
        app.state.stop_event = asyncio.Event()
        app.state.worker_task = asyncio.create_task(_worker_loop(app))
        app.state.cleanup_task = asyncio.create_task(_cleanup_loop(app))
        try:
            yield
        finally:
            app.state.stop_event.set()
            for task in (app.state.worker_task, app.state.cleanup_task):
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            await service_store.close()

    app = FastAPI(title="NotebookLM PDF Service", lifespan=lifespan)

    async def require_api_token(x_api_token: str = Header(default="")) -> None:
        if x_api_token != service_settings.api_token:
            raise HTTPException(status_code=401, detail="Unauthorized")

    @app.post("/v1/pdf-jobs", response_model=CreateJobResponse, dependencies=[Depends(require_api_token)])
    async def create_job(
        file: UploadFile = File(...),
        title: str | None = Form(default=None),
        instructions: str | None = Form(default=None),
        deck_format: str = Form(default="detailed_deck"),
        deck_length: str = Form(default="default"),
    ) -> CreateJobResponse:
        if deck_format not in {"detailed_deck", "presenter_slides"}:
            raise HTTPException(status_code=422, detail="Invalid deck_format")
        if deck_length not in {"default", "short"}:
            raise HTTPException(status_code=422, detail="Invalid deck_length")

        active_job_id = await service_store.get_active_job_id()
        current_queue_length = await service_store.queue_length()
        total_pending = current_queue_length + (1 if active_job_id else 0)
        if total_pending >= service_settings.max_queue_size:
            raise HTTPException(status_code=429, detail={"error_code": "queue_full"})

        job_id = uuid4().hex
        filename = file.filename or "upload"
        resolved_title = (title or Path(filename).stem or "upload").strip()
        input_path = service_settings.temp_dir / f"{job_id}-{Path(filename).name}"
        await _save_upload(file, input_path)

        job = JobRecord.create(
            job_id=job_id,
            title=resolved_title,
            filename=filename,
            input_path=str(input_path.resolve()),
            instructions=instructions,
            deck_format=deck_format,
            deck_length=deck_length,
        )
        await service_store.save_job(job)
        await service_store.enqueue(job.job_id)
        queue_position = await service_store.get_queue_position(job.job_id)

        return CreateJobResponse(
            job_id=job.job_id,
            status=job.status,
            queue_position=(queue_position or 0) + 1,
            created_at=job.created_at,
        )

    @app.get("/v1/pdf-jobs/{job_id}", response_model=JobResponse, dependencies=[Depends(require_api_token)])
    async def get_job(job_id: str) -> JobResponse:
        job = await service_store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return await _job_response(service_store, job)

    @app.post(
        "/v1/pdf-jobs/{job_id}/cancel",
        response_model=JobResponse,
        dependencies=[Depends(require_api_token)],
    )
    async def cancel_job(job_id: str) -> JobResponse:
        job = await service_store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.status == JobStatus.QUEUED.value:
            await service_store.remove_queued_job(job_id)
            await _set_job_terminal(
                service_store,
                job,
                JobStatus.CANCELLED,
                error_code="cancelled",
                error_message="Job cancelled before execution",
            )
            await _cleanup_input_file(job)
        elif job.status not in {status.value for status in TERMINAL_STATUSES}:
            job.status = JobStatus.CANCEL_REQUESTED.value
            job.update_timestamp()
            await service_store.save_job(job)
        return await _job_response(service_store, job)

    @app.get("/downloads/{token}")
    async def download_file(token: str) -> FileResponse:
        entry = await service_store.get_download_entry(token)
        if entry is None or entry.is_expired():
            if entry is not None:
                await service_store.delete_download_entry(token)
                with contextlib.suppress(OSError):
                    entry.path.unlink()
            raise HTTPException(status_code=404, detail="Download not found")
        if not entry.path.exists():
            raise HTTPException(status_code=404, detail="Download file missing")
        return FileResponse(entry.path, media_type="application/pdf", filename=entry.path.name)

    @app.get("/healthz", response_model=HealthResponse)
    async def healthz() -> HealthResponse:
        active_job_id = await service_store.get_active_job_id()
        queue_length = await service_store.queue_length()
        auth_configured = bool(
            os.getenv("NOTEBOOKLM_AUTH_JSON") or os.path.exists(os.getenv("NOTEBOOKLM_STORAGE_PATH", ""))
        )
        return HealthResponse(
            ok=True,
            queue_length=queue_length,
            active_job_id=active_job_id,
            auth_configured=auth_configured,
        )

    return app


async def _save_upload(file: UploadFile, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as handle:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    await file.close()


async def _job_response(store: JobStore, job: JobRecord) -> JobResponse:
    queue_position = None
    if job.status == JobStatus.QUEUED.value:
        queue_index = await store.get_queue_position(job.job_id)
        queue_position = None if queue_index is None else queue_index + 1
    return JobResponse(
        job_id=job.job_id,
        status=job.status,
        queue_position=queue_position,
        download_url=job.download_url if job.status == JobStatus.COMPLETED.value else None,
        error_code=job.error_code,
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


async def _worker_loop(app: FastAPI) -> None:
    store: JobStore = app.state.store
    settings: ServiceSettings = app.state.settings
    stop_event: asyncio.Event = app.state.stop_event
    while not stop_event.is_set():
        job_id = await store.dequeue_next_job(settings.queue_poll_seconds)
        if job_id is None:
            continue
        await _process_job(app, job_id)


async def _process_job(app: FastAPI, job_id: str) -> None:
    store: JobStore = app.state.store
    settings: ServiceSettings = app.state.settings
    processor: Any = app.state.processor
    lock_task: asyncio.Task[None] | None = None

    job = await store.get_job(job_id)
    if job is None:
        return

    if not await store.acquire_execution_lock(job_id, settings.lock_ttl_seconds):
        await store.enqueue(job_id)
        await asyncio.sleep(0.1)
        return

    notebook_id: str | None = None
    output_path: Path | None = None
    try:
        if _is_queue_expired(job, settings):
            await _set_job_terminal(
                store,
                job,
                JobStatus.FAILED,
                error_code="queue_expired",
                error_message="Job expired while waiting in queue",
            )
            await _cleanup_input_file(job)
            return

        if job.started_at is None:
            job.started_at = utc_now().isoformat()
        job.update_timestamp()
        await store.save_job(job)
        lock_task = asyncio.create_task(_renew_lock_loop(store, settings, job_id))
        notebook_id, output_path = await processor.process(
            job,
            lambda stage, payload=None: _on_stage(store, job.job_id, stage, payload),
        )

        latest = await store.get_job(job_id) or job
        if latest.status == JobStatus.CANCEL_REQUESTED.value:
            if output_path is not None:
                with contextlib.suppress(OSError):
                    output_path.unlink()
            await _set_job_terminal(
                store,
                latest,
                JobStatus.CANCELLED,
                error_code="cancelled",
                error_message="Job cancelled during execution",
            )
        else:
            download_url = await _publish_download(app, latest, output_path)
            latest = await store.get_job(job_id) or latest
            latest.status = JobStatus.COMPLETED.value
            latest.download_url = download_url
            latest.finished_at = utc_now().isoformat()
            latest.update_timestamp()
            await store.save_job(latest)
    except Exception as exc:
        latest = await store.get_job(job_id) or job
        await _set_job_terminal(
            store,
            latest,
            JobStatus.FAILED,
            error_code=_map_error_code(exc),
            error_message=str(exc),
        )
    finally:
        latest = await store.get_job(job_id)
        if latest is not None:
            notebook_id = notebook_id or latest.notebook_id
        await processor.cleanup_notebook(notebook_id)
        await _cleanup_input_file(job)
        if lock_task is not None:
            lock_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await lock_task
        await store.release_execution_lock(job_id)


async def _publish_download(app: FastAPI, job: JobRecord, output_path: Path | None) -> str:
    if output_path is None or not output_path.exists():
        raise FileNotFoundError("Generated PDF not found")

    settings: ServiceSettings = app.state.settings
    store: JobStore = app.state.store
    final_path = (settings.downloads_dir / f"{job.job_id}.pdf").resolve()
    final_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.replace(final_path)

    token = secrets.token_urlsafe(24)
    expires_at = utc_now() + timedelta(seconds=settings.download_ttl_seconds)
    entry = DownloadEntry(token=token, file_path=str(final_path), expires_at=expires_at.isoformat())
    await store.save_download_entry(entry, settings.download_ttl_seconds)

    job.download_token = token
    job.download_url = _build_download_url(settings, token)
    job.update_timestamp()
    await store.save_job(job)
    return job.download_url


def _build_download_url(settings: ServiceSettings, token: str) -> str:
    path = f"/downloads/{token}"
    if settings.public_base_url:
        return f"{settings.public_base_url.rstrip('/')}{path}"
    return path


async def _on_stage(
    store: JobStore,
    job_id: str,
    stage: JobStatus,
    payload: dict[str, Any] | None = None,
) -> None:
    payload = payload or {}
    job = await store.get_job(job_id)
    if job is None:
        return
    if job.status == JobStatus.CANCEL_REQUESTED.value:
        return
    job.status = stage.value
    if "notebook_id" in payload:
        job.notebook_id = payload["notebook_id"]
    job.update_timestamp()
    await store.save_job(job)


def _is_queue_expired(job: JobRecord, settings: ServiceSettings) -> bool:
    created_at = datetime.fromisoformat(job.created_at)
    return (utc_now() - created_at).total_seconds() > settings.queue_timeout_seconds


async def _set_job_terminal(
    store: JobStore,
    job: JobRecord,
    status: JobStatus,
    *,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    job.status = status.value
    job.error_code = error_code
    job.error_message = error_message
    job.finished_at = utc_now().isoformat()
    job.update_timestamp()
    job.download_token = None
    job.download_url = None
    await store.save_job(job)


async def _cleanup_input_file(job: JobRecord) -> None:
    with contextlib.suppress(OSError):
        job.input_file.unlink()


async def _renew_lock_loop(store: JobStore, settings: ServiceSettings, job_id: str) -> None:
    while True:
        await asyncio.sleep(max(1, settings.lock_ttl_seconds // 3))
        renewed = await store.renew_execution_lock(job_id, settings.lock_ttl_seconds)
        if not renewed:
            return


async def _cleanup_loop(app: FastAPI) -> None:
    store: JobStore = app.state.store
    settings: ServiceSettings = app.state.settings
    stop_event: asyncio.Event = app.state.stop_event
    while not stop_event.is_set():
        expired = await store.pop_expired_downloads(utc_now())
        for entry in expired:
            with contextlib.suppress(OSError):
                entry.path.unlink()
        await asyncio.sleep(settings.cleanup_interval_seconds)


def _map_error_code(exc: Exception) -> str:
    name = exc.__class__.__name__.lower()
    message = str(exc).lower()
    if "auth" in name or "login" in message or "authenticate" in message:
        return "auth_expired"
    if "rate" in name:
        return "rate_limited"
    if "timeout" in name:
        return "timeout"
    if "network" in name:
        return "network_error"
    return "processing_failed"
