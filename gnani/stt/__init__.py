"""Gnani STT - Python client for Gnani's multilingual Speech-to-Text API."""

from gnani.stt.client import (
    SAMPLE_RATE_8K,
    SAMPLE_RATE_16K,
    STREAM_CHUNK_BYTES,
    STREAM_CHUNK_SAMPLES,
    STREAM_SUPPORTED_LANGUAGES,
    SUPPORTED_LANGUAGES,
    GnaniSTTClient,
    GnaniSTTStreamClient,
    StreamConnectedEvent,
    StreamErrorEvent,
    StreamEvent,
    StreamProcessingEvent,
    StreamTranscriptEvent,
)
from gnani.stt.exceptions import (
    APIError,
    AuthenticationError,
    GnaniSTTError,
    InvalidAudioError,
    StreamClosedError,
    StreamConnectionError,
    StreamError,
)

__version__ = "0.5.1"
__all__ = [
    "SAMPLE_RATE_8K",
    "SAMPLE_RATE_16K",
    "STREAM_CHUNK_BYTES",
    "STREAM_CHUNK_SAMPLES",
    "STREAM_SUPPORTED_LANGUAGES",
    "SUPPORTED_LANGUAGES",
    "APIError",
    "AuthenticationError",
    "GnaniSTTClient",
    "GnaniSTTError",
    "GnaniSTTStreamClient",
    "InvalidAudioError",
    "StreamClosedError",
    "StreamConnectedEvent",
    "StreamConnectionError",
    "StreamError",
    "StreamErrorEvent",
    "StreamEvent",
    "StreamProcessingEvent",
    "StreamTranscriptEvent",
]
