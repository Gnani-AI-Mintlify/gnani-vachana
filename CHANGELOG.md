# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.5] - 2026-07-14

### Removed

- **Code-switching and auto-detect language modes** — REST and WebSocket STT now accept only single BCP-47 language codes (e.g. `"hi-IN"`). Removed comma-separated `language_code` values, `GnaniSTTStreamClient.AUTO_DETECT`, and the `preferred_language` parameter.
## [0.7.4] - 2026-07-14

## [0.7.3] - 2026-07-14

### Changed

- **Local development uses [uv](https://docs.astral.sh/uv/)** — `scripts/setup.sh` creates `.venv` with `uv venv` and installs via `uv sync --extra dev`. `Makefile`, `release.sh`, and CI workflows use `uv run`. `uv.lock` is generated locally for reproducible installs.

## [0.7.2] - 2026-07-14

### Fixed

- **WebSocket compatibility with `websockets` 12.x** — the STT and TTS realtime clients passed `additional_headers` to `websockets.connect()`, which only exists in `websockets >= 13`. On `websockets` 12.x (still allowed by the `>=12.0` requirement, and commonly pinned by other libraries such as `gradio-client`, which requires `<13`) the connection failed with `TypeError: create_connection() got an unexpected keyword argument 'additional_headers'`. The clients now select `additional_headers` (>= 13) or `extra_headers` (< 13) based on the installed version, so all realtime STT/TTS flows work across `websockets` 12–15.

### Added

- **STT streaming sample rates** — `GnaniSTTStreamClient` now accepts `44100` and `48000` Hz in addition to `8000` and `16000`, matching the documented `x-sample-rate` values. See [STT Realtime — Connection Headers](https://docs.gnani.ai/api/STT/stt-websocket). New constants `SAMPLE_RATE_44K`, `SAMPLE_RATE_48K`, and `STREAM_SUPPORTED_SAMPLE_RATES` are exported from `gnani.stt`.
- **STT REST language auto-detection** — `transcribe()` and `transcribe_bytes()` now accept any comma-separated combination of supported single language codes (e.g. `"en-IN,ta-IN"`) to enable server-side auto-detection, per the [REST STT docs](https://docs.gnani.ai/api/STT/speech-to-text).
- **CI workflow** — GitHub Actions `CI` workflow runs ruff, mypy, and the test suite across Python 3.9–3.13 on every push and pull request.
- **Test suite is now committed** — `tests/`, `Makefile`, and `scripts/` are no longer gitignored, so the full unit + live integration suite can be run in CI and verified independently (`git clone` → `pip install -e ".[dev]"` → `pytest tests/`). An sdist `include = ["/gnani"]` filter was added so the published wheel/sdist still ship only `gnani/`; `playground/` and generated `tests/output/` artifacts stay gitignored.

### Changed

- **STT REST response** — documented that the API response no longer includes a `timestamp` field. It now returns `success`, `request_id`, and `transcript` plus metadata (`model`, `processing_time`, `end_to_end_latency`). Docstrings updated accordingly.
- **PyPI publish** — the publish workflow now triggers on `v*.*.*` tag pushes (in addition to GitHub Releases), validates that the tag matches the `pyproject.toml` version, and runs `twine check` on the built distribution before uploading.

### Notes

- **TTS `oggopus` encoding** requires `container="raw"` (the API rejects `oggopus` with `container="ogg"`). The `ogg` container is not accepted for any encoding. Use `container="raw"` for Opus output and `container="wav"`/`"mp3"` for PCM output.

## [0.7.1] - 2026-07-02

### Changed

- **TTS voices** — updated to 4 official voices: Pranav, Kaveri, Shubhra, Deepak. Removed legacy voices (Karan, Simran, Nara, Riya, Viraj, Raju). Default voice changed from `"Karan"` to `"Pranav"`. See [Available Voices](https://docs.gnani.ai/api/TTS/tts-sse#available-voices).

## [0.7.0] - 2026-07-01

### Added

- Comprehensive QA test suite, `Makefile`, versioning scripts.
- Docstring updates (Google-style), ruff ignore rules for pre-existing patterns.

## [0.6.0] - 2026-06-24

### Changed

- **Package renamed** — PyPI distribution name changed from `gnani-vachana` to `gnani`. Install with `pip install gnani`. The Python import namespace (`gnani`) is unchanged.

## [0.5.1] - 2026-06-23

### Removed

- **`language` parameter from TTS** — removed `language` from `GnaniTTSRealtimeClient.synthesize()`, `synthesize_events()`, and `synthesize_and_collect()`. TTS no longer accepts a language parameter.
- **`DEFAULT_LANGUAGE` and `SUPPORTED_LANGUAGES` constants** — removed from `gnani.tts` exports.

### Changed

- **STT documentation** — clarified that only REST and Streaming (WebSocket) modes are integrated; no batch STT. Added PCM specification details with link to [STT Realtime — PCM Specification](https://docs.gnani.ai/api/STT/stt-websocket#pcm-specification).

## [0.4.3] - 2026-05-31

### Removed

- **`organization_id` and `user_id` parameters** — removed from `GnaniSTTClient`. Authentication now requires only `api_key` (via constructor or `GNANI_API_KEY` env var). The `X-Organization-ID` and `X-API-User-ID` headers are no longer sent.

## [0.4.1] - 2026-05-31
- **Removing the user_id and organization_id** — removing the organization_id and user_id

## [0.4.0] - 2026-05-22

### Fixed

- **SSE streaming WAV output** — each SSE chunk from the server is a complete WAV file; the SDK now strips per-chunk WAV headers and reassembles a single valid WAV. Previously, concatenated chunks produced a broken multi-header file with no playable audio.
- **WebSocket streaming WAV output** — same per-chunk WAV header stripping applied to the WebSocket client (`GnaniTTSRealtimeClient`). `synthesize()` now yields raw PCM and `synthesize_and_collect()` returns a valid WAV file.

### Removed

- **`vachana-voice-v2` model** — removed entirely along with all legacy v2 voices (`sia`, `raju`, `kanika`, `nikita`, `ravan`, `simran`, `karan`, `neha`).
- **`vachana-voice-v1` model** — removed from `SUPPORTED_MODELS`.
- **Language-specific v3 voices** — removed 320 language-specific voices. Only the 6 primary voices remain.
- `LEGACY_V2_VOICES` and `V3_VOICES` constants removed from exports.

### Changed

- `SUPPORTED_VOICES` now contains only 6 voices: `Karan`, `Simran`, `Nara`, `Riya`, `Viraj`, `Raju`.
- `SUPPORTED_MODELS` now contains only `vachana-voice-v3`.
- `SUPPORTED_LANGUAGES` reduced to 10 languages: Assamese, Bengali, English, Hindi, Kannada, Malayalam, Marathi, Odia, Tamil, Telugu.

## [0.3.0] - 2026-05-21

### Added

- **22 TTS languages** — Assamese, Bengali, Bodo, Dogri, Gujarati, Hindi, Kannada, Kashmiri, Konkani, Maithili, Malayalam, Manipuri, Marathi, Nepali, Odia, Punjabi, Sanskrit, Santhali, Sindhi, Tamil, Telugu, Urdu.
- **23 STT languages** — expanded from 10 to 23 languages with Assamese, Bodo, Dogri, Kashmiri, Konkani, Maithili, Manipuri, Nepali, Odia, Sanskrit, Santhali, Sindhi, and Urdu.
- `SUPPORTED_LANGUAGES` constant exported from `gnani.tts` for TTS language validation.

### Changed

- **Default TTS model** set to `vachana-voice-v3`.
- **Default TTS voice** changed from `"sia"` to `"Karan"`.
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
- Auto-detect language mode via `GnaniSTTStreamClient.AUTO_DETECT`.
- New exceptions: `StreamConnectionError`, `StreamClosedError`, `StreamError`.
- `STREAM_SUPPORTED_LANGUAGES`, `SAMPLE_RATE_16K`, `SAMPLE_RATE_8K`, `STREAM_CHUNK_BYTES`, `STREAM_CHUNK_SAMPLES` constants.

### Changed

- Bumped version from `0.1.3` to `0.2.0`.
- Added `websockets>=12.0` as a dependency.
- Updated `README.md` with comprehensive realtime streaming documentation, event types reference, and error handling guide.

## [0.1.3] - 2025-12-26

### Added

- Initial public release of the `gnani` (formerly `gnani-vachana`) Python SDK.
- `GnaniSTTClient` for REST-based file transcription.
- Support for 10 Indian languages with multilingual auto-detection.
- `transcribe()` and `transcribe_bytes()` methods.
- Header-based authentication with environment variable fallback.
- Custom exceptions: `GnaniSTTError`, `AuthenticationError`, `InvalidAudioError`, `APIError`.
- GitHub Actions workflow for PyPI publishing.

[Unreleased]: https://github.com/Gnani-AI-Mintlify/Gnani-Vachana/compare/v0.7.1...HEAD
[0.7.1]: https://github.com/Gnani-AI-Mintlify/Gnani-Vachana/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/Gnani-AI-Mintlify/Gnani-Vachana/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/Gnani-AI-Mintlify/Gnani-Vachana/compare/v0.5.1...v0.6.0
[0.4.3]: https://github.com/Gnani-AI-Mintlify/Gnani-Vachana/compare/v0.4.1...v0.4.3
[0.4.1]: https://github.com/Gnani-AI-Mintlify/Gnani-Vachana/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/Gnani-AI-Mintlify/Gnani-Vachana/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/Gnani-AI-Mintlify/Gnani-Vachana/compare/v0.2.2...v0.3.0
[0.2.2]: https://github.com/Gnani-AI-Mintlify/Gnani-Vachana/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/Gnani-AI-Mintlify/Gnani-Vachana/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/Gnani-AI-Mintlify/Gnani-Vachana/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/Gnani-AI-Mintlify/Gnani-Vachana/releases/tag/v0.1.3
