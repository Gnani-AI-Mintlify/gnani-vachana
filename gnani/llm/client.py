"""Clients for the Gnani LLM API: the official ``openai`` package, set up for Gnani.

The Gnani chat completions API is OpenAI-compatible, so these are thin subclasses of
``openai.OpenAI`` and ``openai.AsyncOpenAI``. They only fix what differs:

* the base URL, ``GNANI_API_KEY`` and the default model;
* **streaming**: the API streams unless told not to (OpenAI's does not), and the OpenAI
  package leaves ``stream`` out when it is not given, so a plain call would come back as
  raw server-sent events. ``create()`` sends ``stream=False`` unless the caller says
  otherwise;
* **gateway errors**: a rejected API key comes back in the gateway's own shape,
  ``{"detail": {"error_code", "message"}}``, which the package would reduce to
  ``Error code: 401``. The real message and ``error_code`` are put back.

Everything else (typed responses, streaming, retries, timeouts, the error classes) is
the ``openai`` package's own. This module needs it: ``pip install gnani-vachana[llm]``.
"""

from __future__ import annotations

import os
from typing import Any

try:
    import openai
    from openai.resources.chat import completions as _completions
    from openai.resources.chat.chat import AsyncChat, Chat
except ImportError as exc:  # pragma: no cover - exercised without the extra
    raise ImportError(
        "gnani.llm needs the 'openai' package. Install it with: pip install 'gnani-vachana[llm]'"
    ) from exc

DEFAULT_BASE_URL = "https://api.vachana.ai"
DEFAULT_MODEL = "gnani-evon-v3"

# Reasoning models spend part of the budget thinking before they answer, so the first
# byte of a plain request can be slow. This is a per-read timeout, so it also applies
# between streamed chunks.
DEFAULT_TIMEOUT = 120.0

_API_VERSION_PATH = "/v1"


def _normalize_base_url(base_url: str) -> str:
    """``https://host`` or ``https://host/v1`` -> ``https://host/v1``.

    The OpenAI package appends ``/chat/completions`` to the base URL, so it must end
    with ``/v1``. Accepting both forms keeps a bare host (as the STT and TTS clients
    take) working.
    """
    base_url = base_url.rstrip("/")
    if not base_url.endswith(_API_VERSION_PATH):
        base_url += _API_VERSION_PATH
    return base_url


def _resolve_api_key(api_key: str | None) -> str:
    resolved = api_key if api_key else os.getenv("GNANI_API_KEY", "")
    if not resolved:
        raise openai.OpenAIError(
            "api_key is required. Pass it directly or set the GNANI_API_KEY environment variable."
        )
    return resolved


def _gateway_error(exc: openai.APIStatusError) -> openai.APIStatusError | None:
    """Rebuild a status error from the gateway's ``{"detail": {...}}`` body, if it is one."""
    body = exc.body
    detail = body.get("detail") if isinstance(body, dict) else None
    if not isinstance(detail, dict) or not detail.get("message"):
        return None
    error_code = detail.get("error_code")
    message = str(detail["message"])
    if error_code:
        message = f"{message} ({error_code})"
    rebuilt = type(exc)(
        f"Error code: {exc.status_code} - {message}", response=exc.response, body=body
    )
    if error_code:
        rebuilt.code = error_code
    return rebuilt


def _client_options(
    api_key: str | None, base_url: str, timeout: float, kwargs: dict[str, Any]
) -> dict[str, Any]:
    key = _resolve_api_key(api_key)
    options = {
        "api_key": key,
        "base_url": _normalize_base_url(base_url),
        "timeout": timeout,
        **kwargs,
    }
    # ``openai`` sends the key as ``Authorization: Bearer``. The production gateway only reads
    # ``X-API-Key-ID`` (as the STT and TTS clients send it) and answers MISSING_API_KEY otherwise,
    # so send both. A caller's own ``default_headers`` win.
    options["default_headers"] = {"X-API-Key-ID": key, **(kwargs.get("default_headers") or {})}
    return options


class _Completions(_completions.Completions):
    """``client.chat.completions``: blocking ``stream=False`` default, gateway errors."""

    def create(self, *args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("model", DEFAULT_MODEL)
        kwargs.setdefault("stream", False)
        try:
            return super().create(*args, **kwargs)
        except openai.APIStatusError as exc:
            replacement = _gateway_error(exc)
            if replacement is None:
                raise
            raise replacement from exc


class _AsyncCompletions(_completions.AsyncCompletions):
    """``client.chat.completions`` of the async client."""

    async def create(self, *args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("model", DEFAULT_MODEL)
        kwargs.setdefault("stream", False)
        try:
            return await super().create(*args, **kwargs)
        except openai.APIStatusError as exc:
            replacement = _gateway_error(exc)
            if replacement is None:
                raise
            raise replacement from exc


# ``chat`` and ``chat.completions`` are plain instance attributes in older ``openai``
# releases and cached properties in newer ones. Assigning them in ``__init__`` replaces
# either, so the same code works across the supported range.


class _Chat(Chat):
    def __init__(self, client: Any) -> None:
        super().__init__(client)
        self.completions = _Completions(client)  # type: ignore[assignment, misc]


class _AsyncChat(AsyncChat):
    def __init__(self, client: Any) -> None:
        super().__init__(client)
        self.completions = _AsyncCompletions(client)  # type: ignore[assignment, misc]


class GnaniLLMClient(openai.OpenAI):
    """Client for Gnani's chat completions API (``POST /v1/chat/completions``).

    A subclass of ``openai.OpenAI``, so it is used the same way, and every
    ``openai`` option (``max_retries``, ``default_headers``, ``http_client``, ...) works.
    The API is stateless: ``messages`` must carry the whole conversation on every call.

    Parameters
    ----------
    api_key : str, optional
        Gnani API key. Falls back to the ``GNANI_API_KEY`` environment variable
        (``OPENAI_API_KEY`` is never read). The key must have access to the LLM API,
        otherwise the API answers ``403 SCOPE_NOT_ALLOWED``.
    base_url : str
        API base URL. Defaults to ``https://api.vachana.ai``; a trailing ``/v1`` is
        added when missing.
    timeout : float
        Read timeout in seconds. Defaults to ``120``.
    **kwargs
        Passed to ``openai.OpenAI``, e.g. ``max_retries`` (default ``2``).

    Examples
    --------
    ::

        client = GnaniLLMClient(api_key="key")

        reply = client.chat.completions.create(
            messages=[{"role": "user", "content": "Say hello in Hindi."}],
        )
        print(reply.choices[0].message.content)

        for chunk in client.chat.completions.create(
            messages=[{"role": "user", "content": "Count to 3."}],
            stream=True,
        ):
            print(chunk.choices[0].delta.content or "", end="")
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        **kwargs: Any,
    ) -> None:
        super().__init__(**_client_options(api_key, base_url, timeout, kwargs))
        self.chat = _Chat(self)  # type: ignore[assignment, misc]


class GnaniAsyncLLMClient(openai.AsyncOpenAI):
    """Async client for Gnani's chat completions API.

    The same as :class:`GnaniLLMClient`, on ``openai.AsyncOpenAI``: calls are awaited
    and a stream is read with ``async for``.

    Examples
    --------
    ::

        client = GnaniAsyncLLMClient(api_key="key")

        reply = await client.chat.completions.create(
            messages=[{"role": "user", "content": "Say hello in Hindi."}],
        )
        print(reply.choices[0].message.content)

        stream = await client.chat.completions.create(
            messages=[{"role": "user", "content": "Count to 3."}],
            stream=True,
        )
        async for chunk in stream:
            print(chunk.choices[0].delta.content or "", end="")
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        **kwargs: Any,
    ) -> None:
        super().__init__(**_client_options(api_key, base_url, timeout, kwargs))
        self.chat = _AsyncChat(self)  # type: ignore[assignment, misc]
