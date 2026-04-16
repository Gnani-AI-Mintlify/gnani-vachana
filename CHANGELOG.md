# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.2.0]: https://github.com/Gnani-AI-Mintlify/Gnani-Vachana/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/Gnani-AI-Mintlify/Gnani-Vachana/releases/tag/v0.1.3
