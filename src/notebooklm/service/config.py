"""Configuration for the NotebookLM PDF service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


@dataclass
class ServiceSettings:
    api_token: str = os.getenv("NOTEBOOKLM_SERVICE_API_TOKEN", "dev-token")
    redis_url: str = os.getenv("NOTEBOOKLM_SERVICE_REDIS_URL", "redis://localhost:6379/0")
    queue_name: str = os.getenv("NOTEBOOKLM_SERVICE_QUEUE", "notebooklm:pdf:queue")
    key_prefix: str = os.getenv("NOTEBOOKLM_SERVICE_PREFIX", "notebooklm:pdf")
    temp_dir: Path = Path(os.getenv("NOTEBOOKLM_SERVICE_TMP_DIR", ".notebooklm-service/tmp"))
    downloads_dir: Path = Path(
        os.getenv("NOTEBOOKLM_SERVICE_DOWNLOADS_DIR", ".notebooklm-service/downloads")
    )
    download_ttl_seconds: int = _int_env("NOTEBOOKLM_SERVICE_DOWNLOAD_TTL_SECONDS", 3600)
    job_retention_seconds: int = _int_env("NOTEBOOKLM_SERVICE_JOB_RETENTION_SECONDS", 86400)
    lock_ttl_seconds: int = _int_env("NOTEBOOKLM_SERVICE_LOCK_TTL_SECONDS", 120)
    cleanup_interval_seconds: int = _int_env("NOTEBOOKLM_SERVICE_CLEANUP_INTERVAL_SECONDS", 30)
    queue_poll_seconds: int = _int_env("NOTEBOOKLM_SERVICE_QUEUE_POLL_SECONDS", 1)
    max_queue_size: int = _int_env("NOTEBOOKLM_SERVICE_MAX_QUEUE_SIZE", 10)
    queue_timeout_seconds: int = _int_env("NOTEBOOKLM_SERVICE_QUEUE_TIMEOUT_SECONDS", 3600)
    public_base_url: str | None = os.getenv("NOTEBOOKLM_SERVICE_PUBLIC_BASE_URL")
    default_language: str = os.getenv("NOTEBOOKLM_SERVICE_DEFAULT_LANGUAGE", "zh_Hans")
    source_wait_timeout_seconds: int = _int_env(
        "NOTEBOOKLM_SERVICE_SOURCE_WAIT_TIMEOUT_SECONDS", 300
    )
    generation_wait_timeout_seconds: int = _int_env(
        "NOTEBOOKLM_SERVICE_GENERATION_WAIT_TIMEOUT_SECONDS", 900
    )
    retry_attempts: int = _int_env("NOTEBOOKLM_SERVICE_RETRY_ATTEMPTS", 2)
    retry_delay_seconds: int = _int_env("NOTEBOOKLM_SERVICE_RETRY_DELAY_SECONDS", 2)

    def ensure_directories(self) -> None:
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
