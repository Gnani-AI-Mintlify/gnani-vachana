"""Custom exceptions for the Gnani TTS client."""

from __future__ import annotations


class GnaniTTSError(Exception):
    """Base exception for all Gnani TTS errors."""


class AuthenticationError(GnaniTTSError):
    """Raised when API authentication fails (missing or invalid credentials)."""


class APIError(GnaniTTSError):
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


class StreamConnectionError(GnaniTTSError):
    """Raised when the WebSocket connection to the TTS stream cannot be established."""


class StreamClosedError(GnaniTTSError):
    """Raised when an operation is attempted on a closed stream connection."""


class StreamError(GnaniTTSError):
    """Raised when the TTS stream server sends an error message."""
