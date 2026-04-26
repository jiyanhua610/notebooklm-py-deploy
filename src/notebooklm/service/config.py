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
    api_token: str = "dev-token"
    redis_url: str = "redis://localhost:6379/0"
    queue_name: str = "notebooklm:pdf:queue"
    key_prefix: str = "notebooklm:pdf"
    temp_dir: Path = Path(".notebooklm-service/tmp")
    downloads_dir: Path = Path(".notebooklm-service/downloads")
    download_ttl_seconds: int = 3600
    job_retention_seconds: int = 86400
    lock_ttl_seconds: int = 120
    cleanup_interval_seconds: int = 30
    queue_poll_seconds: int = 1
    max_queue_size: int = 10
    queue_timeout_seconds: int = 3600
    public_base_url: str | None = None
    default_language: str = "zh_Hans"
    source_wait_timeout_seconds: int = 300
    generation_wait_timeout_seconds: int = 900
    retry_attempts: int = 2
    retry_delay_seconds: int = 2
    storage_path: Path | None = None

    @classmethod
    def load(cls) -> ServiceSettings:
        """Load settings from service_config.json or environment variables."""
        import json

        # 1. Start with environment variables as default
        settings = cls(
            api_token=os.getenv("NOTEBOOKLM_SERVICE_API_TOKEN", "dev-token"),
            redis_url=os.getenv("NOTEBOOKLM_SERVICE_REDIS_URL", "redis://localhost:6379/0"),
            queue_name=os.getenv("NOTEBOOKLM_SERVICE_QUEUE", "notebooklm:pdf:queue"),
            key_prefix=os.getenv("NOTEBOOKLM_SERVICE_PREFIX", "notebooklm:pdf"),
            temp_dir=Path(os.getenv("NOTEBOOKLM_SERVICE_TMP_DIR", ".notebooklm-service/tmp")),
            downloads_dir=Path(
                os.getenv("NOTEBOOKLM_SERVICE_DOWNLOADS_DIR", ".notebooklm-service/downloads")
            ),
            download_ttl_seconds=_int_env("NOTEBOOKLM_SERVICE_DOWNLOAD_TTL_SECONDS", 3600),
            job_retention_seconds=_int_env("NOTEBOOKLM_SERVICE_JOB_RETENTION_SECONDS", 86400),
            lock_ttl_seconds=_int_env("NOTEBOOKLM_SERVICE_LOCK_TTL_SECONDS", 120),
            cleanup_interval_seconds=_int_env("NOTEBOOKLM_SERVICE_CLEANUP_INTERVAL_SECONDS", 30),
            queue_poll_seconds=_int_env("NOTEBOOKLM_SERVICE_QUEUE_POLL_SECONDS", 1),
            max_queue_size=_int_env("NOTEBOOKLM_SERVICE_MAX_QUEUE_SIZE", 10),
            queue_timeout_seconds=_int_env("NOTEBOOKLM_SERVICE_QUEUE_TIMEOUT_SECONDS", 3600),
            public_base_url=os.getenv("NOTEBOOKLM_SERVICE_PUBLIC_BASE_URL"),
            default_language=os.getenv("NOTEBOOKLM_SERVICE_DEFAULT_LANGUAGE", "zh_Hans"),
            storage_path=(
                Path(os.environ["NOTEBOOKLM_STORAGE_PATH"])
                if "NOTEBOOKLM_STORAGE_PATH" in os.environ
                else None
            ),
        )

        # 2. Override with service_config.json if it exists
        config_path = Path("service_config.json")
        if config_path.exists():
            try:
                with config_path.open("r", encoding="utf-8") as f:
                    config_data = json.load(f)
                    for key, value in config_data.items():
                        if hasattr(settings, key):
                            if key in ("temp_dir", "downloads_dir", "storage_path") and value:
                                setattr(settings, key, Path(value))
                            else:
                                setattr(settings, key, value)
            except Exception as e:
                print(f"Warning: Failed to load service_config.json: {e}")

        return settings

    def ensure_directories(self) -> None:
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
