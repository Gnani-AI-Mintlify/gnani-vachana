# gnani-vachana
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Official Python client for **[Vachana Speech APIs](https://docs.gnani.ai/)** by [Gnani.ai](https://gnani.ai). Build multilingual voice workflows with Speech-to-Text (STT) and Text-to-Speech (TTS) across REST, SSE streaming, and real-time WebSockets.

> **Vachana** is a production-ready speech platform with high-accuracy STT and low-latency TTS for 10+ Indian languages, with 6 voices, multilingual and code-switching scenarios.

## Installation

```bash
pip install gnani-vachana
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
audio = client.synthesize(
    "नमस्ते, आप कैसे हैं?",
    voice="Karan",
    audio_config=AudioConfig(sample_rate=44100, encoding="linear_pcm", container="wav"),
)

with open("tts_output.wav", "wb") as f:
    f.write(audio)
```

### TTS SSE Streaming (lower latency)

```python
from gnani.tts import GnaniTTSStreamClient

client = GnaniTTSStreamClient(api_key="your-api-key")
audio = client.synthesize("Hello from Gnani TTS", voice="Karan", output_file="tts_sse.wav")
```

### TTS Realtime WebSocket (lowest latency)

```python
import asyncio
from gnani.tts import GnaniTTSRealtimeClient

async def main():
    async with GnaniTTSRealtimeClient(api_key="your-api-key") as client:
        audio = await client.synthesize_and_collect(
            "Hello from Gnani TTS", voice="Karan", output_file="tts_realtime.wav",
        )

asyncio.run(main())
```

## Authentication

All APIs (STT REST, STT Realtime, TTS) require a single API key:

| Parameter | Header         | Description                           |
|-----------|----------------|---------------------------------------|
| `api_key` | `X-API-Key-ID` | API key identifier for authentication |

### Obtaining Credentials

Email **[speechstack@gnani.ai](mailto:speechstack@gnani.ai)** with your name, company, and use case. Credentials are typically provisioned within 1 business day, and all new accounts receive **free credits** -- no credit card required.

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

**Code-switching** — pass comma-separated codes for multilingual audio:

```python
result = client.transcribe("meeting.wav", language_code="en-IN,hi-IN")
```

**Auto-detect (streaming only):**

```python
from gnani.stt import GnaniSTTStreamClient

stream = GnaniSTTStreamClient(api_key="key", language_code=GnaniSTTStreamClient.AUTO_DETECT)
```

---

### TTS Voices

| Voice   | Gender | Description              |
|---------|--------|--------------------------|
| Karan   | Male   | Bold, Trustworthy        |
| Simran  | Female | Confident, Bright        |
| Nara    | Female | Gentle, Expressive       |
| Riya    | Female | Cheerful, Energetic      |
| Viraj   | Male   | Commanding, Dynamic      |
| Raju    | Male   | Grounded, Conversational |

### TTS Languages (Text-to-Speech)

TTS uses ISO 639 language codes (e.g. `hi`, `bn`). Note: TTS does **not** use the `-IN` suffix.

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

### Audio Format

| Property    | 16 kHz                | 8 kHz               |
|-------------|----------------------|----------------------|
| Encoding    | PCM signed 16-bit LE | PCM signed 16-bit LE |
| Sample Rate | 16,000 Hz            | 8,000 Hz             |
| Channels    | 1 (mono)             | 1 (mono)             |
| Chunk Size  | 512 samples (32 ms)  | 512 samples (64 ms)  |
| Frame Bytes | 1,024                | 1,024                |

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

### TTS REST

```python
from gnani.tts import GnaniTTSClient

client = GnaniTTSClient(api_key="your-api-key")
audio = client.synthesize("यह एक टेस्ट है", voice="Karan")
with open("tts_rest.wav", "wb") as f:
    f.write(audio)
```

### TTS Streaming (SSE)

Lower latency than REST — audio is streamed via Server-Sent Events.

```python
from gnani.tts import GnaniTTSStreamClient, AudioConfig

client = GnaniTTSStreamClient(api_key="your-api-key")

# synthesize() collects all SSE chunks and returns a valid WAV file
audio = client.synthesize(
    "Streaming TTS response",
    voice="Raju",
    audio_config=AudioConfig(sample_rate=16000, encoding="linear_pcm", container="wav"),
    output_file="tts_sse.wav",
)
```

For raw PCM streaming (e.g. real-time playback), use `synthesize_stream()`:

```python
for pcm_chunk in client.synthesize_stream("Hello!", voice="Karan"):
    play_audio(pcm_chunk)  # raw PCM, no WAV header
```

### TTS Realtime (WebSocket)

Lowest latency — audio is streamed over a persistent WebSocket connection.

```python
import asyncio
from gnani.tts import GnaniTTSRealtimeClient, AudioConfig

async def main():
    async with GnaniTTSRealtimeClient(api_key="your-api-key") as client:
        # synthesize_and_collect() returns a valid WAV file
        audio = await client.synthesize_and_collect(
            "Realtime TTS response",
            voice="Simran",
            audio_config=AudioConfig(sample_rate=16000, encoding="linear_pcm", container="wav"),
            output_file="tts_realtime.wav",
        )

asyncio.run(main())
```

For raw PCM streaming (e.g. real-time playback):

```python
async with GnaniTTSRealtimeClient(api_key="your-api-key") as client:
    async for pcm_chunk in client.synthesize("Hello!", voice="Karan"):
        play_audio(pcm_chunk)  # raw PCM, no WAV header
```

### TTS Voices

6 voices are available. List them programmatically:

```python
from gnani.tts import GnaniTTSClient

print(GnaniTTSClient.supported_voices())
```

Available voices: `Karan`, `Simran`, `Nara`, `Riya`, `Viraj`, `Raju`.

## Audio Requirements

### REST API

| Constraint       | Value                                      |
|------------------|--------------------------------------------|
| Formats          | WAV, MP3, FLAC, OGG, M4A                   |
| Max duration     | 60 seconds                                 |
| Channels         | Mono or stereo                             |
| Sample rate      | Automatically converted to 16 kHz mono     |

### Realtime Streaming

| Constraint       | Value                                                  |
|------------------|--------------------------------------------------------|
| Encoding         | Raw PCM, signed 16-bit little-endian                   |
| Sample rate      | 16,000 Hz or 8,000 Hz                                  |
| Channels         | 1 (mono)                                               |
| Frame size       | 1,024 bytes (512 samples)                              |
| Pacing           | Send frames at real-time cadence for best VAD accuracy |

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

## Documentation

Full API reference and guides are available at **[docs.gnani.ai](https://docs.gnani.ai/)**.

- [STT REST API](https://docs.gnani.ai/api/STT/speech-to-text)
- [STT Realtime WebSocket](https://docs.gnani.ai/api/STT/stt-websocket)
- [TTS REST API](https://docs.gnani.ai/api/TTS/tts-inference)
- [TTS Streaming (SSE)](https://docs.gnani.ai/api/TTS/tts-sse)
- [TTS Realtime WebSocket](https://docs.gnani.ai/api/TTS/tts-websocket)

## License

This project is licensed under the MIT License -- see the [LICENSE](LICENSE) file for details.
