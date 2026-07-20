import logging
import uuid

logger = logging.getLogger("gnani")

if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)-5s %(name)s | %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.DEBUG)


def resolve_request_id(request_id: str | None) -> str:
    """Return *request_id* or auto-generate one in ``req_<hex>`` format."""
    return request_id or f"req_{uuid.uuid4().hex[:12]}"
