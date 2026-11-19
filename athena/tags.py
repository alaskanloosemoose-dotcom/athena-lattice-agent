"""
[[IMAGE: ...]] tags: Athena asks for a painting by ending a reply with one.

The tag is hidden from the streamed text and turned into a render request.
"""

import re
from typing import Iterable, Iterator, List, Tuple

_MARK = "[[IMAGE"
_TAG = re.compile(r"\[\[\s*IMAGE\s*:\s*(.+?)\s*\]\]", re.IGNORECASE | re.DOTALL)
_OPEN = re.compile(r"\[\[\s*IMAGE\s*:(.*)$", re.IGNORECASE | re.DOTALL)


def extract_image_requests(text: str) -> Tuple[str, List[str]]:
    """Return the text without tags and the descriptions they held."""
    requests = [m.strip() for m in _TAG.findall(text or "") if m.strip()]
    clean = _TAG.sub("", text or "")
    # A tag cut off by the token limit still carries a usable description.
    unclosed = _OPEN.search(clean)
    if unclosed:
        if unclosed.group(1).strip():
            requests.append(unclosed.group(1).strip().rstrip("]").strip())
        clean = clean[:unclosed.start()]
    return clean.strip(), requests


def _partial_mark(text: str) -> int:
    """Length of a trailing piece of text that could be the start of the marker."""
    for n in range(min(len(_MARK), len(text)), 0, -1):
        if text[-n:].upper() == _MARK[:n]:
            return n
    return 0


def visible_stream(chunks: Iterable[str], sink: List[str]) -> Iterator[str]:
    """Pass chunks through until a tag starts; append the full text to sink at the end.

    Only "[[IMAGE" is held back, so code such as [[1, 2]] still streams.
    """
    full = ""
    shown = 0
    found = False
    for chunk in chunks:
        full += chunk
        if not found:
            at = full.upper().find(_MARK)
            found = at != -1
            limit = at if found else len(full) - _partial_mark(full)
            if limit > shown:
                yield full[shown:limit]
                shown = limit
    if not found and shown < len(full):
        yield full[shown:]
    sink.append(full)
