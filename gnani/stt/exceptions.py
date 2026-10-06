"""Custom exceptions for the Gnani STT client."""

from __future__ import annotations

import json
from typing import Any


class GnaniSTTError(Exception):
    """Base exception for all Gnani STT errors."""


class AuthenticationError(GnaniSTTError):
    """Raised when API authentication fails (missing or invalid credentials)."""


class InvalidAudioError(GnaniSTTError):
    """Raised when the provided audio file is invalid or unsupported."""


class APIError(GnaniSTTError):
    """Raised when the Gnani API returns a non-success response.

    Attributes
    ----------
    status_code : int
        HTTP status code returned by the API.
    body : str
        Raw response body from the API.
    """

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code: int = status_code
        self.body: str = body
        super().__init__(f"HTTP {status_code}: {body}")

    @property
    def error_code(self) -> str | None:
        """Machine-readable ``error_code`` from the response body, if it has one.

        Batch STT errors carry codes such as ``TOO_MANY_FILES`` or
        ``FILE_TOO_LARGE``, either at the top level or nested under ``detail``.
        """
        try:
            data: Any = json.loads(self.body)
        except ValueError:
            return None
        if isinstance(data, dict):
            detail = data.get("detail")
            if isinstance(detail, dict):
                data = detail
            code = data.get("error_code") or data.get("code")
            return str(code) if code else None
        return None


class StreamConnectionError(GnaniSTTError):
    """Raised when the WebSocket connection to the STT stream cannot be established."""


class StreamClosedError(GnaniSTTError):
    """Raised when an operation is attempted on a closed stream connection."""


class StreamError(GnaniSTTError):
    """Raised when the STT stream server sends an error message.

    Attributes
    ----------
    timestamp : str | None
        ISO-8601 timestamp of the server error, if available.
    """

    def __init__(self, message: str, timestamp: str | None = None) -> None:
        self.timestamp: str | None = timestamp
        super().__init__(message)


class BatchTimeoutError(GnaniSTTError):
    """Raised when waiting for a batch job exceeds ``timeout``.

    The job keeps running; resume with ``client.get_job(job_id)``.
    """

    def __init__(self, job_id: str, timeout: float) -> None:
        self.job_id: str = job_id
        self.timeout: float = timeout
        super().__init__(
            f"Batch job {job_id} not finished after {timeout:g}s (it is still running)"
        )


class BatchJobFailedError(GnaniSTTError):
    """Raised when a batch job ends ``FAILED``, ``START_FAILED`` or ``CANCELLED``."""

    def __init__(self, job_id: str, status: str, reason: str | None = None) -> None:
        self.job_id: str = job_id
        self.status: str = status
        self.reason: str | None = reason
        super().__init__(f"Batch job {job_id} ended {status}" + (f": {reason}" if reason else ""))
