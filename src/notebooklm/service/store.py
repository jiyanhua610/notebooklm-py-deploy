"""Persistence and queue backends for the PDF service."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from datetime import datetime
from typing import Protocol

from .models import DownloadEntry, JobRecord


class JobStore(Protocol):
    async def save_job(self, job: JobRecord) -> None: ...
    async def get_job(self, job_id: str) -> JobRecord | None: ...
    async def enqueue(self, job_id: str) -> None: ...
    async def dequeue_next_job(self, timeout_seconds: int) -> str | None: ...
    async def get_queue_position(self, job_id: str) -> int | None: ...
    async def remove_queued_job(self, job_id: str) -> bool: ...
    async def queue_length(self) -> int: ...
    async def acquire_execution_lock(self, job_id: str, ttl_seconds: int) -> bool: ...
    async def renew_execution_lock(self, job_id: str, ttl_seconds: int) -> bool: ...
    async def release_execution_lock(self, job_id: str) -> None: ...
    async def get_active_job_id(self) -> str | None: ...
    async def save_download_entry(self, entry: DownloadEntry, ttl_seconds: int) -> None: ...
    async def get_download_entry(self, token: str) -> DownloadEntry | None: ...
    async def delete_download_entry(self, token: str) -> None: ...
    async def pop_expired_downloads(self, now: datetime) -> list[DownloadEntry]: ...
    async def close(self) -> None: ...


class RedisJobStore:
    """Redis-backed job queue and metadata store."""

    def __init__(self, redis_url: str, *, prefix: str, queue_name: str, job_ttl_seconds: int):
        from redis.asyncio import Redis

        self._redis = Redis.from_url(redis_url, decode_responses=True)
        self._prefix = prefix
        self._queue_name = queue_name
        self._job_ttl_seconds = job_ttl_seconds

    def _job_key(self, job_id: str) -> str:
        return f"{self._prefix}:job:{job_id}"

    def _download_key(self, token: str) -> str:
        return f"{self._prefix}:download:{token}"

    @property
    def _lock_key(self) -> str:
        return f"{self._prefix}:active-lock"

    @property
    def _downloads_zset_key(self) -> str:
        return f"{self._prefix}:downloads:expires"

    async def save_job(self, job: JobRecord) -> None:
        key = self._job_key(job.job_id)
        await self._redis.set(key, json.dumps(job.to_dict()))
        if job.is_terminal:
            await self._redis.expire(key, self._job_ttl_seconds)

    async def get_job(self, job_id: str) -> JobRecord | None:
        raw = await self._redis.get(self._job_key(job_id))
        if raw is None:
            return None
        return JobRecord.from_dict(json.loads(raw))

    async def enqueue(self, job_id: str) -> None:
        await self._redis.rpush(self._queue_name, job_id)

    async def dequeue_next_job(self, timeout_seconds: int) -> str | None:
        result = await self._redis.blpop(self._queue_name, timeout=timeout_seconds)
        if result is None:
            return None
        _, job_id = result
        return job_id

    async def get_queue_position(self, job_id: str) -> int | None:
        jobs = await self._redis.lrange(self._queue_name, 0, -1)
        for idx, value in enumerate(jobs):
            if value == job_id:
                return idx
        return None

    async def remove_queued_job(self, job_id: str) -> bool:
        removed = await self._redis.lrem(self._queue_name, 1, job_id)
        return removed > 0

    async def queue_length(self) -> int:
        return int(await self._redis.llen(self._queue_name))

    async def acquire_execution_lock(self, job_id: str, ttl_seconds: int) -> bool:
        result = await self._redis.set(self._lock_key, job_id, ex=ttl_seconds, nx=True)
        return bool(result)

    async def renew_execution_lock(self, job_id: str, ttl_seconds: int) -> bool:
        current = await self._redis.get(self._lock_key)
        if current != job_id:
            return False
        await self._redis.expire(self._lock_key, ttl_seconds)
        return True

    async def release_execution_lock(self, job_id: str) -> None:
        current = await self._redis.get(self._lock_key)
        if current == job_id:
            await self._redis.delete(self._lock_key)

    async def get_active_job_id(self) -> str | None:
        return await self._redis.get(self._lock_key)

    async def save_download_entry(self, entry: DownloadEntry, ttl_seconds: int) -> None:
        key = self._download_key(entry.token)
        await self._redis.set(key, json.dumps(entry.to_dict()), ex=ttl_seconds)
        expires_ts = datetime.fromisoformat(entry.expires_at).timestamp()
        await self._redis.zadd(self._downloads_zset_key, {entry.token: expires_ts})

    async def get_download_entry(self, token: str) -> DownloadEntry | None:
        raw = await self._redis.get(self._download_key(token))
        if raw is None:
            return None
        return DownloadEntry.from_dict(json.loads(raw))

    async def delete_download_entry(self, token: str) -> None:
        await self._redis.delete(self._download_key(token))
        await self._redis.zrem(self._downloads_zset_key, token)

    async def pop_expired_downloads(self, now: datetime) -> list[DownloadEntry]:
        tokens = await self._redis.zrangebyscore(self._downloads_zset_key, 0, now.timestamp())
        entries: list[DownloadEntry] = []
        for token in tokens:
            entry = await self.get_download_entry(token)
            if entry is not None:
                entries.append(entry)
            await self.delete_download_entry(token)
        return entries

    async def close(self) -> None:
        await self._redis.aclose()


class InMemoryJobStore:
    """In-memory store for tests."""

    def __init__(self):
        self.jobs: dict[str, JobRecord] = {}
        self.queue: deque[str] = deque()
        self.downloads: dict[str, DownloadEntry] = {}
        self._active_job_id: str | None = None
        self._lock = asyncio.Lock()
        self._queue_event = asyncio.Event()

    async def save_job(self, job: JobRecord) -> None:
        async with self._lock:
            self.jobs[job.job_id] = JobRecord.from_dict(job.to_dict())

    async def get_job(self, job_id: str) -> JobRecord | None:
        async with self._lock:
            job = self.jobs.get(job_id)
            return JobRecord.from_dict(job.to_dict()) if job is not None else None

    async def enqueue(self, job_id: str) -> None:
        async with self._lock:
            self.queue.append(job_id)
            self._queue_event.set()

    async def dequeue_next_job(self, timeout_seconds: int) -> str | None:
        try:
            await asyncio.wait_for(self._queue_event.wait(), timeout=timeout_seconds)
        except TimeoutError:
            return None
        async with self._lock:
            if not self.queue:
                self._queue_event.clear()
                return None
            job_id = self.queue.popleft()
            if not self.queue:
                self._queue_event.clear()
            return job_id

    async def get_queue_position(self, job_id: str) -> int | None:
        async with self._lock:
            for idx, value in enumerate(self.queue):
                if value == job_id:
                    return idx
        return None

    async def remove_queued_job(self, job_id: str) -> bool:
        async with self._lock:
            try:
                self.queue.remove(job_id)
                if not self.queue:
                    self._queue_event.clear()
                return True
            except ValueError:
                return False

    async def queue_length(self) -> int:
        async with self._lock:
            return len(self.queue)

    async def acquire_execution_lock(self, job_id: str, ttl_seconds: int) -> bool:
        del ttl_seconds
        async with self._lock:
            if self._active_job_id is not None:
                return False
            self._active_job_id = job_id
            return True

    async def renew_execution_lock(self, job_id: str, ttl_seconds: int) -> bool:
        del ttl_seconds
        async with self._lock:
            return self._active_job_id == job_id

    async def release_execution_lock(self, job_id: str) -> None:
        async with self._lock:
            if self._active_job_id == job_id:
                self._active_job_id = None

    async def get_active_job_id(self) -> str | None:
        async with self._lock:
            return self._active_job_id

    async def save_download_entry(self, entry: DownloadEntry, ttl_seconds: int) -> None:
        del ttl_seconds
        async with self._lock:
            self.downloads[entry.token] = entry

    async def get_download_entry(self, token: str) -> DownloadEntry | None:
        async with self._lock:
            return self.downloads.get(token)

    async def delete_download_entry(self, token: str) -> None:
        async with self._lock:
            self.downloads.pop(token, None)

    async def pop_expired_downloads(self, now: datetime) -> list[DownloadEntry]:
        async with self._lock:
            expired = [entry for entry in self.downloads.values() if entry.is_expired(now)]
            for entry in expired:
                self.downloads.pop(entry.token, None)
            return expired

    async def close(self) -> None:
        return None
