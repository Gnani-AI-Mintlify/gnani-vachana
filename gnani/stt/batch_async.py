"""Async Batch Speech-to-Text client.

Same flow as :class:`~gnani.stt.batch.GnaniSTTBatchClient`, for ``asyncio`` code::

    from gnani.stt import AsyncGnaniSTTBatchClient

    client = AsyncGnaniSTTBatchClient()  # reads GNANI_API_KEY
    result = await client.transcribe(["call1.wav", "call2.wav"], language_code="hi-IN")
    print(result[0].text)
    await result.save("./outputs")

Calls run on worker threads (``asyncio.to_thread``) over the same ``requests``
transport as the sync client, so no extra dependency is needed and the event
loop is never blocked. Transcripts are downloaded concurrently, so by the time
``transcribe()`` returns, ``.text`` and ``.segments`` are plain attributes.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from gnani.log import logger
from gnani.stt.batch import (
    BATCH_MIN_POLL_SECONDS,
    SUCCESS_STATUSES,
    BatchFile,
    BatchJob,
    BatchSegment,
    GnaniSTTBatchClient,
    _make_bar,
    _save,
)
from gnani.stt.client import DEFAULT_BASE_URL
from gnani.stt.exceptions import BatchJobFailedError, BatchTimeoutError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable
    from pathlib import Path

# Transcript downloads running at once; keeps a 100-file job from opening 100 sockets.
_DOWNLOAD_CONCURRENCY = 8


class AsyncBatchFile:
    """One file in a batch job. Call :meth:`load` once, then read ``text``/``segments``."""

    def __init__(self, file: BatchFile) -> None:
        self._f = file

    file_id = property(lambda self: self._f.file_id)
    name = property(lambda self: self._f.name)
    status = property(lambda self: self._f.status)
    duration = property(lambda self: self._f.duration)
    error = property(lambda self: self._f.error)
    progress_percent = property(lambda self: self._f.progress_percent)
    stage = property(lambda self: self._f.stage)
    ok = property(lambda self: self._f.ok)

    @property
    def loaded(self) -> bool:
        return self._f._transcript is not None

    async def load(self) -> AsyncBatchFile:
        """Download the transcript (a no-op if already loaded or not ``COMPLETED``)."""
        if self._f.ok and not self.loaded:
            await asyncio.to_thread(lambda: self._f.transcript)
        return self

    def _need_loaded(self) -> None:
        if not self.loaded:
            if not self._f.ok:
                raise ValueError(
                    f"No transcript for '{self.name}': status is {self.status}"
                    + (f" ({self.error})" if self.error else "")
                )
            raise RuntimeError(
                f"Transcript for '{self.name}' not downloaded: await file.load() first"
            )

    @property
    def transcript(self) -> dict[str, Any]:
        self._need_loaded()
        return self._f.transcript

    @property
    def text(self) -> str:
        self._need_loaded()
        return self._f.text

    @property
    def segments(self) -> list[BatchSegment]:
        self._need_loaded()
        return self._f.segments

    def __repr__(self) -> str:
        return f"Async{self._f!r}"


class AsyncBatchJob:
    """A batch job. ``await job.wait()`` then ``await job.files()``."""

    def __init__(self, job: BatchJob) -> None:
        self._j = job

    id = property(lambda self: self._j.id)
    status = property(lambda self: self._j.status)
    percent = property(lambda self: self._j.percent)
    total_files = property(lambda self: self._j.total_files)
    completed_files = property(lambda self: self._j.completed_files)
    failed_files = property(lambda self: self._j.failed_files)
    cancel_reason = property(lambda self: self._j.cancel_reason)
    config = property(lambda self: self._j.config)
    is_done = property(lambda self: self._j.is_done)

    async def refresh(self) -> AsyncBatchJob:
        await asyncio.to_thread(self._j.refresh)
        return self

    async def start(self) -> AsyncBatchJob:
        await asyncio.to_thread(self._j.start)
        return self

    async def cancel(self, reason: str | None = None) -> AsyncBatchJob:
        await asyncio.to_thread(self._j.cancel, reason)
        return self

    async def wait(
        self,
        *,
        timeout: float | None = None,
        poll_interval: float = BATCH_MIN_POLL_SECONDS,
        max_poll_interval: float = 30.0,
        progress: bool = False,
        on_progress: Callable[[AsyncBatchJob], None] | None = None,
        raise_on_failure: bool = True,
    ) -> AsyncBatchJob:
        """Wait until the job is terminal. Semantics match :meth:`BatchJob.wait`.

        Cancelling the awaiting task leaves the job running on the server.
        """
        interval = max(poll_interval, BATCH_MIN_POLL_SECONDS)
        deadline = None if timeout is None else time.monotonic() + timeout
        bar = _make_bar(self.id) if progress else None
        last = -1
        try:
            while True:
                await self.refresh()
                if bar is not None:
                    bar(self._j)
                elif progress and self.percent != last:
                    logger.info("[STT Batch] %s %s %d%%", self.id, self.status, self.percent)
                last = self.percent
                if on_progress is not None:
                    on_progress(self)
                if self.is_done:
                    break
                if deadline is not None and time.monotonic() + interval > deadline:
                    raise BatchTimeoutError(self.id, timeout or 0.0)
                await asyncio.sleep(interval)
                interval = min(interval * 1.25, max(max_poll_interval, interval))
        except asyncio.CancelledError:
            logger.warning(
                "[STT Batch] wait cancelled; job %s keeps running. Resume with client.get_job(%r).",
                self.id,
                self.id,
            )
            raise
        finally:
            if bar is not None:
                bar(None)
        if raise_on_failure and self.status not in SUCCESS_STATUSES:
            raise BatchJobFailedError(self.id, self.status, self.cancel_reason)
        return self

    async def files(self, *, status: str | None = None, load: bool = False) -> list[AsyncBatchFile]:
        """All files in the job. ``load=True`` also downloads every transcript, concurrently."""
        raw = await asyncio.to_thread(self._j.files, status=status)
        out = [AsyncBatchFile(f) for f in raw]
        if load:
            sem = asyncio.Semaphore(_DOWNLOAD_CONCURRENCY)

            async def _one(f: AsyncBatchFile) -> None:
                async with sem:
                    await f.load()

            await asyncio.gather(*(_one(f) for f in out))
        return out

    async def save(self, output_dir: str | Path, *, text_files: bool = False) -> list[Path]:
        """Write each completed file's transcript JSON to ``output_dir``."""
        files = await self.files(load=True)
        return await asyncio.to_thread(_save, [f._f for f in files], output_dir, text_files)

    def __repr__(self) -> str:
        return f"Async{self._j!r}"


class AsyncBatchResult:
    """What :meth:`AsyncGnaniSTTBatchClient.transcribe` returns."""

    def __init__(self, job: AsyncBatchJob, files: list[AsyncBatchFile]) -> None:
        self.job = job
        self.files = files

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.files)

    def __getitem__(self, i: int) -> AsyncBatchFile:
        return self.files[i]

    def __len__(self) -> int:
        return len(self.files)

    @property
    def failed(self) -> list[AsyncBatchFile]:
        return [f for f in self.files if not f.ok]

    @property
    def text(self) -> str:
        """All transcripts joined, one file per paragraph."""
        return "\n\n".join(f.text for f in self.files if f.ok)

    async def save(self, output_dir: str | Path, *, text_files: bool = False) -> list[Path]:
        return await asyncio.to_thread(_save, [f._f for f in self.files], output_dir, text_files)

    def __repr__(self) -> str:
        return (
            f"AsyncBatchResult(job={self.job.id!r}, files={len(self.files)}, "
            f"failed={len(self.failed)})"
        )


class AsyncGnaniSTTBatchClient:
    """Async client for Gnani's Batch Speech-to-Text API.

    Takes the same arguments as :class:`GnaniSTTBatchClient`.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = 60,
        upload_timeout: int = 600,
    ) -> None:
        self._sync = GnaniSTTBatchClient(
            api_key, base_url=base_url, timeout=timeout, upload_timeout=upload_timeout
        )

    async def transcribe(
        self,
        files: Any,
        language_code: str = "en-IN",
        *,
        timeout: float | None = None,
        progress: bool = True,
        raise_on_failure: bool = True,
        **options: Any,
    ) -> AsyncBatchResult:
        """Create, start and wait for a job, then return its files with transcripts loaded.

        ``files`` and ``options`` are those of :meth:`create_job`.
        """
        job = await self.create_job(files, language_code, **options)
        await job.wait(timeout=timeout, progress=progress, raise_on_failure=raise_on_failure)
        return AsyncBatchResult(job, await job.files(load=True))

    async def create_job(
        self, files: Any, language_code: str = "en-IN", **options: Any
    ) -> AsyncBatchJob:
        """Upload audio and create a job, starting it unless ``start=False``.

        Arguments are those of :meth:`GnaniSTTBatchClient.create_job`.
        """
        job = await asyncio.to_thread(self._sync.create_job, files, language_code, **options)
        return AsyncBatchJob(job)

    async def get_job(self, job_id: str) -> AsyncBatchJob:
        """Fetch an existing job, e.g. to resume waiting after a restart."""
        return AsyncBatchJob(await asyncio.to_thread(self._sync.get_job, job_id))

    async def list_jobs(
        self, *, status: str | None = None, limit: int = 20
    ) -> AsyncIterator[AsyncBatchJob]:
        """Iterate your jobs, newest first: ``async for job in client.list_jobs()``."""
        it = self._sync.list_jobs(status=status, limit=limit)
        done = object()
        while True:
            job = await asyncio.to_thread(next, it, done)
            if job is done:
                return
            yield AsyncBatchJob(job)  # type: ignore[arg-type]

    @staticmethod
    def supported_languages() -> dict[str, str]:
        return GnaniSTTBatchClient.supported_languages()
