"""NotebookLM processing pipeline for PDF jobs."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from notebooklm import NotebookLMClient
from notebooklm.exceptions import NetworkError, RPCTimeoutError, RateLimitError
from notebooklm.types import SlideDeckFormat, SlideDeckLength

from .config import ServiceSettings
from .models import JobStatus

StageCallback = Callable[[JobStatus, dict[str, Any] | None], Awaitable[None]]


class NotebookLMPdfProcessor:
    """Run the NotebookLM PDF generation flow for a job."""

    def __init__(self, settings: ServiceSettings):
        self._settings = settings

    async def process(self, job: Any, on_stage: StageCallback) -> tuple[str | None, Path | None]:
        async with await NotebookLMClient.from_storage() as client:
            await on_stage(JobStatus.CREATING_NOTEBOOK, None)
            notebook = await client.notebooks.create(self._build_notebook_title(job))

            for index, input_path in enumerate(job.input_paths, start=1):
                await on_stage(
                    JobStatus.UPLOADING_SOURCE,
                    {
                        "notebook_id": notebook.id,
                        "current_file": job.filenames[index - 1],
                        "current_index": index,
                        "total_files": job.source_count,
                    },
                )
                source = await client.sources.add_file(notebook.id, input_path)

                await on_stage(
                    JobStatus.WAITING_SOURCE_READY,
                    {
                        "notebook_id": notebook.id,
                        "current_file": job.filenames[index - 1],
                        "current_index": index,
                        "total_files": job.source_count,
                    },
                )
                await self._retryable(
                    client.sources.wait_until_ready,
                    notebook.id,
                    source.id,
                    timeout=self._settings.source_wait_timeout_seconds,
                )

            await on_stage(JobStatus.GENERATING_PDF, {"notebook_id": notebook.id})
            status = await client.artifacts.generate_slide_deck(
                notebook.id,
                language=(job.language or self._settings.default_language),
                instructions=job.instructions,
                slide_format=self._resolve_format(job.deck_format),
                slide_length=self._resolve_length(job.deck_length),
            )

            await on_stage(JobStatus.WAITING_GENERATION, {"notebook_id": notebook.id})
            await self._retryable(
                client.artifacts.wait_for_completion,
                notebook.id,
                status.task_id,
                timeout=self._settings.generation_wait_timeout_seconds,
            )

            await on_stage(JobStatus.DOWNLOADING_PDF, {"notebook_id": notebook.id})
            output_path = (self._settings.temp_dir / f"{job.job_id}.{job.output_format}").resolve()
            await self._retryable(
                client.artifacts.download_slide_deck,
                notebook.id,
                str(output_path),
                output_format=job.output_format,
            )
            return notebook.id, output_path

    async def cleanup_notebook(self, notebook_id: str | None) -> None:
        if not notebook_id:
            return
        try:
            async with await NotebookLMClient.from_storage() as client:
                await client.notebooks.delete(notebook_id)
        except Exception:
            return

    async def _retryable(self, func: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any) -> Any:
        last_error: Exception | None = None
        for attempt in range(1, self._settings.retry_attempts + 1):
            try:
                return await func(*args, **kwargs)
            except (NetworkError, RPCTimeoutError, RateLimitError) as exc:
                last_error = exc
                if attempt >= self._settings.retry_attempts:
                    raise
                await asyncio.sleep(self._settings.retry_delay_seconds)
        if last_error is not None:
            raise last_error
        raise RuntimeError("Retry loop exited without result")

    def _build_notebook_title(self, job: Any) -> str:
        safe_title = re.sub(r"[^A-Za-z0-9._ -]+", "-", job.title).strip() or "untitled"
        return f"ppt-job-{job.job_id}-{safe_title}"[:120]

    def _resolve_format(self, value: str) -> SlideDeckFormat | None:
        mapping = {
            "detailed_deck": SlideDeckFormat.DETAILED_DECK,
            "presenter_slides": SlideDeckFormat.PRESENTER_SLIDES,
        }
        return mapping.get(value)

    def _resolve_length(self, value: str) -> SlideDeckLength | None:
        mapping = {
            "default": SlideDeckLength.DEFAULT,
            "short": SlideDeckLength.SHORT,
        }
        return mapping.get(value)
