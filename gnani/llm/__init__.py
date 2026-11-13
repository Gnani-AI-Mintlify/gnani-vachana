"""Gnani LLM - clients for Gnani's chat completions API, on the ``openai`` package.

Needs the ``llm`` extra: ``pip install 'gnani-vachana[llm]'``.
"""

from gnani.llm.client import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT,
    GnaniAsyncLLMClient,
    GnaniLLMClient,
)

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "DEFAULT_TIMEOUT",
    "GnaniAsyncLLMClient",
    "GnaniLLMClient",
]
