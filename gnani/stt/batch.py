"""Batch Speech-to-Text client: transcribe many or long files asynchronously.

The shortest path is one call::

    from gnani.stt import GnaniSTTBatchClient

    client = GnaniSTTBatchClient()  # reads GNANI_API_KEY
    result = client.transcribe(["call1.wav", "call2.wav"], language_code="hi-IN")
    print(result[0].text)
    result.save("./outputs")

For long jobs, or to resume one later, drive the job yourself::

    job = client.create_job("./recordings/", language_code="hi-IN")
    job.wait()
    for f in job.files():
        print(f.name, f.text)
"""

from __future__ import annotations

import glob as _glob
import json
import os
import re
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, BinaryIO, Callable

import requests

from gnani.log import logger, resolve_request_id
from gnani.stt.client import DEFAULT_BASE_URL, SUPPORTED_LANGUAGES
from gnani.stt.exceptions import (
    APIError,
    AuthenticationError,
    BatchJobFailedError,
    BatchTimeoutError,
    InvalidAudioError,
)

BATCH_ENDPOINT = "/stt/v3/batch/jobs"
DEFAULT_BATCH_MODEL = "gnani-prisma-v2.5"

# Batch accepts more containers than the REST endpoint does.
BATCH_SUPPORTED_EXTENSIONS = frozenset(
    {".wav", ".mp3", ".mp4", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".webm", ".amr"}
)
BATCH_MAX_FILES = 100
BATCH_MAX_FILE_BYTES = 10 * 1024 * 1024
BATCH_MAX_ZIP_BYTES = 50 * 1024 * 1024
BATCH_MIN_POLL_SECONDS = 10.0
BATCH_MAX_SPEAKERS = 8
BATCH_BIAS_SCORES = (0.0, 0.5, 1.0, 1.5, 2.0)
BATCH_MAX_BIAS_WORDS = 100

# Job states after which nothing more will change.
TERMINAL_STATUSES = frozenset(
    {"COMPLETED", "PARTIAL_FAILURE", "FAILED", "START_FAILED", "CANCELLED"}
)
# Terminal states in which at least some transcripts exist.
SUCCESS_STATUSES = frozenset({"COMPLETED", "PARTIAL_FAILURE"})

_GLOB_CHARS = re.compile(r"[*?\[]")

# ---------------------------------------------------------------------------
# Result objects
# ---------------------------------------------------------------------------


@dataclass
class BatchSegment:
    """One transcribed span of a file."""

    start: float
    end: float
    text: str
    speaker: int | None = None


@dataclass
class BatchFile:
    """One file in a batch job.

    ``text``, ``segments`` and ``transcript`` download the transcript on first
    access (and only for a ``COMPLETED`` file). If the presigned link has
    expired, the job's file list is re-fetched and the download retried once.
    """

    file_id: str
    name: str
    status: str
    duration: float | None = None
    error: str | None = None
    progress_percent: int = 0
    stage: str | None = None
    transcript_url: str | None = field(default=None, repr=False)
    _job: BatchJob | None = field(default=None, repr=False, compare=False)
    _transcript: dict[str, Any] | None = field(default=None, repr=False, compare=False)

    @property
    def ok(self) -> bool:
        return self.status == "COMPLETED"

    @property
    def transcript(self) -> dict[str, Any]:
        """The full transcript document (``full_transcript``, ``segments``, ...)."""
        if self._transcript is None:
            if not self.ok:
                raise ValueError(
                    f"No transcript for '{self.name}': status is {self.status}"
                    + (f" ({self.error})" if self.error else "")
                )
            self._transcript = self._download()
        return self._transcript

    @property
    def text(self) -> str:
        doc = self.transcript
        full = doc.get("full_transcript")
        if full:
            return str(full)
        return " ".join(s.text for s in self.segments)

    @property
    def segments(self) -> list[BatchSegment]:
        return [
            BatchSegment(
                start=float(s.get("start_time", 0.0)),
                end=float(s.get("end_time", 0.0)),
                text=str(s.get("text", "")),
                speaker=s.get("speaker_id"),
            )
            for s in self.transcript.get("segments", [])
        ]

    def _download(self) -> dict[str, Any]:
        url = self.transcript_url
        for attempt in (1, 2):
            if url:
                # Presigned S3 URL: must NOT carry our API key.
                resp = requests.get(url, timeout=60)
                if resp.status_code == 200:
                    return resp.json()  # type: ignore[no-any-return]
                if attempt == 2 or resp.status_code not in (400, 403, 404):
                    raise APIError(resp.status_code, resp.text)
            if self._job is None:
                raise APIError(
                    403, "transcript link expired and the file has no job to refresh from"
                )
            fresh = {f.file_id: f for f in self._job.files()}.get(self.file_id)
            url = fresh.transcript_url if fresh else None
            self.transcript_url = url
        raise APIError(403, "could not obtain a fresh transcript link")  # pragma: no cover


@dataclass
class BatchJob:
    """A batch transcription job. Use :meth:`wait` then :meth:`files`."""

    id: str
    status: str
    percent: int = 0
    total_files: int | None = None
    completed_files: int | None = None
    failed_files: int | None = None
    cancel_reason: str | None = None
    config: dict[str, Any] | None = None
    _client: GnaniSTTBatchClient | None = field(default=None, repr=False, compare=False)

    @property
    def is_done(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def _c(self) -> GnaniSTTBatchClient:
        if self._client is None:
            raise RuntimeError("job is not attached to a client")
        return self._client

    def refresh(self) -> BatchJob:
        """Re-read status and progress from the API. Returns ``self``."""
        self._apply(self._c()._json("GET", f"{BATCH_ENDPOINT}/{self.id}"))
        return self

    def start(self) -> BatchJob:
        """Start a job created with ``start=False``."""
        self._apply(self._c()._json("POST", f"{BATCH_ENDPOINT}/{self.id}/start"))
        return self

    def cancel(self, reason: str | None = None) -> BatchJob:
        body = {"reason": reason} if reason else {}
        self._apply(self._c()._json("POST", f"{BATCH_ENDPOINT}/{self.id}/cancel", json=body))
        return self

    def wait(
        self,
        *,
        timeout: float | None = None,
        poll_interval: float = BATCH_MIN_POLL_SECONDS,
        max_poll_interval: float = 30.0,
        progress: bool = False,
        on_progress: Callable[[BatchJob], None] | None = None,
        raise_on_failure: bool = True,
    ) -> BatchJob:
        """Block until the job reaches a terminal state.

        Polls every ``poll_interval`` seconds (never below 10 s, the documented
        minimum), slowing gradually to ``max_poll_interval`` on long jobs.

        ``COMPLETED`` and ``PARTIAL_FAILURE`` return normally; check
        :attr:`BatchFile.ok` per file. ``FAILED``, ``START_FAILED`` and
        ``CANCELLED`` raise :class:`BatchJobFailedError` unless
        ``raise_on_failure=False``. Ctrl-C leaves the job running on the server.
        """
        interval = max(poll_interval, BATCH_MIN_POLL_SECONDS)
        deadline = None if timeout is None else time.monotonic() + timeout
        bar = _make_bar(self.id) if progress else None
        last = -1
        try:
            while True:
                self.refresh()
                if bar is not None:
                    bar(self)
                elif progress and self.percent != last:
                    logger.info("[STT Batch] %s %s %d%%", self.id, self.status, self.percent)
                last = self.percent
                if on_progress is not None:
                    on_progress(self)
                if self.is_done:
                    break
                if deadline is not None and time.monotonic() + interval > deadline:
                    raise BatchTimeoutError(self.id, timeout or 0.0)
                time.sleep(interval)
                interval = min(interval * 1.25, max(max_poll_interval, interval))
        except KeyboardInterrupt:
            logger.warning(
                "[STT Batch] interrupted; job %s keeps running. Resume with client.get_job(%r).",
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

    def files(self, *, status: str | None = None) -> list[BatchFile]:
        """All files in the job (follows pagination)."""
        out: list[BatchFile] = []
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"limit": 100}
            if status:
                params["status"] = status
            if cursor:
                params["cursor"] = cursor
            page = self._c()._json("GET", f"{BATCH_ENDPOINT}/{self.id}/files", params=params)
            for d in page.get("data", []):
                out.append(
                    BatchFile(
                        file_id=d["file_id"],
                        name=os.path.basename(d.get("original_path") or d["file_id"]),
                        status=d["status"],
                        duration=float(d["duration_seconds"])
                        if d.get("duration_seconds")
                        else None,
                        error=d.get("error_message"),
                        progress_percent=d.get("progress_percent", 0),
                        stage=d.get("stage"),
                        transcript_url=d.get("transcript_url"),
                        _job=self,
                    )
                )
            pagination = page.get("pagination") or {}
            cursor = pagination.get("next_cursor")
            if not pagination.get("has_more") or not cursor:
                return out

    def save(self, output_dir: str | Path, *, text_files: bool = False) -> list[Path]:
        """Write each completed file's transcript JSON to ``output_dir``.

        ``text_files=True`` also writes a plain ``.txt`` beside each. Failed
        files are skipped (see :attr:`BatchFile.error`). Returns written paths.
        """
        return _save(self.files(), output_dir, text_files)

    def _apply(self, data: dict[str, Any]) -> None:
        self.status = data.get("status", self.status)
        progress = data.get("progress") or {}
        if progress:
            self.percent = int(progress.get("percent", self.percent))
            self.total_files = progress.get("total_files", self.total_files)
            self.completed_files = progress.get("completed_files", self.completed_files)
            self.failed_files = progress.get("failed_files", self.failed_files)
        if self.is_done and self.status in SUCCESS_STATUSES:
            self.percent = 100
        self.cancel_reason = data.get("cancel_reason", self.cancel_reason)
        self.config = data.get("config", self.config)


class BatchResult:
    """What :meth:`GnaniSTTBatchClient.transcribe` returns: a finished job and its files."""

    def __init__(self, job: BatchJob, files: list[BatchFile]) -> None:
        self.job = job
        self.files = files

    def __iter__(self) -> Iterator[BatchFile]:
        return iter(self.files)

    def __getitem__(self, i: int) -> BatchFile:
        return self.files[i]

    def __len__(self) -> int:
        return len(self.files)

    @property
    def failed(self) -> list[BatchFile]:
        return [f for f in self.files if not f.ok]

    @property
    def text(self) -> str:
        """All transcripts joined, one file per paragraph."""
        return "\n\n".join(f.text for f in self.files if f.ok)

    def save(self, output_dir: str | Path, *, text_files: bool = False) -> list[Path]:
        return _save(self.files, output_dir, text_files)

    def __repr__(self) -> str:
        return (
            f"BatchResult(job={self.job.id!r}, files={len(self.files)}, failed={len(self.failed)})"
        )


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class GnaniSTTBatchClient:
    """Client for Gnani's Batch Speech-to-Text API.

    Parameters
    ----------
    api_key : str, optional
        Your API key. Falls back to the ``GNANI_API_KEY`` environment variable.
    base_url : str, optional
        Override the default API base URL.
    timeout : int, optional
        Per-request timeout in seconds for control calls. Defaults to 60.
    upload_timeout : int, optional
        Timeout for the create call, which carries the audio. Defaults to 600.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = 60,
        upload_timeout: int = 600,
    ) -> None:
        resolved = api_key or os.getenv("GNANI_API_KEY", "")
        if not resolved:
            raise AuthenticationError(
                "api_key is required. "
                "Pass it directly or set the GNANI_API_KEY environment variable."
            )
        self.api_key = resolved
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.upload_timeout = upload_timeout

    # -- high level ---------------------------------------------------------

    def transcribe(
        self,
        files: Any,
        language_code: str = "en-IN",
        *,
        timeout: float | None = None,
        progress: bool = True,
        raise_on_failure: bool = True,
        **options: Any,
    ) -> BatchResult:
        """Create, start and wait for a job, then return its files.

        ``files`` and ``options`` are those of :meth:`create_job`.
        ``timeout`` bounds the wait, not the upload.
        """
        job = self.create_job(files, language_code, **options)
        job.wait(timeout=timeout, progress=progress, raise_on_failure=raise_on_failure)
        return BatchResult(job, job.files())

    def create_job(
        self,
        files: Any,
        language_code: str = "en-IN",
        *,
        model: str = DEFAULT_BATCH_MODEL,
        diarization: bool = False,
        speakers: int | None = None,
        multi_channel: bool = False,
        denoise: bool = False,
        bias_words: str | Iterable[str] | None = None,
        bias_score: float | None = None,
        callback_url: str | None = None,
        start: bool = True,
        request_id: str | None = None,
    ) -> BatchJob:
        """Upload audio and create a job, starting it unless ``start=False``.

        Parameters
        ----------
        files
            A path, directory (searched recursively), glob pattern, ZIP, list of
            those, ``bytes``, ``(name, bytes)``, an open binary file, or public
            ``https://`` URLs. Local files and URLs cannot be mixed.
        language_code
            One code (``"hi-IN"``), several comma-separated (``"hi-IN,en-IN"``;
            the language is identified per speaker turn, the first code being
            the fallback), or ``"auto"``.
        speakers
            Most speakers to separate, 1-8 (a ceiling, not a target). Implies
            ``diarization``.
        bias_words, bias_score
            Words to bias recognition toward, and strength (0, 0.5, 1, 1.5, 2).
        callback_url
            Optional webhook for the terminal result. Polling stays the source
            of truth.
        """
        codes = _validate_language(language_code)
        config = _build_config(
            model=model,
            language_code=codes,
            diarization=diarization or speakers is not None,
            speakers=speakers,
            multi_channel=multi_channel,
            denoise=denoise,
            bias_words=bias_words,
            bias_score=bias_score,
        )
        locals_, urls = _resolve_inputs(files)
        rid = resolve_request_id(request_id)
        logger.info(
            "[STT Batch] create start | request_id=%s | files=%d", rid, len(locals_) + len(urls)
        )

        if urls:
            body: dict[str, Any] = {
                "config": config,
                "source": {"type": "cloud_storage", "auth": {"mode": "public"}, "paths": urls},
            }
            if callback_url:
                body["callback_url"] = callback_url
            data = self._json("POST", BATCH_ENDPOINT, json=body, request_id=rid)
        else:
            form: dict[str, Any] = {"config": json.dumps(config)}
            if callback_url:
                form["callback_url"] = callback_url
            handles: list[BinaryIO] = []
            try:
                parts: list[tuple[str, Any]] = []
                for item in locals_:
                    if item.path is not None:
                        fh: BinaryIO = open(item.path, "rb")  # noqa: SIM115
                        handles.append(fh)
                        parts.append(("files", (item.name, fh)))
                    else:
                        parts.append(("files", (item.name, item.data)))
                data = self._json(
                    "POST",
                    BATCH_ENDPOINT,
                    data=form,
                    files=parts,
                    timeout=self.upload_timeout,
                    request_id=rid,
                )
            finally:
                for fh in handles:
                    fh.close()

        job = BatchJob(id=data["job_id"], status=data.get("status", "CREATED"), _client=self)
        logger.info("[STT Batch] job created | job_id=%s", job.id)
        if start:
            job.start()
        return job

    def get_job(self, job_id: str) -> BatchJob:
        """Fetch an existing job, e.g. to resume waiting after a restart."""
        job = BatchJob(id=job_id, status="CREATED", _client=self)
        return job.refresh()

    def list_jobs(self, *, status: str | None = None, limit: int = 20) -> Iterator[BatchJob]:
        """Iterate your jobs, newest first, following pagination."""
        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"limit": min(max(limit, 1), 100)}
            if status:
                params["status"] = status
            if cursor:
                params["cursor"] = cursor
            page = self._json("GET", BATCH_ENDPOINT, params=params)
            for d in page.get("data", []):
                yield BatchJob(
                    id=d["job_id"],
                    status=d["status"],
                    total_files=d.get("total_files"),
                    completed_files=d.get("completed_files"),
                    failed_files=d.get("failed_files"),
                    _client=self,
                )
            pagination = page.get("pagination") or {}
            cursor = pagination.get("next_cursor")
            if not pagination.get("has_more") or not cursor:
                return

    @staticmethod
    def supported_languages() -> dict[str, str]:
        """Language codes accepted by batch (``"auto"`` is also accepted)."""
        return dict(SUPPORTED_LANGUAGES)

    # -- transport ----------------------------------------------------------

    def _json(
        self,
        method: str,
        path: str,
        *,
        request_id: str | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        headers = {
            "X-API-Key-ID": self.api_key,
            "X-API-Request-ID": resolve_request_id(request_id),
        }
        resp = requests.request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            timeout=timeout or self.timeout,
            **kwargs,
        )
        if not 200 <= resp.status_code < 300:
            logger.error("[STT Batch] %s %s failed | status=%s", method, path, resp.status_code)
            raise APIError(resp.status_code, resp.text)
        return resp.json()  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_language(language_code: str) -> str:
    raw = [c.strip() for c in language_code.split(",") if c.strip()]
    if not raw:
        raise ValueError("language_code is required")
    if "auto" in (c.lower() for c in raw):
        if len(raw) > 1:
            raise ValueError("'auto' cannot be combined with other language codes")
        return "auto"
    bad = [c for c in raw if c not in SUPPORTED_LANGUAGES]
    if bad:
        raise ValueError(
            f"Unsupported language_code {', '.join(repr(b) for b in bad)}. "
            f"Choose from: {', '.join(sorted(SUPPORTED_LANGUAGES))}, or 'auto'"
        )
    return ",".join(dict.fromkeys(raw))  # drop duplicates, keep order (first = fallback)


def _build_config(
    *,
    model: str,
    language_code: str,
    diarization: bool,
    speakers: int | None,
    multi_channel: bool,
    denoise: bool,
    bias_words: str | Iterable[str] | None,
    bias_score: float | None,
) -> dict[str, Any]:
    cfg: dict[str, Any] = {"model": model, "mode": "transcribe", "language_code": language_code}
    if diarization:
        cfg["with_diarization"] = True
    if speakers is not None:
        if not 1 <= speakers <= BATCH_MAX_SPEAKERS:
            raise ValueError(f"speakers must be between 1 and {BATCH_MAX_SPEAKERS}, got {speakers}")
        cfg["num_speakers"] = speakers
    if multi_channel:
        cfg["is_multi_channel"] = True
    if denoise:
        cfg["with_denoise"] = True
    if bias_words:
        words = (
            [w.strip() for w in bias_words.split(",") if w.strip()]
            if isinstance(bias_words, str)
            else [str(w).strip() for w in bias_words if str(w).strip()]
        )
        if len(words) > BATCH_MAX_BIAS_WORDS:
            raise ValueError(f"bias_words takes at most {BATCH_MAX_BIAS_WORDS} words")
        cfg["bias_list"] = words
    if bias_score is not None:
        if bias_score not in BATCH_BIAS_SCORES:
            raise ValueError(f"bias_score must be one of {BATCH_BIAS_SCORES}, got {bias_score}")
        cfg["bias_score"] = bias_score
    return cfg


@dataclass
class _Local:
    name: str
    path: Path | None = None
    data: bytes | None = None


def _check_local(name: str, size: int | None) -> None:
    ext = Path(name).suffix.lower()
    if ext == ".zip":
        if size is not None and size > BATCH_MAX_ZIP_BYTES:
            raise InvalidAudioError(
                f"ZIP '{name}' exceeds the {BATCH_MAX_ZIP_BYTES // 2**20} MB limit"
            )
        return
    if ext not in BATCH_SUPPORTED_EXTENSIONS:
        raise InvalidAudioError(
            f"Unsupported audio format '{ext}' for '{name}'. "
            f"Supported: {', '.join(sorted(BATCH_SUPPORTED_EXTENSIONS))}, or a .zip"
        )
    if size is not None and size > BATCH_MAX_FILE_BYTES:
        raise InvalidAudioError(
            f"'{name}' is {size / 2**20:.1f} MB; batch takes at most "
            f"{BATCH_MAX_FILE_BYTES // 2**20} MB per file"
        )


def _resolve_inputs(files: Any) -> tuple[list[_Local], list[str]]:
    """Normalise the many accepted ``files`` shapes into uploads or URLs.

    The multipart filename is always the basename: a path like ``../a/x.wav``
    on the wire is blocked by Cloudflare's WAF before it reaches any service.
    """
    if (
        isinstance(files, tuple)
        and len(files) == 2
        and isinstance(files[0], str)
        and not (isinstance(files[1], str))
    ):
        items: list[Any] = [files]
    elif isinstance(files, (str, Path, bytes)) or hasattr(files, "read"):
        items = [files]
    else:
        items = list(files)

    locals_: list[_Local] = []
    urls: list[str] = []

    for n, item in enumerate(items):
        if isinstance(item, str) and item.lower().startswith(("http://", "https://")):
            urls.append(item)
        elif isinstance(item, (str, Path)):
            for p in _expand_path(Path(item) if isinstance(item, Path) else item):
                _check_local(p.name, p.stat().st_size)
                locals_.append(_Local(name=p.name, path=p))
        elif isinstance(item, bytes):
            name = f"audio_{n}.wav"
            _check_local(name, len(item))
            locals_.append(_Local(name=name, data=item))
        elif isinstance(item, tuple) and len(item) == 2:
            name = os.path.basename(str(item[0]))
            payload = item[1].read() if hasattr(item[1], "read") else item[1]
            _check_local(name, len(payload))
            locals_.append(_Local(name=name, data=payload))
        elif hasattr(item, "read"):
            raw_name = getattr(item, "name", None)
            name = os.path.basename(raw_name) if isinstance(raw_name, str) else f"audio_{n}.wav"
            payload = item.read()
            _check_local(name, len(payload))
            locals_.append(_Local(name=name, data=payload))
        else:
            raise InvalidAudioError(f"Cannot use {type(item).__name__} as an audio input")

    if urls and locals_:
        raise ValueError("Pass either local files or public URLs in one job, not both")
    total = len(locals_) + len(urls)
    if total == 0:
        raise InvalidAudioError("No audio files given")
    if total > BATCH_MAX_FILES:
        raise InvalidAudioError(f"{total} files given; a job takes at most {BATCH_MAX_FILES}")
    return locals_, urls


def _expand_path(spec: str | Path) -> list[Path]:
    path = Path(spec)
    if path.is_dir():
        found = sorted(
            p
            for p in path.rglob("*")
            if p.is_file()
            and (p.suffix.lower() in BATCH_SUPPORTED_EXTENSIONS or p.suffix.lower() == ".zip")
        )
        if not found:
            raise InvalidAudioError(f"No audio files found in directory: {path}")
        return found
    if path.is_file():
        return [path]
    if _GLOB_CHARS.search(str(spec)):
        matches = sorted(
            Path(m) for m in _glob.glob(str(spec), recursive=True) if os.path.isfile(m)
        )
        if not matches:
            raise InvalidAudioError(f"No files match: {spec}")
        return matches
    raise InvalidAudioError(f"Audio file not found: {path}")


def _save(files: list[BatchFile], output_dir: str | Path, text_files: bool) -> list[Path]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    used: set[str] = set()
    for f in files:
        if not f.ok:
            continue
        stem = Path(f.name).stem or f.file_id
        candidate, i = stem, 1
        while candidate in used:
            i += 1
            candidate = f"{stem}_{i}"
        used.add(candidate)
        jp = out / f"{candidate}.json"
        jp.write_text(json.dumps(f.transcript, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(jp)
        if text_files:
            tp = out / f"{candidate}.txt"
            tp.write_text(f.text, encoding="utf-8")
            written.append(tp)
    return written


def _make_bar(job_id: str) -> Callable[[BatchJob | None], None] | None:
    """A tqdm bar if tqdm is installed, else a log line on each change."""
    try:
        from tqdm import tqdm  # type: ignore[import-untyped,import-not-found,unused-ignore]
    except ImportError:
        return None
    bar = tqdm(total=100, desc=f"job {job_id[:8]}", unit="%", leave=False)

    def update(job: BatchJob | None) -> None:
        if job is None:
            bar.close()
            return
        bar.n = job.percent
        bar.set_postfix_str(job.status)
        bar.refresh()

    return update
