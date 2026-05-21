# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-05-21

### Added

- **22 TTS languages** — Assamese, Bengali, Bodo, Dogri, Gujarati, Hindi, Kannada, Kashmiri, Konkani, Maithili, Malayalam, Manipuri, Marathi, Nepali, Odia, Punjabi, Sanskrit, Santhali, Sindhi, Tamil, Telugu, Urdu.
- **250+ v3 TTS voices** (capitalized, e.g. `"Karan"`, `"Simran"`) — language-specific voices covering all 22 scheduled languages with both male and female options per language.
- **23 STT languages** — expanded from 10 to 23 languages with Assamese, Bodo, Dogri, Kashmiri, Konkani, Maithili, Manipuri, Nepali, Odia, Sanskrit, Santhali, Sindhi, and Urdu.
- `SUPPORTED_LANGUAGES` constant exported from `gnani.tts` for TTS language validation.
- `LEGACY_V2_VOICES` and `V3_VOICES` constants to distinguish between model generations.
- Legacy v2 voices (lowercase: `"sia"`, `"raju"`, `"karan"`, etc.) remain supported for backward compatibility with `vachana-voice-v2`.

### Changed

- **Default TTS model** upgraded from `vachana-voice-v2` to `vachana-voice-v3`.
- **Default TTS voice** changed from `"sia"` to `"Karan"`.
- `SUPPORTED_VOICES` is now the union of legacy v2 and new v3 voices. Casing matters: `"karan"` targets v2, `"Karan"` targets v3.
- `SUPPORTED_MODELS` now includes `vachana-voice-v3`, `vachana-voice-v2`, and `vachana-voice-v1`.
- `AUTO_DETECT_LANGUAGES` dynamically built from the supported language set.

## [0.2.2] - 2026-04-27

### Added

- **`output_file` parameter** on all TTS `synthesize` methods — pass a file path (str or `Path`) to save the synthesised audio directly to disk.
  - `GnaniTTSClient.synthesize()` — writes the full audio after download.
  - `GnaniTTSStreamClient.synthesize_stream()` — streams each chunk to the file as it arrives.
  - `GnaniTTSStreamClient.synthesize()` — writes the collected audio after all chunks are received.
  - `GnaniTTSRealtimeClient.synthesize_and_collect()` — writes the collected audio after the WebSocket stream completes.
- Internal `_save_audio` helper for consistent file writing with automatic parent-directory creation.
- **`language` parameter** on `GnaniTTSRealtimeClient.synthesize()` and `synthesize_and_collect()` — specify the language/locale for WebSocket TTS (defaults to `"IND-IN"`).
- `DEFAULT_LANGUAGE` constant (`"IND-IN"`) exported from `gnani.tts`.
- **`synthesize_events()`** method on `GnaniTTSRealtimeClient` — yields typed `TTSStreamEvent` objects (`TTSStartEvent`, `TTSAudioChunkEvent`, `TTSCompletedEvent`) with full metadata (`request_id`, `chunk_index`, `is_final`).
- `TTSStartEvent` dataclass for the stream-started notification (includes `request_id`).

### Changed

- **WebSocket TTS message parsing** — the server sends JSON text frames (`type: "start"`, `"audio"`, `"complete"`, `"error"`), not raw binary. `synthesize()` now decodes the base64 `data.audio` field from each `"audio"` frame and yields the raw bytes. Previously the code expected binary WebSocket frames and silently dropped all messages.
- **WebSocket TTS request body** now always includes `voice` and `language` as top-level fields (previously `voice` was omitted when `speaker_embedding` was provided). The body now matches the `wss://api.vachana.ai/api/v1/tts` contract: `{ text, voice, language, model, audio_config }`.
- `TTSAudioChunkEvent` now includes an `is_final` field.
- `TTSCompletedEvent` now includes a `request_id` field.

## [0.2.1] - 2026-04-20

### Added

- **Text-to-Speech (REST)** via `GnaniTTSClient` — synchronous synthesis returning complete audio bytes from `POST /api/v1/tts/inference`.
- **Text-to-Speech (Streaming)** via `GnaniTTSStreamClient` — SSE-based streaming that yields audio chunks as they are generated from `POST /api/v1/tts/sse`.
- **Text-to-Speech (Realtime)** via `GnaniTTSRealtimeClient` — async WebSocket client that streams audio with the lowest latency over `wss://api.vachana.ai/api/v1/tts`.
- `AudioConfig` dataclass for configuring sample rate, encoding, container, channels, sample width, and MP3 bitrate.
- `SpeakerEmbedding` dataclass for voice cloning support (overrides the `voice` parameter).
- `TTSAudioChunkEvent` and `TTSCompletedEvent` typed dataclasses for realtime stream events.
- New `gnani.tts` sub-package with its own exception hierarchy: `GnaniTTSError`, `AuthenticationError`, `APIError`, `StreamConnectionError`, `StreamClosedError`, `StreamError`.
- Constants: `SUPPORTED_VOICES`, `SUPPORTED_ENCODINGS`, `SUPPORTED_CONTAINERS`, `SUPPORTED_BITRATES`, `SUPPORTED_MODELS`, `DEFAULT_MODEL`.
- `gnani/__init__.py` now re-exports both `gnani.stt` and `gnani.tts` sub-packages.

## [0.2.0] - 2026-04-16

### Added

- **Realtime WebSocket streaming** via `GnaniSTTStreamClient` — stream raw PCM audio and receive live transcription events over `wss://api.vachana.ai/stt/v3/stream`.
- Typed event dataclasses: `StreamConnectedEvent`, `StreamProcessingEvent`, `StreamTranscriptEvent`, `StreamErrorEvent`.
- Async context manager and async iterator support for the streaming client.
- `stream_audio()` high-level helper with callback support for transcript, processing, and error events.
- Support for 8 kHz and 16 kHz audio sample rates in streaming mode.
- New experimental language codes for streaming: `en-hi-IN-latn` (Hinglish Latin), `en-hi-in-cm` (Hinglish code-mixed).
- Auto-detect language mode via `GnaniSTTStreamClient.AUTO_DETECT`.
- New exceptions: `StreamConnectionError`, `StreamClosedError`, `StreamError`.
- `STREAM_SUPPORTED_LANGUAGES`, `SAMPLE_RATE_16K`, `SAMPLE_RATE_8K`, `STREAM_CHUNK_BYTES`, `STREAM_CHUNK_SAMPLES` constants.

### Changed

- Bumped version from `0.1.3` to `0.2.0`.
- Added `websockets>=12.0` as a dependency.
- Updated `README.md` with comprehensive realtime streaming documentation, event types reference, and error handling guide.

## [0.1.3] - 2025-12-26

### Added

- Initial public release of the `gnani-vachana` Python SDK.
- `GnaniSTTClient` for REST-based file transcription.
- Support for 10 Indian languages plus English-Hindi code-switching.
- `transcribe()` and `transcribe_bytes()` methods.
- Header-based authentication with environment variable fallback.
- Custom exceptions: `GnaniSTTError`, `AuthenticationError`, `InvalidAudioError`, `APIError`.
- GitHub Actions workflow for PyPI publishing.

[Unreleased]: https://github.com/Gnani-AI-Mintlify/Gnani-Vachana/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/Gnani-AI-Mintlify/Gnani-Vachana/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/Gnani-AI-Mintlify/Gnani-Vachana/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/Gnani-AI-Mintlify/Gnani-Vachana/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Gnani-AI-Mintlify/Gnani-Vachana/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/Gnani-AI-Mintlify/Gnani-Vachana/releases/tag/v0.1.3
