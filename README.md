# gnani-vachana
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Official Python client by [Gnani.ai](https://gnani.ai). Build multilingual voice workflows with Speech-to-Text (STT) and Text-to-Speech (TTS) across REST, SSE streaming, and real-time WebSockets.

> **[Gnani.ai](https://gnani.ai)** is a production-ready speech AI platform with high-accuracy STT and low-latency TTS for 10+ Indian languages, with Timbre voices across REST, SSE, and WebSocket APIs.

## Installation

```bash
pip install gnani-vachana
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add gnani-vachana
```

Requires **Python 3.9+**.

## Quick Start

### STT REST (file-based transcription)

```python
from gnani.stt import GnaniSTTClient

client = GnaniSTTClient(api_key="your-api-key")

result = client.transcribe("audio.wav", language_code="hi-IN")
print(result["transcript"])
```

### Realtime Streaming (WebSocket)

```python
import asyncio
from gnani.stt import GnaniSTTStreamClient, StreamTranscriptEvent

async def main():
    async with GnaniSTTStreamClient(api_key="your-api-key", language_code="hi-IN") as stream:
        # Send audio chunks (raw PCM, 16-bit LE, 16 kHz, mono)
        with open("audio.pcm", "rb") as f:
            while chunk := f.read(1024):
                await stream.send_audio(chunk)
                await asyncio.sleep(0.032)  # real-time pacing (32 ms per frame)

        # Iterate over events
        async for event in stream:
            if isinstance(event, StreamTranscriptEvent):
                print(event.text)

asyncio.run(main())
```

### TTS REST (single response)

```python
from gnani.tts import GnaniTTSClient, AudioConfig

client = GnaniTTSClient(api_key="your-api-key")

# timbre-v2.0 (default model)
audio = client.synthesize(
    "नमस्ते, आप कैसे हैं?",
    voice="Pranav",
    model="timbre-v2.0",
    audio_config=AudioConfig(sample_rate=48000, encoding="linear_pcm", container="wav"),
)

# timbre-v2.5 — language control + speed
audio = client.synthesize(
    "नमस्ते, यह एक परीक्षण है।",
    voice="Nalini",
    model="timbre-v2.5",
    language="hi-IN",
    speed=1.0,
    audio_config=AudioConfig(container="mp3", sample_rate=48000, bitrate="128k"),
)

with open("tts_output.mp3", "wb") as f:
    f.write(audio)
```

### TTS SSE Streaming (lower latency)

```python
from gnani.tts import GnaniTTSStreamClient, AudioConfig

client = GnaniTTSStreamClient(api_key="your-api-key")
audio = client.synthesize(
    "Hello from Gnani TTS",
    voice="Pranav",
    model="timbre-v2.0",
    audio_config=AudioConfig(sample_rate=48000, encoding="linear_pcm", container="wav"),
    output_file="tts_sse.wav",
)
```

### TTS Realtime WebSocket (lowest latency)

```python
import asyncio
from gnani.tts import GnaniTTSRealtimeClient, AudioConfig

async def main():
    async with GnaniTTSRealtimeClient(api_key="your-api-key") as client:
        audio = await client.synthesize_and_collect(
            "Hello from Gnani TTS",
            voice="Pranav",
            model="timbre-v2.0",
            audio_config=AudioConfig(sample_rate=48000, encoding="linear_pcm", container="wav"),
            output_file="tts_realtime.wav",
        )

asyncio.run(main())
```

## Authentication

All APIs (STT REST, STT Realtime, TTS) require a single API key:

| Parameter | Header         | Description                           |
|-----------|----------------|---------------------------------------|
| `api_key` | `X-API-Key-ID` | API key identifier for authentication |

### Obtaining Credentials

You need a Gnani API key. [Gnani APIs](https://app.gnani.ai/voice) have this.

### Passing Credentials

**Option 1 -- Constructor argument:**

```python
from gnani.stt import GnaniSTTClient, GnaniSTTStreamClient
from gnani.tts import GnaniTTSClient, GnaniTTSRealtimeClient, GnaniTTSStreamClient

client = GnaniSTTClient(api_key="your-api-key")
stream = GnaniSTTStreamClient(api_key="your-api-key")
tts_rest = GnaniTTSClient(api_key="your-api-key")
tts_stream = GnaniTTSStreamClient(api_key="your-api-key")
tts_realtime = GnaniTTSRealtimeClient(api_key="your-api-key")
```

**Option 2 -- Environment variable:**

```bash
export GNANI_API_KEY="your-api-key"
```

```python
from gnani.stt import GnaniSTTClient, GnaniSTTStreamClient
from gnani.tts import GnaniTTSClient

client = GnaniSTTClient()           # picks up GNANI_API_KEY
stream = GnaniSTTStreamClient()     # picks up GNANI_API_KEY
tts = GnaniTTSClient()              # picks up GNANI_API_KEY
```

## Supported Languages

### STT Languages (Speech-to-Text)

STT uses BCP-47 locale codes (e.g. `hi-IN`). For the full list of supported languages, see:

- **[STT REST — Supported Languages](https://docs.gnani.ai/api/STT/speech-to-text#supported-languages)**
- **[STT Realtime — Supported Languages](https://docs.gnani.ai/api/STT/stt-websocket#supported-languages)**

---

### TTS Voices & Models

TTS uses the **Timbre** engine. Two model IDs are supported:

| Model | Voices | `language` |
|-------|--------|------------|
| `timbre-v2.0` (default) | 4 legacy voices | Not supported |
| `timbre-v2.5` | 42 voices | Supported |

> **Migration:** The former model name `vachana-voice-v3` has been renamed to **`timbre-v2.0`**. Update any `model="vachana-voice-v3"` calls to `model="timbre-v2.0"` (or omit `model` to use the default).

#### timbre-v2.0 voices

| Voice   | Gender | Description              |
|---------|--------|--------------------------|
| Pranav  | Male   | Bold, Trustworthy        |
| Kaveri  | Female | Confident, Bright        |
| Shubhra | Female | Gentle, Expressive       |
| Deepak  | Male   | Grounded, Conversational |

#### timbre-v2.5 voices

42 Timbre voices across Hindi, English, Tamil, Telugu, Kannada, Malayalam, Marathi, Bengali, Gujarati, Punjabi, and Hinglish. Examples: `Nalini`, `Kaveri`, `Asmita`, `Suhana`, `Poorvi`.

List voices programmatically:

```python
from gnani.tts import GnaniTTSClient

print(GnaniTTSClient.supported_voices())                    # timbre-v2.0 (default)
print(GnaniTTSClient.supported_voices(model="timbre-v2.5")) # 42 voices
```

#### timbre-v2.5 optional controls

Only **`timbre-v2.5`** accepts the `language` and `speed` parameters:

| Parameter | Type | Description |
|-----------|------|-------------|
| `language` | `str` | BCP-47 code: `auto`, `hi-IN`, `en-IN`, `ta-IN`, `te-IN`, `kn-IN`, `ml-IN`, `mr-IN`, `bn-IN`, `gu-IN`, `pa-IN` |
| `speed` | `float` | Speaking rate. Range `0.85`–`1.15`. Defaults to `1.0` (normal speed). |

`voice` is required for all Timbre models unless `speaker_embedding` is provided.

### TTS Languages (Text-to-Speech)

For the full list of supported languages, see **[TTS — Supported Languages](https://docs.gnani.ai/api/TTS/tts-inference#supported-languages)**.

## REST Usage

### Transcribe a file by path

```python
result = client.transcribe("meeting.wav", language_code="en-IN")
print(result["transcript"])
```

### Transcribe from a file object

```python
with open("meeting.mp3", "rb") as f:
    result = client.transcribe(f, language_code="ta-IN")
```

### Transcribe raw bytes

```python
audio_bytes = download_audio_from_somewhere()
result = client.transcribe_bytes(
    audio_bytes, filename="clip.wav", language_code="kn-IN"
)
```

### Custom request ID

```python
result = client.transcribe(
    "call.flac", language_code="hi-IN", request_id="my-trace-123"
)
```

### List supported languages

```python
for code, name in GnaniSTTClient.supported_languages().items():
    print(f"{code}: {name}")
```

## Realtime Streaming Usage

### Connection Flow

1. Client opens a WebSocket connection to `wss://api.vachana.ai/stt/v3/stream` with auth headers.
2. Server sends a `connected` event with the active configuration.
3. Client sends binary PCM audio frames (1024 bytes each = 512 samples at 16-bit).
4. Server detects speech via VAD and responds with `processing` and `transcript` events.
5. Either side may close the connection at any time.

### PCM Specification

All audio must be sent as **raw PCM binary frames**. No container format (WAV, MP3, etc.) is accepted mid-stream.

| Property          | 16 kHz                                    | 8 kHz                                     |
|-------------------|-------------------------------------------|-------------------------------------------|
| Encoding          | PCM signed 16-bit little-endian           | PCM signed 16-bit little-endian           |
| Sample Rate       | 16,000 Hz                                 | 8,000 Hz                                  |
| Channels          | 1 (mono)                                  | 1 (mono)                                  |
| Samples per chunk | 512                                       | 512                                       |
| **Bytes per frame** | **1,024 bytes** (512 samples × 2 bytes) | **1,024 bytes** (512 samples × 2 bytes)   |
| Frame duration    | 32 ms                                     | 64 ms                                     |

- Each binary frame must be **exactly 1,024 bytes**.
- Frames must be sent at **real-time cadence** — one frame every 32 ms (16 kHz) or 64 ms (8 kHz). Do not buffer and burst; this degrades VAD accuracy.
- For `44100` and `48000` Hz sources, the server resamples internally — still send 1,024-byte frames at the appropriate cadence.

For the full WebSocket protocol reference, see **[STT Realtime — PCM Specification](https://docs.gnani.ai/api/STT/stt-websocket#pcm-specification)**.

### Using the async context manager

```python
import asyncio
from gnani.stt import GnaniSTTStreamClient, StreamTranscriptEvent

async def main():
    async with GnaniSTTStreamClient(
        api_key="your-api-key",
        language_code="hi-IN",
        sample_rate=16000,
    ) as stream:
        print(f"Connected! Sample rate: {stream.connected_config.sample_rate}")

        with open("audio.pcm", "rb") as f:
            while chunk := f.read(1024):
                await stream.send_audio(chunk)
                await asyncio.sleep(0.032)

        async for event in stream:
            if isinstance(event, StreamTranscriptEvent):
                print(f"[{event.segment_index}] {event.text}")
                print(f"  Duration: {event.audio_duration_ms}ms, Latency: {event.latency}ms")

asyncio.run(main())
```

### Manual connect / close

```python
import asyncio
from gnani.stt import GnaniSTTStreamClient, StreamTranscriptEvent

async def main():
    stream = GnaniSTTStreamClient(api_key="your-api-key")
    config = await stream.connect()
    print(f"Server ready: {config.message}")

    await stream.send_audio(audio_chunk)
    transcripts = await stream.close()

    for t in transcripts:
        print(t.text)

asyncio.run(main())
```

### High-level stream_audio helper with callbacks

```python
import asyncio
from gnani.stt import GnaniSTTStreamClient, StreamTranscriptEvent, StreamProcessingEvent

async def main():
    async with GnaniSTTStreamClient(api_key="your-api-key") as stream:
        with open("audio.pcm", "rb") as f:
            transcripts = await stream.stream_audio(
                f,
                on_transcript=lambda t: print(f"Transcript: {t.text}"),
                on_processing=lambda p: print(f"Processing at {p.timestamp}..."),
                realtime_pace=True,
            )

    print(f"Total segments: {len(transcripts)}")

asyncio.run(main())
```

### Using 8 kHz audio

```python
stream = GnaniSTTStreamClient(
    api_key="your-api-key",
    language_code="en-IN",
    sample_rate=8000,
)
```

### Event Types

All events are typed dataclasses:

| Event                    | Fields                                                                 | Description                                  |
|--------------------------|------------------------------------------------------------------------|----------------------------------------------|
| `StreamConnectedEvent`   | `message`, `timestamp`, `sample_rate`, `chunk_size`, `raw`             | Handshake confirmation with server config    |
| `StreamProcessingEvent`  | `timestamp`, `raw`                                                     | VAD detected end-of-speech, transcribing     |
| `StreamTranscriptEvent`  | `text`, `audio_duration_ms`, `segment_id`, `segment_index`, `latency`, `timestamp`, `raw` | Completed transcription for a speech segment |
| `StreamErrorEvent`       | `message`, `timestamp`, `raw`                                          | Server-side error                            |

### Accessing the raw JSON payload

Every event includes a `raw` field with the full server JSON:

```python
async for event in stream:
    print(event.raw)  # dict with the complete server response
```

## Text-to-Speech Usage

> Input text is normalized server-side; see the [Text Normalization Guide](https://docs.gnani.ai/api/TTS/tts-input-formating) for symbols, numbers, and abbreviations.

### TTS Models

```python
from gnani.tts import DEFAULT_MODEL, SUPPORTED_MODELS

print(DEFAULT_MODEL)              # timbre-v2.0
print(sorted(SUPPORTED_MODELS))   # timbre-v2.0, timbre-v2.5
```

### TTS REST

```python
from gnani.tts import GnaniTTSClient

client = GnaniTTSClient(api_key="your-api-key")
# Default audio_config uses sample_rate=48000
audio = client.synthesize("यह एक टेस्ट है", voice="Pranav", model="timbre-v2.0")
with open("tts_rest.wav", "wb") as f:
    f.write(audio)
```

### TTS Streaming (SSE)

Lower latency than REST — audio is streamed via Server-Sent Events.

```python
from gnani.tts import GnaniTTSStreamClient, AudioConfig

client = GnaniTTSStreamClient(api_key="your-api-key")

# synthesize() collects all chunks and returns audio matching audio_config
audio = client.synthesize(
    "Streaming TTS response",
    voice="Pranav",
    model="timbre-v2.0",
    audio_config=AudioConfig(sample_rate=48000, encoding="linear_pcm", container="wav"),
    output_file="tts_sse.wav",
)
```

For chunk-by-chunk streaming (e.g. real-time playback), use `synthesize_stream()`:

```python
for audio_chunk in client.synthesize_stream("Hello!", voice="Pranav", model="timbre-v2.0"):
    play_audio(audio_chunk)  # format depends on audio_config (PCM, OGG, MP3, etc.)
```

### TTS Realtime (WebSocket)

Lowest latency — audio is streamed over a persistent WebSocket connection.

```python
import asyncio
from gnani.tts import GnaniTTSRealtimeClient, AudioConfig

async def main():
    async with GnaniTTSRealtimeClient(api_key="your-api-key") as client:
        # synthesize_and_collect() returns audio matching audio_config
        audio = await client.synthesize_and_collect(
            "Realtime TTS response",
            voice="Kaveri",
            model="timbre-v2.0",
            audio_config=AudioConfig(sample_rate=48000, encoding="linear_pcm", container="wav"),
            output_file="tts_realtime.wav",
        )

asyncio.run(main())
```

For chunk-by-chunk streaming (e.g. real-time playback):

```python
async with GnaniTTSRealtimeClient(api_key="your-api-key") as client:
    async for audio_chunk in client.synthesize("Hello!", voice="Pranav", model="timbre-v2.0"):
        play_audio(audio_chunk)  # format depends on audio_config (PCM, OGG, MP3, etc.)
```

### TTS timbre-v2.5 (expanded catalog)

```python
from gnani.tts import GnaniTTSClient, AudioConfig

client = GnaniTTSClient(api_key="your-api-key")
audio = client.synthesize(
    "Hello, this is a Timbre test.",
    voice="Kaveri",
    model="timbre-v2.5",
    language="en-IN",
    speed=1.0,
    audio_config=AudioConfig(container="mp3", sample_rate=48000, bitrate="128k"),
)
```

The same `model` and `language` parameters work on `GnaniTTSStreamClient` (SSE) and `GnaniTTSRealtimeClient` (WebSocket) when using `timbre-v2.5`.

### TTS Telephony Formats

For telephony integrations (IVR, SIP), use 8 kHz A-law or μ-law:

```python
from gnani.tts import GnaniTTSClient, AudioConfig

client = GnaniTTSClient(api_key="your-api-key")

# A-law (G.711a) — common in European/Indian telephony
alaw_audio = client.synthesize(
    "Hello from Gnani",
    voice="Pranav",
    audio_config=AudioConfig(container="alaw", sample_rate=8000),
)

# μ-law (G.711u) — common in North American telephony
mulaw_audio = client.synthesize(
    "Hello from Gnani",
    voice="Pranav",
    audio_config=AudioConfig(container="mulaw", sample_rate=8000),
)
```

### TTS OGG/Opus

Returns a playable OGG Opus file (`OggS` header). Use either form:

- `container="ogg"` (encoding defaults to `oggopus`)
- `container="raw", encoding="oggopus"`

Supported at all standard sample rates (8000–48000).

```python
from gnani.tts import GnaniTTSClient, AudioConfig

client = GnaniTTSClient(api_key="your-api-key")

# Using container="ogg"
ogg_audio = client.synthesize(
    "Hello from Gnani",
    voice="Pranav",
    audio_config=AudioConfig(container="ogg", encoding="oggopus", sample_rate=48000),
)

with open("output.ogg", "wb") as f:
    f.write(ogg_audio)
```

**SSE / WebSocket:** OGG is delivered as one complete file in a single chunk (not streamable frame-by-frame). For chunk iteration, use `synthesize_stream()` (SSE) or async `synthesize()` (WebSocket) — the buffered `synthesize()` and `synthesize_and_collect()` methods correctly return the raw OGG bytes without WAV wrapping when using non-PCM encodings.

### TTS Audio Format Matrix

Supported combinations of `container`, `encoding`, `sample_rate`, and `bitrate`:

| Container | Encoding | Sample Rates | Bitrate | Notes |
|-----------|----------|--------------|---------|-------|
| `wav` | `linear_pcm` | 8000, 16000, 22050, 24000, 44100, 48000 | — | Standard WAV (RIFF header) |
| `mp3` | `linear_pcm` | 8000, 16000, 22050, 24000, 44100, 48000 | `32k`, `64k`, `96k`, `128k`, `192k` | All 5 bitrates supported |
| `raw` | `linear_pcm` | 8000, 16000, 22050, 24000, 44100, 48000 | — | Raw PCM, no header |
| `ogg` | `oggopus` | 8000, 16000, 22050, 24000, 44100, 48000 | — | Playable OGG Opus file |
| `raw` | `oggopus` | 8000, 16000, 22050, 24000, 44100, 48000 | — | Equivalent to `ogg` |
| `mulaw` | `linear_pcm` | 8000 | — | G.711μ telephony |
| `alaw` | `linear_pcm` | 8000 | — | G.711A telephony |

**Notes:**
- `bitrate` is **only** applicable to `container="mp3"`. It is ignored for all other containers.
- `mulaw` and `alaw` containers are **telephony-only** — they require `sample_rate=8000`.
- For telephony, prefer `container="alaw"` / `container="mulaw"` over `encoding="pcm_alaw"` / `encoding="pcm_mulaw"`.
- `container="ogg"` and `container="raw"` with `encoding="oggopus"` are equivalent — both return a playable OGG Opus file.

> **File extensions:** Match the output file extension to your `audio_config.container` — use `.wav` for WAV, `.mp3` for MP3, `.ogg` for OGG/Opus, `.raw` for raw PCM, `.alaw` / `.ulaw` for telephony.

### TTS Supported Constants

```python
from gnani.tts import (
    SUPPORTED_ENCODINGS,     # {"linear_pcm", "oggopus", "pcm_mulaw", "pcm_alaw"}
    SUPPORTED_CONTAINERS,    # {"raw", "mp3", "wav", "ogg", "mulaw", "alaw"}
    SUPPORTED_BITRATES,      # {"32k", "64k", "96k", "128k", "192k"}
    SUPPORTED_SAMPLE_RATES,  # (8000, 16000, 22050, 24000, 44100, 48000)
    DEFAULT_SPEED,           # 1.0
    MIN_SPEED,               # 0.85
    MAX_SPEED,               # 1.15
)
```

### TTS Voices

List voices for a specific model:

```python
from gnani.tts import GnaniTTSClient, TIMBRE_V25_VOICES

print(GnaniTTSClient.supported_voices())                    # 4 voices (timbre-v2.0)
print(GnaniTTSClient.supported_voices(model="timbre-v2.5")) # 42 voices
print(len(TIMBRE_V25_VOICES))                               # 42
```

Legacy voices (`Pranav`, `Kaveri`, `Shubhra`, `Deepak`) are valid for `timbre-v2.0` only.

## Audio Requirements

### STT REST

| Constraint       | Value                                      |
|------------------|--------------------------------------------|
| Formats          | WAV, MP3, FLAC, OGG, M4A                   |
| Max duration     | 60 seconds                                 |
| Channels         | Mono or stereo                             |
| Sample rate      | Automatically converted to 16 kHz mono     |

### STT Streaming (WebSocket)

| Constraint       | Value                                                  |
|------------------|--------------------------------------------------------|
| Encoding         | Raw PCM, signed 16-bit little-endian                   |
| Sample rate      | 16,000 Hz or 8,000 Hz                                  |
| Channels         | 1 (mono)                                               |
| Frame size       | 1,024 bytes (512 samples)                              |
| Pacing           | Send frames at real-time cadence for best VAD accuracy |

See **[PCM Specification](https://docs.gnani.ai/api/STT/stt-websocket#pcm-specification)** for full details.

## Response Format

### REST

```json
{
  "success": true,
  "request_id": "req_abc123",
  "timestamp": "20251226_143052.123",
  "transcript": "नमस्ते, आप कैसे हैं?"
}
```

### Realtime Streaming

**Connected:**
```json
{
  "type": "connected",
  "message": "STT service ready — VAD service connected",
  "timestamp": "2024-01-15T10:30:00.000Z",
  "config": { "sample_rate": 16000, "chunk_size": 512 }
}
```

**Transcript:**
```json
{
  "type": "transcript",
  "timestamp": "2024-01-15T10:30:05.987Z",
  "text": "Hello, how are you today?",
  "audio_duration_ms": 2340,
  "segment_id": "<segment_id>",
  "segment_index": "<segment_index>",
  "latency": 320
}
```

## Error Handling

```python
from gnani.stt import (
    AuthenticationError,
    InvalidAudioError,
    APIError,
    StreamConnectionError,
    StreamClosedError,
    StreamError,
)

# REST errors
try:
    result = client.transcribe("audio.wav", language_code="hi-IN")
except AuthenticationError:
    print("Check your credentials")
except InvalidAudioError as e:
    print(f"Bad audio file: {e}")
except APIError as e:
    print(f"API error {e.status_code}: {e}")

# Streaming errors
try:
    async with GnaniSTTStreamClient(api_key="key") as stream:
        await stream.send_audio(chunk)
except StreamConnectionError as e:
    print(f"Connection failed: {e}")
except StreamClosedError as e:
    print(f"Stream already closed: {e}")
except StreamError as e:
    print(f"Server error: {e} (at {e.timestamp})")
```

### TTS Errors

```python
from gnani.tts import (
    GnaniTTSClient,
    GnaniTTSRealtimeClient,
    AuthenticationError,
    APIError,
    StreamConnectionError,
    StreamError,
)

# REST / SSE errors
try:
    audio = GnaniTTSClient(api_key="key").synthesize("Hello", voice="Pranav")
except AuthenticationError:
    print("Check your API key")
except APIError as e:
    print(f"TTS API error {e.status_code}: {e}")

# WebSocket errors
try:
    async with GnaniTTSRealtimeClient(api_key="key") as client:
        audio = await client.synthesize_and_collect("Hello", voice="Pranav")
except StreamConnectionError as e:
    print(f"WebSocket connection failed: {e}")
except StreamError as e:
    print(f"TTS stream error: {e}")
```

## Documentation

Full API reference and guides are available at **[docs.gnani.ai](https://docs.gnani.ai/)**.

- [STT REST API](https://docs.gnani.ai/api/STT/speech-to-text)
- [STT Realtime WebSocket](https://docs.gnani.ai/api/STT/stt-websocket)
- [TTS REST API](https://docs.gnani.ai/api/TTS/tts-inference)
- [TTS Streaming (SSE)](https://docs.gnani.ai/api/TTS/tts-sse)
- [TTS Realtime WebSocket](https://docs.gnani.ai/api/TTS/tts-websocket)
- [Text Normalization Guide](https://docs.gnani.ai/api/TTS/tts-input-formating)

## License

This project is licensed under the MIT License -- see the [LICENSE](LICENSE) file for details.
