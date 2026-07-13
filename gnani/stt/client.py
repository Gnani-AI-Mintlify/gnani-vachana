"""Core client for the Gnani Speech-to-Text API (REST and Realtime WebSocket)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, BinaryIO, Callable, Union, cast

import requests
import websockets

from gnani.stt.exceptions import (
    APIError,
    AuthenticationError,
    InvalidAudioError,
    StreamClosedError,
    StreamConnectionError,
    StreamError,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

SUPPORTED_LANGUAGES = {
    "en-IN": "English (India)",
    "hi-IN": "Hindi",
    "gu-IN": "Gujarati",
    "ta-IN": "Tamil",
    "kn-IN": "Kannada",
    "te-IN": "Telugu",
    "mr-IN": "Marathi",
    "bn-IN": "Bengali",
    "ml-IN": "Malayalam",
    "pa-IN": "Punjabi",
    "en-IN,hi-IN": "English-Hindi",
}

STREAM_SUPPORTED_LANGUAGES = {
    "bn-IN": "Bengali",
    "en-IN": "English (India)",
    "gu-IN": "Gujarati",
    "hi-IN": "Hindi",
    "kn-IN": "Kannada",
    "ml-IN": "Malayalam",
    "mr-IN": "Marathi",
    "pa-IN": "Punjabi",
    "ta-IN": "Tamil",
    "te-IN": "Telugu",
    "en-hi-IN-latn": "Hinglish (Latin script, experimental)",
    "en-hi-in-cm": "Hinglish (Code-mixed, experimental)",
}

AUTO_DETECT_LANGUAGES = ",".join(k for k in STREAM_SUPPORTED_LANGUAGES if not k.startswith("en-hi"))

SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"}

DEFAULT_BASE_URL = "https://api.vachana.ai"
STT_ENDPOINT = "/stt/v3"
STT_STREAM_ENDPOINT = "/stt/v3/stream"

SAMPLE_RATE_16K = 16_000
SAMPLE_RATE_8K = 8_000
SAMPLE_RATE_44K = 44_100
SAMPLE_RATE_48K = 48_000
# Sample rates accepted by the Realtime WebSocket (x-sample-rate header).
# See https://docs.gnani.ai/api/STT/stt-websocket (Connection Headers).
STREAM_SUPPORTED_SAMPLE_RATES = (
    SAMPLE_RATE_8K,
    SAMPLE_RATE_16K,
    SAMPLE_RATE_44K,
    SAMPLE_RATE_48K,
)
STREAM_CHUNK_SAMPLES = 512
STREAM_CHUNK_BYTES = STREAM_CHUNK_SAMPLES * 2  # 16-bit = 2 bytes per sample

# Single-language codes accepted by the REST endpoint. A comma-separated
# combination of these enables server-side auto-detection.
# See https://docs.gnani.ai/api/STT/speech-to-text
REST_SINGLE_LANGUAGES = {
    code: name for code, name in SUPPORTED_LANGUAGES.items() if "," not in code
}


def _validate_rest_language_code(language_code: str) -> None:
    """Validate a REST ``language_code``.

    Accepts a single supported code (e.g. ``"hi-IN"``), a pre-defined combo
    from ``SUPPORTED_LANGUAGES``, or any comma-separated combination of
    supported single codes (e.g. ``"en-IN,ta-IN"``) to enable auto-detection.
    """
    if language_code in SUPPORTED_LANGUAGES:
        return
    parts = [p.strip() for p in language_code.split(",") if p.strip()]
    if len(parts) >= 2 and all(p in REST_SINGLE_LANGUAGES for p in parts):
        return
    raise ValueError(
        f"Unsupported language_code '{language_code}'. "
        f"Choose from: {', '.join(sorted(REST_SINGLE_LANGUAGES))} "
        f"or a comma-separated combination of these for auto-detection."
    )


def _ws_header_kwargs(headers: dict[str, str]) -> dict[str, Any]:
    """Return the correct ``connect()`` header kwarg for the installed websockets.

    websockets >= 13 renamed the ``extra_headers`` argument to
    ``additional_headers``. Support both so the SDK works across versions,
    e.g. when another dependency pins ``websockets < 13``.
    """
    try:
        major = int(websockets.__version__.split(".", 1)[0])
    except (AttributeError, ValueError):
        major = 13
    key = "additional_headers" if major >= 13 else "extra_headers"
    return {key: headers}


# ---------------------------------------------------------------------------
# Dataclasses for structured streaming responses
# ---------------------------------------------------------------------------


@dataclass
class StreamConnectedEvent:
    """Received once immediately after the WebSocket handshake succeeds.

    Attributes
    ----------
    message : str
        Human-readable status from the server.
    timestamp : str
        ISO-8601 timestamp of the event.
    sample_rate : int
        Negotiated audio sample rate in Hz.
    chunk_size : int
        Expected chunk size in samples.
    raw : dict[str, Any]
        The full raw JSON payload from the server.
    """

    message: str
    timestamp: str
    sample_rate: int
    chunk_size: int
    raw: dict[str, Any] = field(repr=False)


@dataclass
class StreamProcessingEvent:
    """Emitted when VAD detects end-of-speech and transcription has begun.

    Attributes
    ----------
    timestamp : str
        ISO-8601 timestamp of the event.
    raw : dict[str, Any]
        The full raw JSON payload from the server.
    """

    timestamp: str
    raw: dict[str, Any] = field(repr=False)


@dataclass
class StreamTranscriptEvent:
    """Contains the transcribed text for a completed speech segment.

    Attributes
    ----------
    text : str
        The transcribed text.
    audio_duration_ms : int
        Duration of the audio segment in milliseconds.
    segment_id : str
        Unique identifier for this speech segment.
    segment_index : str
        Ordinal index of this segment within the session.
    latency : int
        Server-side processing latency in milliseconds.
    timestamp : str
        ISO-8601 timestamp of the event.
    raw : dict[str, Any]
        The full raw JSON payload from the server.
    """

    text: str
    audio_duration_ms: int
    segment_id: str
    segment_index: str
    latency: int
    timestamp: str
    raw: dict[str, Any] = field(repr=False)


@dataclass
class StreamErrorEvent:
    """Received when the server encounters an error.

    Attributes
    ----------
    message : str
        Human-readable error description.
    timestamp : str
        ISO-8601 timestamp of the event.
    raw : dict[str, Any]
        The full raw JSON payload from the server.
    """

    message: str
    timestamp: str
    raw: dict[str, Any] = field(repr=False)


StreamEvent = Union[
    StreamConnectedEvent,
    StreamProcessingEvent,
    StreamTranscriptEvent,
    StreamErrorEvent,
]


class GnaniSTTClient:
    """Client for Gnani's multilingual Speech-to-Text REST API.

    Parameters
    ----------
    api_key : str
        Your secret API key (``X-API-Key-ID``).
    base_url : str, optional
        Override the default API base URL.
    timeout : int, optional
        Request timeout in seconds. Defaults to 60.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = 60,
    ):
        resolved_key = api_key if api_key else os.getenv("GNANI_API_KEY", "")
        if not resolved_key:
            raise AuthenticationError(
                "api_key is required. "
                "Pass it directly or set the GNANI_API_KEY environment variable."
            )
        self.api_key = resolved_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _build_headers(self, request_id: str | None = None) -> dict[str, str]:
        return {
            "X-API-Key-ID": self.api_key,
            "X-API-Request-ID": request_id or f"req_{uuid.uuid4().hex[:12]}",
        }

    def transcribe(
        self,
        audio: Union[str, Path, BinaryIO],
        language_code: str = "en-IN",
        *,
        preferred_language: str | None = None,
        format: str = "verbatim",
        itn_native_numerals: bool = False,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Transcribe an audio file using Gnani STT.

        Parameters
        ----------
        audio : str | Path | file-like
            Path to an audio file, or an open file-like object (binary mode).
        language_code : str
            BCP-47 style language code. See ``SUPPORTED_LANGUAGES`` for the
            full list. Defaults to ``"en-IN"``. Pass a comma-separated list
            for auto-detection (e.g. ``"en-IN,hi-IN"``).
        preferred_language : str, optional
            Force the single-language model for this code even when multiple
            languages are specified in ``language_code``. Must be one of the
            codes in ``language_code``.
        format : str
            ``"verbatim"`` (default) returns raw spoken-form output.
            ``"transcribe"`` enables Inverse Text Normalization (ITN):
            numbers, currency, dates, and phone numbers are written in
            their conventional form. Currently supported for ``hi-IN``
            and ``en-IN`` only.
        itn_native_numerals : bool
            When ``format="transcribe"``, set ``True`` to render digits in
            the native script of the target language (e.g. ``₹५,०००``
            instead of ``₹5,000`` for Hindi). Has no effect when
            ``format="verbatim"``. Defaults to ``False``.
        request_id : str, optional
            Custom request ID for tracking. Auto-generated if omitted.

        Returns
        -------
        dict
            The parsed JSON response from the API, containing at minimum
            ``success``, ``request_id``, and ``transcript``, plus response
            metadata such as ``model``, ``processing_time``, and
            ``end_to_end_latency``.

        Raises
        ------
        InvalidAudioError
            If the file extension is not supported or the file cannot be read.
        APIError
            If the API returns a non-200 response.
        """
        _validate_rest_language_code(language_code)

        if format not in ("verbatim", "transcribe"):
            raise ValueError(f"format must be 'verbatim' or 'transcribe', got '{format}'")

        headers = self._build_headers(request_id)
        file_handle: BinaryIO | None = None
        should_close = False

        try:
            if isinstance(audio, (str, Path)):
                path = Path(audio)
                if not path.exists():
                    raise InvalidAudioError(f"Audio file not found: {path}")
                if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    raise InvalidAudioError(
                        f"Unsupported audio format '{path.suffix}'. "
                        f"Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
                    )
                file_handle = open(path, "rb")  # noqa: SIM115
                should_close = True
            else:
                file_handle = audio

            url = f"{self.base_url}{STT_ENDPOINT}"
            files = {"audio_file": file_handle}
            data: dict[str, Any] = {"language_code": language_code, "format": format}

            if preferred_language is not None:
                data["preferred_language"] = preferred_language
            if itn_native_numerals:
                data["itn_native_numerals"] = "true"

            response = requests.post(
                url,
                headers=headers,
                files=files,
                data=data,
                timeout=self.timeout,
            )
        finally:
            if should_close and file_handle is not None:
                file_handle.close()

        if response.status_code != 200:
            raise APIError(response.status_code, response.text)

        return cast("dict[str, Any]", response.json())

    def transcribe_bytes(
        self,
        audio_bytes: bytes,
        filename: str = "audio.wav",
        language_code: str = "en-IN",
        *,
        preferred_language: str | None = None,
        format: str = "verbatim",
        itn_native_numerals: bool = False,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        """Transcribe raw audio bytes.

        Parameters
        ----------
        audio_bytes : bytes
            Raw audio content.
        filename : str
            Filename hint so the server can infer the format.
        language_code : str
            Target language code.
        preferred_language : str, optional
            Force the single-language model for this code even when multiple
            languages are specified in ``language_code``.
        format : str
            ``"verbatim"`` (default) or ``"transcribe"`` (enables ITN).
        itn_native_numerals : bool
            When ``format="transcribe"``, render digits in native script.
        request_id : str, optional
            Custom request ID.

        Returns
        -------
        dict
            Parsed JSON response from the API.
        """
        _validate_rest_language_code(language_code)

        if format not in ("verbatim", "transcribe"):
            raise ValueError(f"format must be 'verbatim' or 'transcribe', got '{format}'")

        headers = self._build_headers(request_id)
        url = f"{self.base_url}{STT_ENDPOINT}"
        files = {"audio_file": (filename, audio_bytes)}
        data: dict[str, Any] = {"language_code": language_code, "format": format}

        if preferred_language is not None:
            data["preferred_language"] = preferred_language
        if itn_native_numerals:
            data["itn_native_numerals"] = "true"

        response = requests.post(
            url,
            headers=headers,
            files=files,
            data=data,
            timeout=self.timeout,
        )

        if response.status_code != 200:
            raise APIError(response.status_code, response.text)

        return cast("dict[str, Any]", response.json())

    @staticmethod
    def supported_languages() -> dict[str, str]:
        """Return a mapping of supported language codes to their names."""
        return dict(SUPPORTED_LANGUAGES)


# ---------------------------------------------------------------------------
# Realtime (WebSocket) streaming client
# ---------------------------------------------------------------------------


def _parse_stream_message(data: str) -> StreamEvent:
    """Parse a JSON message from the STT stream into a typed dataclass."""
    payload: dict[str, Any] = json.loads(data)
    msg_type = payload.get("type", "")

    if msg_type == "connected":
        config = payload.get("config", {})
        return StreamConnectedEvent(
            message=payload.get("message", ""),
            timestamp=payload.get("timestamp", ""),
            sample_rate=config.get("sample_rate", SAMPLE_RATE_16K),
            chunk_size=config.get("chunk_size", STREAM_CHUNK_SAMPLES),
            raw=payload,
        )
    elif msg_type == "processing":
        return StreamProcessingEvent(
            timestamp=payload.get("timestamp", ""),
            raw=payload,
        )
    elif msg_type == "transcript":
        return StreamTranscriptEvent(
            text=payload.get("text", ""),
            audio_duration_ms=payload.get("audio_duration_ms", 0),
            segment_id=payload.get("segment_id", ""),
            segment_index=payload.get("segment_index", ""),
            latency=payload.get("latency", 0),
            timestamp=payload.get("timestamp", ""),
            raw=payload,
        )
    elif msg_type == "error":
        return StreamErrorEvent(
            message=payload.get("message", ""),
            timestamp=payload.get("timestamp", ""),
            raw=payload,
        )
    elif msg_type in ("speech_start", "speech_end", "vad_start", "vad_end"):
        # Informational VAD lifecycle events — treat as processing signals.
        return StreamProcessingEvent(
            timestamp=payload.get("timestamp", ""),
            raw=payload,
        )
    else:
        return StreamErrorEvent(
            message=f"Unknown message type: {msg_type}",
            timestamp=payload.get("timestamp", ""),
            raw=payload,
        )


class GnaniSTTStreamClient:
    """Async client for Gnani's Realtime Speech-to-Text WebSocket API.

    Streams raw PCM audio to the server and receives live transcription
    events as speech segments are detected by server-side VAD.

    Parameters
    ----------
    api_key : str
        Your API key (sent as ``x-api-key-id`` header).
    language_code : str
        BCP-47 language code for transcription. Use a single code like
        ``"hi-IN"`` or pass ``GnaniSTTStreamClient.AUTO_DETECT`` for
        automatic language detection. Defaults to ``"en-IN"``.
    sample_rate : int
        Audio sample rate in Hz. One of ``8000``, ``16000``, ``44100``, or
        ``48000``. Defaults to ``16000``. Note the PCM frame spec (512 samples
        / 1024 bytes) is defined for 8 kHz and 16 kHz.
    base_url : str, optional
        Override the default WebSocket base URL.
    preferred_language : str, optional
        Force the single-language model for this code even when multiple
        languages are specified in ``language_code``. Sent as the
        ``preferred_language`` connection header.
    format : str
        ``"verbatim"`` (default) or ``"transcribe"`` (enables ITN).
    itn_native_numerals : bool
        When ``format="transcribe"``, render digits in native script.

    Examples
    --------
    Basic usage with an async context manager::

        async with GnaniSTTStreamClient(api_key="key") as stream:
            async for event in stream:
                if isinstance(event, StreamTranscriptEvent):
                    print(event.text)

    Sending audio from a file::

        async with GnaniSTTStreamClient(api_key="key") as stream:
            with open("audio.pcm", "rb") as f:
                while chunk := f.read(1024):
                    await stream.send_audio(chunk)
                    await asyncio.sleep(0.032)  # ~real-time pacing
            results = await stream.close()
    """

    AUTO_DETECT = AUTO_DETECT_LANGUAGES

    def __init__(
        self,
        api_key: str | None = None,
        language_code: str = "en-IN",
        *,
        sample_rate: int = SAMPLE_RATE_16K,
        base_url: str = DEFAULT_BASE_URL,
        preferred_language: str | None = None,
        format: str = "verbatim",
        itn_native_numerals: bool = False,
    ):
        resolved_key = api_key if api_key else os.getenv("GNANI_API_KEY", "")
        if not resolved_key:
            raise AuthenticationError(
                "api_key is required. Pass it directly or set the "
                "GNANI_API_KEY environment variable."
            )
        self.api_key = resolved_key

        if sample_rate not in STREAM_SUPPORTED_SAMPLE_RATES:
            allowed = ", ".join(str(r) for r in STREAM_SUPPORTED_SAMPLE_RATES)
            raise ValueError(f"sample_rate must be one of {allowed}, got {sample_rate}")

        # Allow auto-detect string or any single supported code
        if (
            language_code != AUTO_DETECT_LANGUAGES
            and language_code not in STREAM_SUPPORTED_LANGUAGES
        ):
            raise ValueError(
                f"Unsupported language_code '{language_code}'. "
                f"Choose from: {', '.join(sorted(STREAM_SUPPORTED_LANGUAGES))} "
                f"or use GnaniSTTStreamClient.AUTO_DETECT for auto-detection."
            )

        if format not in ("verbatim", "transcribe"):
            raise ValueError(f"format must be 'verbatim' or 'transcribe', got '{format}'")

        self.language_code = language_code
        self.sample_rate = sample_rate
        self.preferred_language = preferred_language
        self.format = format
        self.itn_native_numerals = itn_native_numerals

        ws_scheme = "wss" if base_url.startswith("https") else "ws"
        host = base_url.replace("https://", "").replace("http://", "").rstrip("/")
        self._ws_url = f"{ws_scheme}://{host}{STT_STREAM_ENDPOINT}"

        self._ws: websockets.ClientConnection | None = None
        self._connected_event: StreamConnectedEvent | None = None
        self._receive_task: asyncio.Task | None = None
        self._events: asyncio.Queue[StreamEvent | None] = asyncio.Queue()
        self._transcripts: list[StreamTranscriptEvent] = []

    @property
    def is_connected(self) -> bool:
        """``True`` if the WebSocket connection is open."""
        if self._ws is None:
            return False

        # websockets<=11 exposed `.open`; newer versions expose `.state`.
        if hasattr(self._ws, "open"):
            return bool(self._ws.open)
        if hasattr(self._ws, "closed"):
            return not bool(self._ws.closed)

        state = getattr(self._ws, "state", None)
        state_name = getattr(state, "name", None)
        if isinstance(state_name, str):
            return state_name.upper() == "OPEN"

        # Fallback for unknown client implementations.
        return True

    @property
    def connected_config(self) -> StreamConnectedEvent | None:
        """The ``connected`` event received after handshake, or ``None``."""
        return self._connected_event

    @property
    def transcripts(self) -> list[StreamTranscriptEvent]:
        """All transcript events received so far in this session."""
        return list(self._transcripts)

    # -- Connection lifecycle ------------------------------------------------

    async def connect(self) -> StreamConnectedEvent:
        """Open the WebSocket connection and wait for the ``connected`` event.

        Returns
        -------
        StreamConnectedEvent
            The server's initial configuration message.

        Raises
        ------
        StreamConnectionError
            If the connection cannot be established.
        """
        headers: dict[str, str] = {
            "x-api-key-id": self.api_key,
            "lang_code": self.language_code,
            "x-sample-rate": str(self.sample_rate),
        }
        if self.format != "verbatim":
            headers["x-format"] = self.format
        if self.preferred_language is not None:
            headers["preferred_language"] = self.preferred_language
        if self.itn_native_numerals:
            headers["itn_native_numerals"] = "true"

        try:
            self._ws = await websockets.connect(
                self._ws_url,
                **_ws_header_kwargs(headers),
                ping_interval=20,
                ping_timeout=20,
                close_timeout=10,
            )
        except Exception as exc:
            raise StreamConnectionError(f"Failed to connect to {self._ws_url}: {exc}") from exc

        self._transcripts.clear()
        self._events = asyncio.Queue()
        self._receive_task = asyncio.create_task(self._receive_loop())

        # Wait for the initial "connected" message
        first = await self._events.get()
        if isinstance(first, StreamConnectedEvent):
            self._connected_event = first
            return first
        elif isinstance(first, StreamErrorEvent):
            await self._close_ws()
            raise StreamConnectionError(f"Server error on connect: {first.message}")
        else:
            await self._close_ws()
            raise StreamConnectionError("Unexpected first message from server")

    async def send_audio(self, audio_chunk: bytes) -> None:
        """Send a binary audio frame to the server.

        Each frame should be exactly **1024 bytes** (512 PCM 16-bit samples,
        corresponding to 32 ms at 16 kHz or 64 ms at 8 kHz). Frames should
        be sent at a steady real-time cadence for best VAD accuracy.

        Parameters
        ----------
        audio_chunk : bytes
            Raw PCM audio data (signed 16-bit little-endian, mono).

        Raises
        ------
        StreamClosedError
            If the connection is not open.
        """
        if not self.is_connected:
            raise StreamClosedError("Stream is not connected. Call connect() first.")
        ws = self._ws
        if ws is None:
            raise StreamClosedError("Stream is not connected. Call connect() first.")
        await ws.send(audio_chunk)

    async def close(self) -> list[StreamTranscriptEvent]:
        """Gracefully close the WebSocket connection.

        Returns
        -------
        list[StreamTranscriptEvent]
            All transcript events received during this session.
        """
        await self._close_ws()
        return list(self._transcripts)

    # -- Async iteration -----------------------------------------------------

    def events(self) -> AsyncIterator[StreamEvent]:
        """Return an async iterator over all incoming stream events.

        Yields each ``StreamConnectedEvent``, ``StreamProcessingEvent``,
        ``StreamTranscriptEvent``, or ``StreamErrorEvent`` as it arrives.
        Iteration ends when the connection closes.

        Usage::

            async for event in stream.events():
                if isinstance(event, StreamTranscriptEvent):
                    print(event.text)
        """
        return self._event_iterator()

    async def _event_iterator(self) -> AsyncIterator[StreamEvent]:
        while True:
            event = await self._events.get()
            if event is None:
                break
            yield event

    def __aiter__(self) -> AsyncIterator[StreamEvent]:
        """Iterate over stream events. Equivalent to ``stream.events()``."""
        return self._event_iterator()

    # -- Async context manager -----------------------------------------------

    async def __aenter__(self) -> GnaniSTTStreamClient:
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    # -- Callback-based convenience ------------------------------------------

    async def stream_audio(
        self,
        audio_source: AsyncIterator[bytes] | BinaryIO,
        *,
        on_transcript: Callable[[StreamTranscriptEvent], None] | None = None,
        on_processing: Callable[[StreamProcessingEvent], None] | None = None,
        on_error: Callable[[StreamErrorEvent], None] | None = None,
        chunk_size: int = STREAM_CHUNK_BYTES,
        realtime_pace: bool = True,
    ) -> list[StreamTranscriptEvent]:
        """Stream audio and collect transcripts with optional callbacks.

        This is a high-level convenience method that handles sending audio
        and consuming server events concurrently.

        Parameters
        ----------
        audio_source : AsyncIterator[bytes] | file-like
            An async iterator yielding audio chunks, or a synchronous
            file-like object opened in binary mode.
        on_transcript : callable, optional
            Called with each ``StreamTranscriptEvent``.
        on_processing : callable, optional
            Called with each ``StreamProcessingEvent``.
        on_error : callable, optional
            Called with each ``StreamErrorEvent``.
        chunk_size : int
            Bytes per audio frame. Defaults to 1024 (512 samples x 2 bytes).
        realtime_pace : bool
            If ``True`` (default), sleep between frames to approximate
            real-time audio pacing based on the configured sample rate.

        Returns
        -------
        list[StreamTranscriptEvent]
            All transcripts received during the stream.
        """
        if not self.is_connected:
            raise StreamClosedError("Stream is not connected. Call connect() first.")

        seconds_per_chunk = chunk_size / 2 / self.sample_rate

        async def _send() -> None:
            if hasattr(audio_source, "__aiter__"):
                async for chunk in audio_source:
                    if not self.is_connected:
                        break
                    await self.send_audio(chunk)
                    if realtime_pace:
                        await asyncio.sleep(seconds_per_chunk)
            else:
                while True:
                    chunk = audio_source.read(chunk_size)
                    if not chunk:
                        break
                    if not self.is_connected:
                        break
                    await self.send_audio(chunk)
                    if realtime_pace:
                        await asyncio.sleep(seconds_per_chunk)

        async def _receive() -> None:
            async for event in self.events():
                if isinstance(event, StreamTranscriptEvent) and on_transcript:
                    on_transcript(event)
                elif isinstance(event, StreamProcessingEvent) and on_processing:
                    on_processing(event)
                elif isinstance(event, StreamErrorEvent):
                    if on_error:
                        on_error(event)
                    else:
                        raise StreamError(event.message, event.timestamp)

        send_task = asyncio.create_task(_send())
        recv_task = asyncio.create_task(_receive())

        await send_task
        # Allow remaining server responses to arrive
        await asyncio.sleep(1.0)
        await self.close()
        recv_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await recv_task

        return list(self._transcripts)

    # -- Internal helpers ----------------------------------------------------

    async def _receive_loop(self) -> None:
        """Background task that reads messages from the WebSocket."""
        ws = self._ws
        if ws is None:
            return
        try:
            async for raw_msg in ws:
                if isinstance(raw_msg, str):
                    event = _parse_stream_message(raw_msg)
                    if isinstance(event, StreamTranscriptEvent):
                        self._transcripts.append(event)
                    await self._events.put(event)
        except websockets.ConnectionClosed:
            pass
        except Exception as exc:
            await self._events.put(
                StreamErrorEvent(
                    message=f"Receive error: {exc}",
                    timestamp="",
                    raw={"type": "error", "message": str(exc)},
                )
            )
        finally:
            await self._events.put(None)

    async def _close_ws(self) -> None:
        """Close the WebSocket and cancel the receive loop."""
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receive_task
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None

    @staticmethod
    def supported_languages() -> dict[str, str]:
        """Return a mapping of supported streaming language codes to names."""
        return dict(STREAM_SUPPORTED_LANGUAGES)
