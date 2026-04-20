"""Custom exceptions for the Gnani STT client."""

from __future__ import annotations


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
