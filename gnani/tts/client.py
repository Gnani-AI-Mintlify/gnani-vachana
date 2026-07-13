"""Core client for Gnani Text-to-Speech API (REST, SSE Streaming, Realtime WebSocket)."""

from __future__ import annotations

import base64
import contextlib
import json
import os
import struct
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Union

import requests
import websockets

from gnani.tts.exceptions import (
    APIError,
    AuthenticationError,
    StreamConnectionError,
    StreamError,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

DEFAULT_BASE_URL = "https://api.vachana.ai"
TTS_ENDPOINT = "/api/v1/tts/inference"
TTS_SSE_ENDPOINT = "/api/v1/tts/sse"
TTS_WS_ENDPOINT = "/api/v1/tts"

DEFAULT_MODEL = "vachana-voice-v3"

SUPPORTED_VOICES = frozenset(
    {
        "Pranav",
        "Kaveri",
        "Shubhra",
        "Deepak",
    }
)

SUPPORTED_ENCODINGS = frozenset({"linear_pcm", "oggopus"})
SUPPORTED_CONTAINERS = frozenset({"raw", "mp3", "wav", "mulaw", "ogg"})
SUPPORTED_BITRATES = frozenset({"96k", "128k", "192k"})
SUPPORTED_MODELS = frozenset({"vachana-voice-v3"})


# ---------------------------------------------------------------------------
# Request / config dataclasses
# ---------------------------------------------------------------------------


@dataclass
class AudioConfig:
    """Audio output configuration for TTS requests.

    Attributes
    ----------
    sample_rate : int
        Sample rate in Hz (8000–44100). Defaults to ``44100``.
    encoding : str
        Audio encoding. One of ``"linear_pcm"`` or ``"oggopus"``.
        Defaults to ``"linear_pcm"``.
    num_channels : int
        Number of audio channels (1–8). Defaults to ``1`` (mono).
    sample_width : int
        Sample width in bytes (1–4). Defaults to ``2`` (16-bit).
    container : str
        Audio container. One of ``"raw"``, ``"mp3"``, ``"wav"``,
        ``"mulaw"``, or ``"ogg"``. Defaults to ``"wav"``.
    bitrate : str, optional
        MP3 bitrate — ``"96k"``, ``"128k"``, or ``"192k"``.
        Only relevant when ``container="mp3"``.
    """

    sample_rate: int = 44100
    encoding: str = "linear_pcm"
    num_channels: int = 1
    sample_width: int = 2
    container: str = "wav"
    bitrate: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-safe dict for the API request body."""
        d: dict[str, Any] = {
            "sample_rate": self.sample_rate,
            "encoding": self.encoding,
            "num_channels": self.num_channels,
            "sample_width": self.sample_width,
            "container": self.container,
        }
        if self.bitrate is not None:
            d["bitrate"] = self.bitrate
        return d


@dataclass
class SpeakerEmbedding:
    """Optional speaker embedding for voice cloning.

    When provided, ``voice`` is ignored and the embedding is used instead.

    Attributes
    ----------
    embedding : str
        Base64-encoded or raw embedding string.
    shape : list[int]
        Tensor shape of the embedding (e.g. ``[1, 768]``).
    dtype : str
        Dtype of the embedding tensor (e.g. ``"torch.bfloat16"``).
    """

    embedding: str
    shape: list[int]
    dtype: str = "torch.bfloat16"

    def to_dict(self) -> dict[str, Any]:
        return {"embedding": self.embedding, "shape": self.shape, "dtype": self.dtype}


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


def _build_request_body(
    text: str,
    voice: str | None,
    model: str,
    audio_config: AudioConfig,
    speaker_embedding: SpeakerEmbedding | None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "text": text,
        "model": model,
        "audio_config": audio_config.to_dict(),
    }
    if speaker_embedding is not None:
        body["speaker_embedding"] = speaker_embedding.to_dict()
    elif voice is not None:
        body["voice"] = voice
    return body


def _validate_voice(voice: str | None) -> None:
    if voice is not None and voice not in SUPPORTED_VOICES:
        raise ValueError(
            f"Unsupported voice '{voice}'. Supported voices: {', '.join(sorted(SUPPORTED_VOICES))}"
        )


def _validate_model(model: str) -> None:
    if model not in SUPPORTED_MODELS:
        raise ValueError(
            f"Unsupported model '{model}'. Choose from: {', '.join(sorted(SUPPORTED_MODELS))}"
        )


def _save_audio(audio: bytes, output_file: str | Path) -> Path:
    """Write *audio* bytes to *output_file*, creating parent dirs if needed.

    Returns the resolved :class:`~pathlib.Path` that was written.
    """
    dest = Path(output_file)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(audio)
    return dest


# ---------------------------------------------------------------------------
# REST client
# ---------------------------------------------------------------------------


class GnaniTTSClient:
    """Synchronous client for Gnani's Text-to-Speech REST API.

    Returns the complete synthesised audio in a single response. Best for
    batch processing or short texts. For lower-latency playback use
    :class:`GnaniTTSStreamClient` (SSE) or :class:`GnaniTTSRealtimeClient`
    (WebSocket).

    Parameters
    ----------
    api_key : str
        Your API key (``X-API-Key-ID``). Falls back to the
        ``GNANI_API_KEY`` environment variable.
    base_url : str, optional
        Override the default API base URL.
    timeout : int, optional
        Request timeout in seconds. Defaults to ``60``.

    Examples
    --------
    ::

        client = GnaniTTSClient(api_key="key")
        audio_bytes = client.synthesize("नमस्ते, आप कैसे हैं?", voice="Pranav")
        with open("output.wav", "wb") as f:
            f.write(audio_bytes)
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
                "api_key is required. Pass it directly or set the "
                "GNANI_API_KEY environment variable."
            )
        self.api_key = resolved_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _build_headers(self) -> dict[str, str]:
        return {
            "X-API-Key-ID": self.api_key,
            "Content-Type": "application/json",
        }

    def synthesize(
        self,
        text: str,
        voice: str | None = "Pranav",
        *,
        model: str = DEFAULT_MODEL,
        audio_config: AudioConfig | None = None,
        speaker_embedding: SpeakerEmbedding | None = None,
        output_file: str | Path | None = None,
    ) -> bytes:
        """Synthesise speech and return the full audio as bytes.

        Parameters
        ----------
        text : str
            The text to synthesise.
        voice : str, optional
            Pre-defined voice ID (e.g. ``"Pranav"``, ``"Kaveri"``).
            See https://docs.gnani.ai/api/TTS/tts-sse#available-voices
            Ignored when ``speaker_embedding`` is provided. Defaults to ``"Pranav"``.
        model : str
            TTS model to use. Defaults to ``"vachana-voice-v3"``.
        audio_config : AudioConfig, optional
            Output audio configuration. Defaults to 44100 Hz WAV with linear PCM.
        speaker_embedding : SpeakerEmbedding, optional
            Voice cloning embedding. When provided, ``voice`` is ignored.
        output_file : str or Path, optional
            If provided, the synthesised audio is written to this file path.
            Parent directories are created automatically.

        Returns
        -------
        bytes
            Raw audio data in the format specified by ``audio_config``.

        Raises
        ------
        APIError
            If the API returns a non-200 response.
        """
        _validate_model(model)
        _validate_voice(voice)

        cfg = audio_config or AudioConfig()
        body = _build_request_body(text, voice, model, cfg, speaker_embedding)

        response = requests.post(
            f"{self.base_url}{TTS_ENDPOINT}",
            headers=self._build_headers(),
            json=body,
            timeout=self.timeout,
        )

        if response.status_code != 200:
            raise APIError(response.status_code, response.text)

        audio = response.content
        if output_file is not None:
            _save_audio(audio, output_file)
        return audio

    @staticmethod
    def supported_voices() -> list[str]:
        """Return the list of supported voice IDs."""
        return sorted(SUPPORTED_VOICES)


# ---------------------------------------------------------------------------
# SSE Streaming client
# ---------------------------------------------------------------------------


_WAV_HEADER_SIZE = 44


def _strip_wav_header(data: bytes) -> bytes:
    """Strip the RIFF/WAV header if present, returning only PCM samples."""
    if len(data) > _WAV_HEADER_SIZE and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return data[_WAV_HEADER_SIZE:]
    return data


def _build_wav_header(
    pcm_size: int,
    sample_rate: int = 16000,
    num_channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    """Build a minimal WAV header for raw PCM data."""
    byte_rate = sample_rate * num_channels * sample_width
    block_align = num_channels * sample_width
    data_size = pcm_size
    riff_size = 36 + data_size
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        riff_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        num_channels,
        sample_rate,
        byte_rate,
        block_align,
        sample_width * 8,
        b"data",
        data_size,
    )


def _parse_sse_lines(response: requests.Response) -> Iterator[bytes]:
    """Parse the SSE TTS stream and yield decoded audio chunks.

    The server sends SSE events with JSON payloads:

    1. ``event: start`` / ``{"status": "streaming_started", ...}`` — skipped
    2. ``event: chunk`` / ``{"chunk_index": N, "audio": "<base64>"}`` — audio
    3. ``event: complete`` / ``{"chunk_index": N, "audio": "", "is_final": true}``

    Each ``audio`` field decodes to a complete WAV file (RIFF header + PCM).
    This function strips per-chunk WAV headers and yields only raw PCM.
    The caller (e.g. :meth:`GnaniTTSStreamClient.synthesize`) is responsible
    for wrapping the collected PCM in a single valid WAV header.
    """
    buf = ""
    for raw_line in response.iter_lines(decode_unicode=True):
        if not raw_line:
            continue
        line = raw_line.decode() if isinstance(raw_line, bytes) else raw_line

        if line.startswith("data:"):
            line = line[len("data:") :].strip()
        if line.startswith("event:"):
            continue

        buf += line
        try:
            payload = json.loads(buf)
        except json.JSONDecodeError:
            continue
        buf = ""

        if "error" in payload or payload.get("status") == "error":
            raise StreamError(payload.get("message", payload.get("error", json.dumps(payload))))

        if payload.get("status") == "streaming_started":
            continue

        if payload.get("is_final", False):
            audio_b64 = payload.get("audio", "")
            if audio_b64:
                yield _strip_wav_header(base64.b64decode(audio_b64))
            return

        audio_b64 = payload.get("audio", "")
        if not audio_b64:
            continue

        yield _strip_wav_header(base64.b64decode(audio_b64))


class GnaniTTSStreamClient:
    """Synchronous SSE streaming client for Gnani's Text-to-Speech API.

    Streams audio chunks as they are generated, allowing playback to start
    before the full audio is ready. Lower latency than the REST client.

    Parameters
    ----------
    api_key : str
        Your API key (``X-API-Key-ID``). Falls back to the
        ``GNANI_API_KEY`` environment variable.
    base_url : str, optional
        Override the default API base URL.
    timeout : int, optional
        Request timeout in seconds. Defaults to ``60``.

    Examples
    --------
    Save a complete WAV file::

        client = GnaniTTSStreamClient(api_key="key")
        audio = client.synthesize("Hello!", voice="Pranav", output_file="output.wav")
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
                "api_key is required. Pass it directly or set the "
                "GNANI_API_KEY environment variable."
            )
        self.api_key = resolved_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _build_headers(self) -> dict[str, str]:
        return {
            "X-API-Key-ID": self.api_key,
            "Content-Type": "application/json",
        }

    def synthesize_stream(
        self,
        text: str,
        voice: str | None = "Pranav",
        *,
        model: str = DEFAULT_MODEL,
        audio_config: AudioConfig | None = None,
        speaker_embedding: SpeakerEmbedding | None = None,
    ) -> Iterator[bytes]:
        """Synthesise speech and yield raw PCM audio chunks.

        Each chunk contains raw PCM samples (no WAV header). Use
        :meth:`synthesize` to get a complete WAV file instead.

        Parameters
        ----------
        text : str
            The text to synthesise.
        voice : str, optional
            Pre-defined voice ID. Defaults to ``"Pranav"``.
        model : str
            TTS model to use. Defaults to ``"vachana-voice-v3"``.
        audio_config : AudioConfig, optional
            Output audio configuration.
        speaker_embedding : SpeakerEmbedding, optional
            Voice cloning embedding. When provided, ``voice`` is ignored.

        Yields
        ------
        bytes
            Raw PCM audio chunks as they arrive.

        Raises
        ------
        APIError
            If the API returns a non-200 response.
        StreamError
            If the server sends an error event.
        """
        _validate_model(model)
        _validate_voice(voice)

        cfg = audio_config or AudioConfig()
        body = _build_request_body(text, voice, model, cfg, speaker_embedding)

        response = requests.post(
            f"{self.base_url}{TTS_SSE_ENDPOINT}",
            headers=self._build_headers(),
            json=body,
            stream=True,
            timeout=self.timeout,
        )

        if response.status_code != 200:
            raise APIError(response.status_code, response.text)

        yield from _parse_sse_lines(response)

    def synthesize(
        self,
        text: str,
        voice: str | None = "Pranav",
        *,
        model: str = DEFAULT_MODEL,
        audio_config: AudioConfig | None = None,
        speaker_embedding: SpeakerEmbedding | None = None,
        output_file: str | Path | None = None,
    ) -> bytes:
        """Synthesise speech and return the complete audio as a valid WAV.

        Convenience wrapper around :meth:`synthesize_stream` that collects
        all raw PCM chunks and wraps them in a single WAV header.

        Parameters
        ----------
        output_file : str or Path, optional
            If provided, the complete audio is written to this file.
            Parent directories are created automatically.
        """
        cfg = audio_config or AudioConfig()
        pcm = b"".join(
            self.synthesize_stream(
                text,
                voice,
                model=model,
                audio_config=audio_config,
                speaker_embedding=speaker_embedding,
            )
        )
        audio = (
            _build_wav_header(
                len(pcm),
                cfg.sample_rate,
                cfg.num_channels,
                cfg.sample_width,
            )
            + pcm
        )
        if output_file is not None:
            _save_audio(audio, output_file)
        return audio

    @staticmethod
    def supported_voices() -> list[str]:
        """Return the list of supported voice IDs."""
        return sorted(SUPPORTED_VOICES)


# ---------------------------------------------------------------------------
# Realtime WebSocket client
# ---------------------------------------------------------------------------


@dataclass
class TTSStartEvent:
    """Emitted when the server begins streaming audio.

    Attributes
    ----------
    request_id : str
        Unique identifier for this TTS request.
    message : str
        Human-readable status message from the server.
    """

    request_id: str
    message: str


@dataclass
class TTSAudioChunkEvent:
    """A binary audio chunk received from the TTS WebSocket stream.

    Attributes
    ----------
    data : bytes
        Raw audio bytes for this chunk.
    chunk_index : int
        Zero-based index of this chunk within the response.
    is_final : bool
        ``True`` if this is the last audio-bearing chunk.
    """

    data: bytes
    chunk_index: int
    is_final: bool = False


@dataclass
class TTSCompletedEvent:
    """Emitted when the server has finished streaming all audio.

    Attributes
    ----------
    request_id : str
        Unique identifier for this TTS request.
    total_chunks : int
        Total number of audio chunks received.
    """

    request_id: str
    total_chunks: int


TTSStreamEvent = Union[TTSStartEvent, TTSAudioChunkEvent, TTSCompletedEvent]


class GnaniTTSRealtimeClient:
    """Async WebSocket client for Gnani's Realtime Text-to-Speech API.

    Provides the lowest latency TTS by streaming audio over a persistent
    WebSocket connection. Audio chunks are yielded as binary frames
    arrive from the server.

    Parameters
    ----------
    api_key : str
        Your API key (``X-API-Key-ID``). Falls back to the
        ``GNANI_API_KEY`` environment variable.
    base_url : str, optional
        Override the default API base URL.

    Examples
    --------
    Using as an async context manager::

        async with GnaniTTSRealtimeClient(api_key="key") as client:
            with open("output.wav", "wb") as f:
                async for chunk in client.synthesize(
                    "नमस्ते, आप कैसे हैं?", voice="Pranav"
                ):
                    f.write(chunk)

    Collect full audio in one call::

        async with GnaniTTSRealtimeClient(api_key="key") as client:
            audio = await client.synthesize_and_collect("Hello!", voice="Pranav")
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
    ):
        resolved_key = api_key if api_key else os.getenv("GNANI_API_KEY", "")
        if not resolved_key:
            raise AuthenticationError(
                "api_key is required. Pass it directly or set the "
                "GNANI_API_KEY environment variable."
            )
        self.api_key = resolved_key

        ws_scheme = "wss" if base_url.startswith("https") else "ws"
        host = base_url.replace("https://", "").replace("http://", "").rstrip("/")
        self._ws_url = f"{ws_scheme}://{host}{TTS_WS_ENDPOINT}"

    def _build_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-API-Key-ID": self.api_key,
        }

    async def synthesize(
        self,
        text: str,
        voice: str | None = "Pranav",
        *,
        model: str = DEFAULT_MODEL,
        audio_config: AudioConfig | None = None,
        speaker_embedding: SpeakerEmbedding | None = None,
    ) -> AsyncIterator[bytes]:
        """Stream audio chunks for the given text via WebSocket.

        Opens a new WebSocket connection, sends the TTS request, and
        yields binary audio chunks as they arrive. The connection is
        closed automatically when the server finishes.

        Parameters
        ----------
        text : str
            The text to synthesise.
        voice : str, optional
            Pre-defined voice ID. Defaults to ``"Pranav"``.
        model : str
            TTS model to use. Defaults to ``"vachana-voice-v3"``.
        audio_config : AudioConfig, optional
            Output audio configuration.
        speaker_embedding : SpeakerEmbedding, optional
            Voice cloning embedding (included alongside ``voice``).

        Yields
        ------
        bytes
            Raw audio chunks as they arrive from the server.

        Raises
        ------
        StreamConnectionError
            If the WebSocket connection cannot be established.
        """
        _validate_model(model)
        _validate_voice(voice)

        cfg = audio_config or AudioConfig()
        body: dict[str, Any] = {
            "text": text,
            "voice": voice,
            "model": model,
            "audio_config": cfg.to_dict(),
        }
        if speaker_embedding is not None:
            body["speaker_embedding"] = speaker_embedding.to_dict()

        try:
            ws = await websockets.connect(
                self._ws_url,
                **_ws_header_kwargs(self._build_headers()),
                ping_interval=20,
                ping_timeout=20,
                close_timeout=10,
            )
        except Exception as exc:
            raise StreamConnectionError(f"Failed to connect to {self._ws_url}: {exc}") from exc

        try:
            await ws.send(json.dumps(body))
            async for message in ws:
                if isinstance(message, bytes):
                    yield _strip_wav_header(message)
                    continue

                try:
                    payload = json.loads(message)
                except (json.JSONDecodeError, TypeError):
                    continue

                msg_type = payload.get("type")

                if msg_type == "audio":
                    data = payload.get("data", {})
                    audio_b64 = data.get("audio", "")
                    if audio_b64:
                        yield _strip_wav_header(base64.b64decode(audio_b64))

                elif msg_type == "complete":
                    data = payload.get("data")
                    if data is not None:
                        audio_b64 = data.get("audio", "")
                        if audio_b64:
                            yield _strip_wav_header(base64.b64decode(audio_b64))
                    return

                elif msg_type == "error":
                    raise StreamError(payload.get("message", json.dumps(payload)))

        except websockets.ConnectionClosed:
            pass
        finally:
            with contextlib.suppress(Exception):
                await ws.close()

    async def synthesize_events(
        self,
        text: str,
        voice: str | None = "Pranav",
        *,
        model: str = DEFAULT_MODEL,
        audio_config: AudioConfig | None = None,
        speaker_embedding: SpeakerEmbedding | None = None,
    ) -> AsyncIterator[TTSStreamEvent]:
        """Stream typed events for the given text via WebSocket.

        Unlike :meth:`synthesize` (which yields raw ``bytes``), this method
        yields :class:`TTSStartEvent`, :class:`TTSAudioChunkEvent`, and
        :class:`TTSCompletedEvent` objects so callers can inspect metadata
        like ``chunk_index`` and ``request_id``.

        Parameters
        ----------
        text : str
            The text to synthesise.
        voice : str, optional
            Pre-defined voice ID. Defaults to ``"Pranav"``.
        model : str
            TTS model to use. Defaults to ``"vachana-voice-v3"``.
        audio_config : AudioConfig, optional
            Output audio configuration.
        speaker_embedding : SpeakerEmbedding, optional
            Voice cloning embedding (included alongside ``voice``).

        Yields
        ------
        TTSStreamEvent
            One of :class:`TTSStartEvent`, :class:`TTSAudioChunkEvent`,
            or :class:`TTSCompletedEvent`.
        """
        _validate_model(model)
        _validate_voice(voice)

        cfg = audio_config or AudioConfig()
        body: dict[str, Any] = {
            "text": text,
            "voice": voice,
            "model": model,
            "audio_config": cfg.to_dict(),
        }
        if speaker_embedding is not None:
            body["speaker_embedding"] = speaker_embedding.to_dict()

        try:
            ws = await websockets.connect(
                self._ws_url,
                **_ws_header_kwargs(self._build_headers()),
                ping_interval=20,
                ping_timeout=20,
                close_timeout=10,
            )
        except Exception as exc:
            raise StreamConnectionError(f"Failed to connect to {self._ws_url}: {exc}") from exc

        chunk_count = 0
        try:
            await ws.send(json.dumps(body))
            async for message in ws:
                if isinstance(message, bytes):
                    chunk_count += 1
                    yield TTSAudioChunkEvent(
                        data=_strip_wav_header(message),
                        chunk_index=chunk_count,
                        is_final=False,
                    )
                    continue

                try:
                    payload = json.loads(message)
                except (json.JSONDecodeError, TypeError):
                    continue

                msg_type = payload.get("type")

                if msg_type == "start":
                    yield TTSStartEvent(
                        request_id=payload.get("request_id", ""),
                        message=payload.get("message", ""),
                    )

                elif msg_type == "audio":
                    data = payload.get("data", {})
                    audio_b64 = data.get("audio", "")
                    if audio_b64:
                        chunk_count += 1
                        yield TTSAudioChunkEvent(
                            data=_strip_wav_header(base64.b64decode(audio_b64)),
                            chunk_index=data.get("chunk_index", chunk_count),
                            is_final=data.get("is_final", False),
                        )

                elif msg_type == "complete":
                    data = payload.get("data")
                    if data is not None:
                        audio_b64 = data.get("audio", "")
                        if audio_b64:
                            chunk_count += 1
                            yield TTSAudioChunkEvent(
                                data=_strip_wav_header(base64.b64decode(audio_b64)),
                                chunk_index=data.get("chunk_index", chunk_count),
                                is_final=data.get("is_final", True),
                            )
                    yield TTSCompletedEvent(
                        request_id=payload.get("request_id", ""),
                        total_chunks=chunk_count,
                    )
                    return

                elif msg_type == "error":
                    raise StreamError(payload.get("message", json.dumps(payload)))

        except websockets.ConnectionClosed:
            pass
        finally:
            with contextlib.suppress(Exception):
                await ws.close()

    async def synthesize_and_collect(
        self,
        text: str,
        voice: str | None = "Pranav",
        *,
        model: str = DEFAULT_MODEL,
        audio_config: AudioConfig | None = None,
        speaker_embedding: SpeakerEmbedding | None = None,
        output_file: str | Path | None = None,
    ) -> bytes:
        """Synthesise speech and return a complete valid WAV file.

        Convenience wrapper around :meth:`synthesize` that collects raw
        PCM chunks and wraps them in a single WAV header.

        Parameters
        ----------
        output_file : str or Path, optional
            If provided, the complete audio is written to this file.
            Parent directories are created automatically.

        Returns
        -------
        bytes
            The complete synthesised audio as a valid WAV file.
        """
        cfg = audio_config or AudioConfig()
        chunks: list[bytes] = []
        async for chunk in self.synthesize(
            text,
            voice,
            model=model,
            audio_config=audio_config,
            speaker_embedding=speaker_embedding,
        ):
            chunks.append(chunk)
        pcm = b"".join(chunks)
        audio = (
            _build_wav_header(
                len(pcm),
                cfg.sample_rate,
                cfg.num_channels,
                cfg.sample_width,
            )
            + pcm
        )
        if output_file is not None:
            _save_audio(audio, output_file)
        return audio

    async def __aenter__(self) -> GnaniTTSRealtimeClient:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass

    @staticmethod
    def supported_voices() -> list[str]:
        """Return the list of supported voice IDs."""
        return sorted(SUPPORTED_VOICES)
