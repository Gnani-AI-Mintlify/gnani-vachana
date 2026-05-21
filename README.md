# gnani-vachana
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Official Python client for **[Vachana Speech APIs](https://docs.inya.ai/vachana/introduction/introduction)** by [Gnani.ai](https://gnani.ai). Build multilingual voice workflows with Speech-to-Text (STT) and Text-to-Speech (TTS) across REST, SSE streaming, and real-time WebSockets.

> **Vachana** is a production-ready speech platform with high-accuracy STT and low-latency TTS for 22+ Indian languages, including 250+ voices, multilingual and code-switching scenarios.

## Installation

```bash
pip install gnani-vachana
```

Requires **Python 3.9+**.

## Quick Start

### STT REST (file-based transcription)

```python
from gnani.stt import GnaniSTTClient

client = GnaniSTTClient(
    organization_id="your-organization-id",
    api_key="your-api-key",
    user_id="your-user-id",
)

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

### TTS Realtime (WebSocket)

```python
import asyncio
from gnani.tts import GnaniTTSRealtimeClient

async def main():
    async with GnaniTTSRealtimeClient(api_key="your-api-key") as client:
        with open("tts_realtime.wav", "wb") as f:
            async for chunk in client.synthesize("Hello from Gnani TTS", voice="Karan"):
                f.write(chunk)

asyncio.run(main())
```

## Authentication

### STT REST API

The REST API uses header-based authentication. Every request requires three credentials:

| Parameter          | Header              | Description                        |
|--------------------|---------------------|------------------------------------|
| `organization_id`  | `X-Organization-ID` | Your organisation identifier       |
| `api_key`          | `X-API-Key-ID`      | Secret key for authentication      |
| `user_id`          | `X-API-User-ID`     | Your user / organisation name      |

### STT Realtime Streaming API

The WebSocket streaming API requires a single API key:

| Parameter   | Header         | Description                           |
|-------------|----------------|---------------------------------------|
| `api_key`   | `x-api-key-id` | API key identifier for authentication |

### TTS API (REST, SSE, Realtime)

All TTS interfaces require a single API key:

| Parameter | Header         | Description                           |
|-----------|----------------|---------------------------------------|
| `api_key` | `X-API-Key-ID` | API key identifier for authentication |

### Obtaining Credentials

Email **[speechstack@gnani.ai](mailto:speechstack@gnani.ai)** with your name, company, and use case. Credentials are typically provisioned within 1 business day, and all new accounts receive **free credits** -- no credit card required.

### Passing Credentials

**Option 1 -- Constructor arguments:**

```python
from gnani.stt import GnaniSTTClient, GnaniSTTStreamClient
from gnani.tts import GnaniTTSClient, GnaniTTSRealtimeClient, GnaniTTSStreamClient

# REST client
client = GnaniSTTClient(
    organization_id="your-organization-id",
    api_key="your-api-key",
    user_id="your-user-id",
)

# Streaming client
stream = GnaniSTTStreamClient(api_key="your-api-key")

# TTS clients
tts_rest = GnaniTTSClient(api_key="your-api-key")
tts_stream = GnaniTTSStreamClient(api_key="your-api-key")
tts_realtime = GnaniTTSRealtimeClient(api_key="your-api-key")
```

**Option 2 -- Environment variables:**

```bash
# REST client credentials
export GNANI_ORGANIZATION_ID="your-organization-id"
export GNANI_API_KEY="your-api-key"
export GNANI_USER_ID="your-user-id"
```

```python
from gnani.stt import GnaniSTTClient, GnaniSTTStreamClient
from gnani.tts import GnaniTTSClient

client = GnaniSTTClient()           # picks up all three env vars
stream = GnaniSTTStreamClient()     # picks up GNANI_API_KEY
tts = GnaniTTSClient()              # picks up GNANI_API_KEY
```

## Supported Languages

### STT Languages (Speech-to-Text) — 10 languages

STT uses BCP-47 locale codes (e.g. `hi-IN`):

| Language        | Code      | Native Script |
|-----------------|-----------|---------------|
| English (India) | `en-IN`   | Latin         |
| Hindi           | `hi-IN`   | हिन्दी           |
| Gujarati        | `gu-IN`   | ગુજરાતી         |
| Tamil           | `ta-IN`   | தமிழ்          |
| Kannada         | `kn-IN`   | ಕನ್ನಡ          |
| Telugu          | `te-IN`   | తెలుగు         |
| Marathi         | `mr-IN`   | मराठी          |
| Bengali         | `bn-IN`   | বাংলা          |
| Malayalam       | `ml-IN`   | മലയാളം        |
| Punjabi         | `pa-IN`   | ਪੰਜਾਬੀ          |

**Code-switching** — pass comma-separated codes for multilingual audio:

```python
result = client.transcribe("meeting.wav", language_code="en-IN,hi-IN")
```

**Streaming-only experimental codes:**

| Language                     | Code             | Notes                             |
|------------------------------|------------------|-----------------------------------|
| Hinglish (Latin)             | `en-hi-IN-latn`  | Latin script (experimental)       |
| Hinglish (Code-mixed)        | `en-hi-in-cm`    | Latin + Devanagari (experimental) |
| Auto-detect                  | `AUTO_DETECT`     | All supported (experimental)     |

```python
from gnani.stt import GnaniSTTStreamClient

stream = GnaniSTTStreamClient(api_key="key", language_code="en-hi-IN-latn")
stream = GnaniSTTStreamClient(api_key="key", language_code=GnaniSTTStreamClient.AUTO_DETECT)
```

---

### TTS Languages (Text-to-Speech) — 22 languages

TTS uses ISO 639 language codes (e.g. `hi`, `bn`). Note: TTS does **not** use the `-IN` suffix.

| Language   | Code  | Sample Voices               |
|------------|-------|-----------------------------|
| Assamese   | `as`  | Priya, Ankita, Arjun        |
| Bengali    | `bn`  | Ananya, Barnali, Abhik      |
| Bodo       | `brx` | Anamika, Basanti, Anil      |
| Dogri      | `doi` | Asha, Bhavna, Ajay          |
| Gujarati   | `gu`  | Avani, Bansari, Akshay      |
| Hindi      | `hi`  | Aarav, Bharat, Deepak       |
| Kannada    | `kn`  | Anitha, Bhavani, Aditya     |
| Kashmiri   | `ks`  | Aafreen, Bilqees, Altaf     |
| Konkani    | `kok` | Alka, Bindiya, Agnelo       |
| Maithili   | `mai` | Archana, Binita, Amaresh    |
| Malayalam  | `ml`  | Ambika, Bindhu, Abhilash    |
| Manipuri   | `mni` | Achouba, Biren_M, Chaoba    |
| Marathi    | `mr`  | Aparna, Bharati, Amol       |
| Nepali     | `ne`  | Anita, Binita_N, Amar       |
| Odia       | `or`  | Anuradha, Bijayalaxmi       |
| Punjabi    | `pa`  | Amandeep, Balwinder         |
| Sanskrit   | `sa`  | Akshara, Bhavika, Achyut    |
| Santhali   | `sat` | Arjun_S, Birsa, Chand       |
| Sindhi     | `sd`  | Ameena, Bhagwanti           |
| Tamil      | `ta`  | Abinaya, Anbarasan          |
| Telugu     | `te`  | Alekhya, Bhargavi, Adithya  |
| Urdu       | `ur`  | Aiza, Bushra, Asad          |

Plus 6 **primary voices** that work across languages: `Karan`, `Simran`, `Nara`, `Riya`, `Viraj`, `Raju`.

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

```python
from gnani.tts import GnaniTTSStreamClient

client = GnaniTTSStreamClient(api_key="your-api-key")
with open("tts_sse.wav", "wb") as f:
    for chunk in client.synthesize_stream("Streaming TTS response", voice="Raju"):
        f.write(chunk)
```

### TTS Realtime (WebSocket)

```python
import asyncio
from gnani.tts import GnaniTTSRealtimeClient

async def main():
    async with GnaniTTSRealtimeClient(api_key="your-api-key") as client:
        audio = await client.synthesize_and_collect("Realtime TTS response", voice="Simran")
        with open("tts_realtime.wav", "wb") as f:
            f.write(audio)

asyncio.run(main())
```

### TTS Voices

250+ voices are available across 22 Indian languages. List them programmatically:

```python
from gnani.tts import GnaniTTSClient

print(GnaniTTSClient.supported_voices())
```

**v3 voices** (capitalized): `Karan`, `Simran`, `Nara`, `Riya`, `Viraj`, `Raju`, plus 250+ language-specific voices (e.g. `Aarav` for Hindi, `Priya` for Assamese, `Ananya` for Bengali).

**Legacy v2 voices** (lowercase, still supported): `sia`, `raju`, `kanika`, `nikita`, `ravan`, `simran`, `karan`, `neha`.

> **Casing matters:** `"karan"` (lowercase) uses `vachana-voice-v2`, while `"Karan"` (capitalized) uses `vachana-voice-v3`. Some names overlap between models — the casing determines which model is targeted.

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

Full API reference and guides are available at **[docs.inya.ai/vachana](https://docs.inya.ai/vachana/introduction/introduction)**.

- [STT REST API](https://docs.inya.ai/vachana/STT/speech-to-text)
- [STT Realtime WebSocket](https://docs.inya.ai/vachana/STT/stt-websocket)
- [TTS REST API](https://docs.inya.ai/vachana/TTS/tts-inference)
- [TTS Streaming (SSE)](https://docs.inya.ai/vachana/TTS/tts-sse)
- [TTS Realtime WebSocket](https://docs.inya.ai/vachana/TTS/tts-websocket)

## License

This project is licensed under the MIT License -- see the [LICENSE](LICENSE) file for details.
