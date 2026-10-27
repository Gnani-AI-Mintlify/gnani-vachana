"""Request options for the ``prisma-v3.0`` STT model, shared by every STT client.

``prisma-v3.0`` is one multilingual model for all ten languages. It can identify
the language itself (``language_code="indic-auto"``), take 2-4 *candidate*
languages as a hint, write in a third output style (``codemix``), and accept
request context (``keywords``, ``topic``, ``previous_text``, ``speaker_names``).
None of that applies to the other models, so these options are refused with any
other ``model`` rather than silently ignored.

The limits mirror asr-server's (``tatva_output``) so a bad value fails here,
before any audio is uploaded, instead of as a 400 from the API.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any, Union

PRISMA_V3_MODEL = "prisma-v3.0"
# "Let the model identify the language" on REST and streaming. Batch spells it
# "auto" and also accepts this.
INDIC_AUTO_LANGUAGE_CODE = "indic-auto"
# REST and streaming. "transliterate" writes Indic speech in Latin letters.
PRISMA_V3_FORMATS = ("verbatim", "transcribe", "codemix", "transliterate")
# Batch jobs: the controller's OutputFormat has no "transliterate".
PRISMA_V3_BATCH_FORMATS = ("verbatim", "transcribe", "codemix")

PRISMA_V3_MIN_CANDIDATES = 2
PRISMA_V3_MAX_CANDIDATES = 4
PRISMA_V3_MAX_KEYWORDS = 200
# Batch only: the controller still enforces a 30-character topic minimum.
PRISMA_V3_BATCH_TOPIC_MIN_CHARS = 30
PRISMA_V3_TOPIC_MAX_CHARS = 1600
PRISMA_V3_MAX_SPEAKER_NAMES = 4
# asr-server keeps only the last 600 characters of previous_text.
PRISMA_V3_PREVIOUS_KEEP_CHARS = 600

_TAG_MARKERS = ("<|", "|>")

# Batch only: the controller still refuses every other context shape. asr-server
# itself (REST and streaming) takes any combination of the four fields.
_BATCH_ALLOWED_CONTEXT = frozenset(
    {
        frozenset(),
        frozenset({"keywords"}),
        frozenset({"topic"}),
        frozenset({"topic", "keywords"}),
        frozenset({"speaker_names"}),
        frozenset({"previous_text"}),
    }
)

StrList = Union[str, Iterable[str], None]


def is_prisma_v3(model: str | None) -> bool:
    return (model or "").strip().lower() == PRISMA_V3_MODEL


def normalize_model(model: str | None) -> str | None:
    """Strip the name and use the canonical spelling of ``prisma-v3.0``."""
    if model is None:
        return None
    name = model.strip()
    if not name:
        return None
    return PRISMA_V3_MODEL if name.lower() == PRISMA_V3_MODEL else name


def require_prisma_v3(model: str | None, **options: Any) -> None:
    """Raise if any prisma-v3.0-only option is set for another model."""
    sent = [name for name, value in options.items() if value not in (None, "", [], ())]
    if sent and not is_prisma_v3(model):
        raise ValueError(
            f"{', '.join(sent)} {'is' if len(sent) == 1 else 'are'} only supported "
            f"with model={PRISMA_V3_MODEL!r} (got model={model!r})"
        )


def check_format(format: str, model: str | None) -> None:
    allowed: tuple[str, ...] = ("verbatim", "transcribe")
    if is_prisma_v3(model):
        allowed = PRISMA_V3_FORMATS
    if format not in allowed:
        hint = ""
        if format in PRISMA_V3_FORMATS:
            hint = f" ({format!r} needs model={PRISMA_V3_MODEL!r})"
        raise ValueError(
            f"format must be one of {', '.join(repr(a) for a in allowed)}, got {format!r}{hint}"
        )


def _to_list(field: str, value: StrList) -> list[str]:
    """A list, a JSON-array string, or a comma-separated string, trimmed."""
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{field} must be a list of strings") from exc
            if not isinstance(parsed, list):
                raise ValueError(f"{field} must be a list of strings")
            items: list[Any] = parsed
        else:
            items = text.split(",")
    else:
        items = list(value)
    out: list[str] = []
    for item in items:
        if not isinstance(item, str):
            raise ValueError(f"{field} must be a list of strings")
        word = item.strip()
        if word and word not in out:
            out.append(word)
    return out


def _check_markers(field: str, *values: str) -> None:
    for v in values:
        if any(m in v for m in _TAG_MARKERS):
            raise ValueError(f"{field} must not contain '<|' or '|>'")


def parse_candidates(value: StrList, supported: Mapping[str, str]) -> list[str]:
    """2-4 distinct candidate languages, as BCP-47 codes (order kept)."""
    codes = _to_list("language_candidates", value)
    bad = [c for c in codes if c not in supported]
    if bad:
        raise ValueError(
            f"Unsupported language_candidates {', '.join(repr(b) for b in bad)}. "
            f"Choose from: {', '.join(sorted(supported))}"
        )
    if not PRISMA_V3_MIN_CANDIDATES <= len(codes) <= PRISMA_V3_MAX_CANDIDATES:
        raise ValueError(
            f"language_candidates takes {PRISMA_V3_MIN_CANDIDATES}-{PRISMA_V3_MAX_CANDIDATES} "
            f"distinct languages, got {len(codes)}. For one language, pass it as "
            f"language_code instead."
        )
    return codes


def parse_keywords(value: StrList) -> list[str]:
    words = _to_list("keywords", value)
    _check_markers("keywords", *words)
    if len(words) > PRISMA_V3_MAX_KEYWORDS:
        raise ValueError(
            f"keywords takes at most {PRISMA_V3_MAX_KEYWORDS} items, got {len(words)}"
        )
    return words


def build_context(
    *,
    keywords: StrList = None,
    topic: str | None = None,
    previous_text: str | None = None,
    speaker_names: StrList = None,
    batch: bool = False,
) -> dict[str, Any]:
    """Validate the context options and return only those that were set.

    REST and streaming take any combination, and any non-empty ``topic`` or
    ``previous_text``. ``batch=True`` applies the batch controller's stricter
    rules: one of five combinations and a 30-character minimum topic.
    """
    ctx: dict[str, Any] = {}
    words = parse_keywords(keywords)
    if words:
        ctx["keywords"] = words
    if topic is not None and topic.strip():
        t = topic.strip()
        _check_markers("topic", t)
        low = PRISMA_V3_BATCH_TOPIC_MIN_CHARS if batch else 1
        if not low <= len(t) <= PRISMA_V3_TOPIC_MAX_CHARS:
            raise ValueError(
                f"topic must be {low}-{PRISMA_V3_TOPIC_MAX_CHARS} characters, got {len(t)}"
            )
        ctx["topic"] = t
    if previous_text is not None and previous_text.strip():
        p = previous_text.strip()
        _check_markers("previous_text", p)
        ctx["previous_text"] = p[-PRISMA_V3_PREVIOUS_KEEP_CHARS:]
    names = _to_list("speaker_names", speaker_names)
    if names:
        _check_markers("speaker_names", *names)
        if len(names) > PRISMA_V3_MAX_SPEAKER_NAMES:
            raise ValueError(
                f"speaker_names takes at most {PRISMA_V3_MAX_SPEAKER_NAMES} names, "
                f"got {len(names)}"
            )
        if any("\n" in n or "\r" in n for n in names):
            raise ValueError("speaker_names must each be a single line")
        ctx["speaker_names"] = names
    if batch and frozenset(ctx) not in _BATCH_ALLOWED_CONTEXT:
        raise ValueError(
            "prisma-v3.0 accepts one of: keywords, topic, topic + keywords, "
            f"speaker_names, or previous_text (got {' + '.join(sorted(ctx))})"
        )
    return ctx
