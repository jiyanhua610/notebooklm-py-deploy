"""Shared models for the NotebookLM slide deck service."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    """Return the current UTC time."""
    return datetime.now(timezone.utc)


class JobStatus(str, Enum):
    QUEUED = "queued"
    CREATING_NOTEBOOK = "creating_notebook"
    UPLOADING_SOURCE = "uploading_source"
    WAITING_SOURCE_READY = "waiting_source_ready"
    GENERATING_PDF = "generating_pdf"
    WAITING_GENERATION = "waiting_generation"
    DOWNLOADING_PDF = "downloading_pdf"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    CANCEL_REQUESTED = "cancel_requested"


TERMINAL_STATUSES = {
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
}


@dataclass
class JobRecord:
    """Persisted job state."""

    job_id: str
    title: str
    filenames: list[str]
    input_paths: list[str]
    status: str
    instructions: str | None
    language: str | None
    deck_format: str
    deck_length: str
    output_format: str
    created_at: str
    updated_at: str
    started_at: str | None = None
    finished_at: str | None = None
    notebook_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    download_token: str | None = None
    download_url: str | None = None

    @classmethod
    def create(
        cls,
        *,
        job_id: str,
        title: str,
        filenames: list[str],
        input_paths: list[str],
        instructions: str | None,
        language: str | None,
        deck_format: str,
        deck_length: str,
        output_format: str,
    ) -> "JobRecord":
        now = utc_now().isoformat()
        return cls(
            job_id=job_id,
            title=title,
            filenames=filenames,
            input_paths=input_paths,
            status=JobStatus.QUEUED.value,
            instructions=instructions,
            language=language,
            deck_format=deck_format,
            deck_length=deck_length,
            output_format=output_format,
            created_at=now,
            updated_at=now,
        )

    @property
    def is_terminal(self) -> bool:
        return self.status in {status.value for status in TERMINAL_STATUSES}

    @property
    def input_files(self) -> list[Path]:
        return [Path(path) for path in self.input_paths]

    @property
    def source_count(self) -> int:
        return len(self.input_paths)

    def update_timestamp(self) -> None:
        self.updated_at = utc_now().isoformat()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JobRecord":
        normalized = dict(data)
        if "filenames" not in normalized and "filename" in normalized:
            normalized["filenames"] = [normalized.pop("filename")]
        if "input_paths" not in normalized and "input_path" in normalized:
            normalized["input_paths"] = [normalized.pop("input_path")]
        normalized.setdefault("output_format", "pdf")
        return cls(**normalized)


@dataclass
class DownloadEntry:
    """Download token mapping."""

    token: str
    file_path: str
    expires_at: str

    @property
    def path(self) -> Path:
        return Path(self.file_path)

    def is_expired(self, at: datetime | None = None) -> bool:
        now = at or utc_now()
        return datetime.fromisoformat(self.expires_at) <= now

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DownloadEntry":
        return cls(**data)
