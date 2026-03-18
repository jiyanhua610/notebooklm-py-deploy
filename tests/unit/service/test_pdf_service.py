"""Tests for the NotebookLM PDF microservice."""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from notebooklm.service.app import create_app
from notebooklm.service.config import ServiceSettings
from notebooklm.service.models import JobStatus, utc_now
from notebooklm.service.store import InMemoryJobStore


class FakeProcessor:
    def __init__(self):
        self.started_jobs: list[str] = []
        self.allow_finish = threading.Event()
        self.fail = False

    async def process(self, job, on_stage):
        self.started_jobs.append(job.job_id)
        notebook_id = f"nb-{job.job_id}"
        await on_stage(JobStatus.CREATING_NOTEBOOK, {"notebook_id": notebook_id})
        await on_stage(JobStatus.UPLOADING_SOURCE, {"notebook_id": notebook_id})
        await on_stage(JobStatus.WAITING_SOURCE_READY, {"notebook_id": notebook_id})
        await on_stage(JobStatus.GENERATING_PDF, {"notebook_id": notebook_id})
        await on_stage(JobStatus.WAITING_GENERATION, {"notebook_id": notebook_id})
        await asyncio.to_thread(self.allow_finish.wait)
        if self.fail:
            raise RuntimeError("boom")
        await on_stage(JobStatus.DOWNLOADING_PDF, {"notebook_id": notebook_id})
        output = Path(job.input_path).with_suffix(".pdf")
        output.write_bytes(b"%PDF-1.4 fake")
        return notebook_id, output

    async def cleanup_notebook(self, notebook_id):
        return None


@pytest.fixture
def service_setup(tmp_path):
    settings = ServiceSettings(
        api_token="secret",
        redis_url="redis://unused",
        queue_name="queue",
        key_prefix="test",
        temp_dir=tmp_path / "tmp",
        downloads_dir=tmp_path / "downloads",
        download_ttl_seconds=1,
        job_retention_seconds=3600,
        lock_ttl_seconds=30,
        cleanup_interval_seconds=1,
        queue_poll_seconds=1,
        max_queue_size=2,
        queue_timeout_seconds=3600,
        public_base_url="http://testserver",
    )
    settings.ensure_directories()
    store = InMemoryJobStore()
    processor = FakeProcessor()
    app = create_app(settings=settings, store=store, processor=processor)
    return app, store, processor


def _headers():
    return {"X-API-Token": "secret"}


def _create_job(client: TestClient, filename: str = "source.pdf"):
    return client.post(
        "/v1/pdf-jobs",
        headers=_headers(),
        files={"file": (filename, b"hello", "application/pdf")},
    )


def _wait_for_status(client: TestClient, job_id: str, expected: str, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        payload = client.get(f"/v1/pdf-jobs/{job_id}", headers=_headers()).json()
        if payload["status"] == expected:
            return payload
        time.sleep(0.05)
    return client.get(f"/v1/pdf-jobs/{job_id}", headers=_headers()).json()


def _wait_until_not_queued(client: TestClient, job_id: str, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        payload = client.get(f"/v1/pdf-jobs/{job_id}", headers=_headers()).json()
        if payload["status"] != JobStatus.QUEUED.value:
            return payload
        time.sleep(0.05)
    return client.get(f"/v1/pdf-jobs/{job_id}", headers=_headers()).json()


def test_jobs_are_queued_and_processed_in_order(service_setup):
    app, _store, processor = service_setup
    with TestClient(app) as client:
        first = _create_job(client)
        second = _create_job(client, "second.pdf")

        assert first.status_code == 200
        assert second.status_code == 200
        first_job = first.json()["job_id"]
        second_job = second.json()["job_id"]

        first_status = client.get(f"/v1/pdf-jobs/{first_job}", headers=_headers()).json()
        second_status = client.get(f"/v1/pdf-jobs/{second_job}", headers=_headers()).json()
        assert first_status["status"] != JobStatus.QUEUED.value
        assert second_status["status"] == JobStatus.QUEUED.value
        assert second_status["queue_position"] == 1

        processor.allow_finish.set()
        second_running = _wait_until_not_queued(client, second_job)
        assert second_running["status"] != JobStatus.QUEUED.value
        assert processor.started_jobs[:2] == [first_job, second_job]


def test_cancel_queued_job_removes_it_from_queue(service_setup):
    app, _store, processor = service_setup
    with TestClient(app) as client:
        _create_job(client)
        second = _create_job(client, "second.pdf")
        second_job = second.json()["job_id"]

        response = client.post(f"/v1/pdf-jobs/{second_job}/cancel", headers=_headers())
        assert response.status_code == 200
        assert response.json()["status"] == JobStatus.CANCELLED.value

        processor.allow_finish.set()
        time.sleep(0.3)
        assert second_job not in processor.started_jobs


def test_cancel_running_job_hides_download(service_setup):
    app, _store, processor = service_setup
    with TestClient(app) as client:
        created = _create_job(client)
        job_id = created.json()["job_id"]

        response = client.post(f"/v1/pdf-jobs/{job_id}/cancel", headers=_headers())
        assert response.status_code == 200
        assert response.json()["status"] == JobStatus.CANCEL_REQUESTED.value

        processor.allow_finish.set()
        final = _wait_for_status(client, job_id, JobStatus.CANCELLED.value)
        assert final["status"] == JobStatus.CANCELLED.value
        assert final["download_url"] is None


def test_queue_full_returns_429(service_setup):
    app, _store, _processor = service_setup
    with TestClient(app) as client:
        first = _create_job(client)
        second = _create_job(client, "second.pdf")
        third = _create_job(client, "third.pdf")

        assert first.status_code == 200
        assert second.status_code == 200
        assert third.status_code == 429


def test_completed_job_returns_download_url(service_setup):
    app, _store, processor = service_setup
    with TestClient(app) as client:
        created = _create_job(client)
        job_id = created.json()["job_id"]
        processor.allow_finish.set()

        final = _wait_for_status(client, job_id, JobStatus.COMPLETED.value)
        assert final["status"] == JobStatus.COMPLETED.value
        assert final["download_url"].startswith("http://testserver/downloads/")

        download = client.get(final["download_url"])
        assert download.status_code == 200
        assert download.headers["content-type"].startswith("application/pdf")


def test_expired_download_token_is_rejected(service_setup):
    app, store, processor = service_setup
    with TestClient(app) as client:
        created = _create_job(client)
        job_id = created.json()["job_id"]
        processor.allow_finish.set()

        final = _wait_for_status(client, job_id, JobStatus.COMPLETED.value)
        token = final["download_url"].rsplit("/", 1)[-1]
        entry = store.downloads[token]
        entry.expires_at = utc_now().isoformat()
        store.downloads[token] = entry

        download = client.get(final["download_url"])
        assert download.status_code == 404
