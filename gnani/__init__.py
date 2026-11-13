"""Gnani - Python SDK for Gnani.ai's speech and language AI platform."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

from gnani import stt, tts

if TYPE_CHECKING:
    from gnani import llm

__all__ = ["llm", "stt", "tts"]


def __getattr__(name: str) -> Any:
    # ``gnani.llm`` needs the optional ``openai`` package, so it is imported on first
    # use: ``import gnani`` keeps working for STT and TTS users without it.
    if name == "llm":
        return importlib.import_module("gnani.llm")
    raise AttributeError(f"module 'gnani' has no attribute {name!r}")
