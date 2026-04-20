"""Core client for Gnani Text-to-Speech API (REST, SSE Streaming, Realtime WebSocket)."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Iterator, Union

import requests
import websockets

from gnani.tts.exceptions import (
    APIError,
    AuthenticationError,
    StreamClosedError,
    StreamConnectionError,
    StreamError,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

DEFAULT_BASE_URL = "https://api.vachana.ai"
TTS_ENDPOINT = "/api/v1/tts/inference"
TTS_SSE_ENDPOINT = "/api/v1/tts/sse"
TTS_WS_ENDPOINT = "/api/v1/tts"

DEFAULT_MODEL = "vachana-voice-v2"

SUPPORTED_VOICES = frozenset({"sia", "raju", "kanika", "nikita", "ravan", "simran", "karan", "neha"})
SUPPORTED_ENCODINGS = frozenset({"linear_pcm", "oggopus"})
SUPPORTED_CONTAINERS = frozenset({"raw", "mp3", "wav", "mulaw", "ogg"})
SUPPORTED_BITRATES = frozenset({"96k", "128k", "192k"})
SUPPORTED_MODELS = frozenset({"vachana-voice-v2"})


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
            f"Unsupported voice '{voice}'. "
            f"Choose from: {', '.join(sorted(SUPPORTED_VOICES))}"
        )


def _validate_model(model: str) -> None:
    if model not in SUPPORTED_MODELS:
        raise ValueError(
            f"Unsupported model '{model}'. "
            f"Choose from: {', '.join(sorted(SUPPORTED_MODELS))}"
        )


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
        audio_bytes = client.synthesize("नमस्ते, आप कैसे हैं?", voice="sia")
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
        self.api_key = api_key or os.getenv("GNANI_API_KEY", "")
        if not self.api_key:
            raise AuthenticationError(
                "api_key is required. Pass it directly or set the "
                "GNANI_API_KEY environment variable."
            )
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
        voice: str | None = "sia",
        *,
        model: str = DEFAULT_MODEL,
        audio_config: AudioConfig | None = None,
        speaker_embedding: SpeakerEmbedding | None = None,
    ) -> bytes:
        """Synthesise speech and return the full audio as bytes.

        Parameters
        ----------
        text : str
            The text to synthesise.
        voice : str, optional
            Pre-defined voice ID. One of ``"sia"``, ``"raju"``, ``"kanika"``,
            ``"nikita"``, ``"ravan"``, ``"simran"``, ``"karan"``, ``"neha"``.
            Ignored when ``speaker_embedding`` is provided. Defaults to ``"sia"``.
        model : str
            TTS model to use. Defaults to ``"vachana-voice-v2"``.
        audio_config : AudioConfig, optional
            Output audio configuration. Defaults to 44100 Hz WAV with linear PCM.
        speaker_embedding : SpeakerEmbedding, optional
            Voice cloning embedding. When provided, ``voice`` is ignored.

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

        return response.content

    @staticmethod
    def supported_voices() -> list[str]:
        """Return the list of supported voice IDs."""
        return sorted(SUPPORTED_VOICES)


# ---------------------------------------------------------------------------
# SSE Streaming client
# ---------------------------------------------------------------------------


def _parse_sse_lines(response: requests.Response) -> Iterator[bytes]:
    """Parse a Server-Sent Events stream and yield decoded audio chunks."""
    event_type: str | None = None

    for raw_line in response.iter_lines(decode_unicode=True):
        if not raw_line:
            event_type = None
            continue

        if raw_line.startswith("event:"):
            event_type = raw_line[len("event:"):].strip()

        elif raw_line.startswith("data:"):
            data = raw_line[len("data:"):].strip()

            if event_type == "audio_chunk":
                yield base64.b64decode(data)

            elif event_type == "completed":
                return

            elif event_type == "error":
                try:
                    payload = json.loads(data)
                    msg = payload.get("message", data)
                except (json.JSONDecodeError, AttributeError):
                    msg = data
                raise StreamError(msg)


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
    Stream directly to a file::

        client = GnaniTTSStreamClient(api_key="key")
        with open("output.wav", "wb") as f:
            for chunk in client.synthesize_stream("Hello, world!", voice="sia"):
                f.write(chunk)

    Collect all chunks into a single bytes object::

        audio = client.synthesize("Hello!", voice="sia")
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: int = 60,
    ):
        self.api_key = api_key or os.getenv("GNANI_API_KEY", "")
        if not self.api_key:
            raise AuthenticationError(
                "api_key is required. Pass it directly or set the "
                "GNANI_API_KEY environment variable."
            )
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
        voice: str | None = "sia",
        *,
        model: str = DEFAULT_MODEL,
        audio_config: AudioConfig | None = None,
        speaker_embedding: SpeakerEmbedding | None = None,
    ) -> Iterator[bytes]:
        """Synthesise speech and yield audio chunks as they are generated.

        Parameters
        ----------
        text : str
            The text to synthesise.
        voice : str, optional
            Pre-defined voice ID. Defaults to ``"sia"``.
        model : str
            TTS model to use. Defaults to ``"vachana-voice-v2"``.
        audio_config : AudioConfig, optional
            Output audio configuration.
        speaker_embedding : SpeakerEmbedding, optional
            Voice cloning embedding. When provided, ``voice`` is ignored.

        Yields
        ------
        bytes
            Raw audio chunks as they arrive.

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
        voice: str | None = "sia",
        *,
        model: str = DEFAULT_MODEL,
        audio_config: AudioConfig | None = None,
        speaker_embedding: SpeakerEmbedding | None = None,
    ) -> bytes:
        """Synthesise speech and return the complete audio as bytes.

        Convenience wrapper around :meth:`synthesize_stream` that collects
        all chunks into a single ``bytes`` object.
        """
        return b"".join(
            self.synthesize_stream(
                text,
                voice,
                model=model,
                audio_config=audio_config,
                speaker_embedding=speaker_embedding,
            )
        )

    @staticmethod
    def supported_voices() -> list[str]:
        """Return the list of supported voice IDs."""
        return sorted(SUPPORTED_VOICES)


# ---------------------------------------------------------------------------
# Realtime WebSocket client
# ---------------------------------------------------------------------------


@dataclass
class TTSAudioChunkEvent:
    """A binary audio chunk received from the TTS WebSocket stream.

    Attributes
    ----------
    data : bytes
        Raw audio bytes for this chunk.
    chunk_index : int
        Zero-based index of this chunk within the response.
    """

    data: bytes
    chunk_index: int


@dataclass
class TTSCompletedEvent:
    """Emitted when the server has finished streaming all audio.

    Attributes
    ----------
    total_chunks : int
        Total number of audio chunks received.
    """

    total_chunks: int


TTSStreamEvent = Union[TTSAudioChunkEvent, TTSCompletedEvent]


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
                    "नमस्ते, आप कैसे हैं?", voice="sia"
                ):
                    f.write(chunk)

    Collect full audio in one call::

        async with GnaniTTSRealtimeClient(api_key="key") as client:
            audio = await client.synthesize_and_collect("Hello!", voice="sia")
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
    ):
        self.api_key = api_key or os.getenv("GNANI_API_KEY", "")
        if not self.api_key:
            raise AuthenticationError(
                "api_key is required. Pass it directly or set the "
                "GNANI_API_KEY environment variable."
            )

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
        voice: str | None = "sia",
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
            Pre-defined voice ID. Defaults to ``"sia"``.
        model : str
            TTS model to use. Defaults to ``"vachana-voice-v2"``.
        audio_config : AudioConfig, optional
            Output audio configuration.
        speaker_embedding : SpeakerEmbedding, optional
            Voice cloning embedding. When provided, ``voice`` is ignored.

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
        body = _build_request_body(text, voice, model, cfg, speaker_embedding)

        try:
            ws = await websockets.connect(
                self._ws_url,
                additional_headers=self._build_headers(),
                ping_interval=20,
                ping_timeout=20,
                close_timeout=10,
            )
        except Exception as exc:
            raise StreamConnectionError(
                f"Failed to connect to {self._ws_url}: {exc}"
            ) from exc

        try:
            await ws.send(json.dumps(body))
            async for message in ws:
                if isinstance(message, bytes):
                    yield message
        except websockets.ConnectionClosed:
            pass
        finally:
            with contextlib.suppress(Exception):
                await ws.close()

    async def synthesize_and_collect(
        self,
        text: str,
        voice: str | None = "sia",
        *,
        model: str = DEFAULT_MODEL,
        audio_config: AudioConfig | None = None,
        speaker_embedding: SpeakerEmbedding | None = None,
    ) -> bytes:
        """Synthesise speech and collect all audio chunks into a single bytes object.

        Convenience wrapper around :meth:`synthesize` that collects every
        chunk before returning.

        Returns
        -------
        bytes
            The complete synthesised audio.
        """
        chunks: list[bytes] = []
        async for chunk in self.synthesize(
            text,
            voice,
            model=model,
            audio_config=audio_config,
            speaker_embedding=speaker_embedding,
        ):
            chunks.append(chunk)
        return b"".join(chunks)

    async def __aenter__(self) -> GnaniTTSRealtimeClient:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass

    @staticmethod
    def supported_voices() -> list[str]:
        """Return the list of supported voice IDs."""
        return sorted(SUPPORTED_VOICES)
