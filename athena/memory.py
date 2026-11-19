"""Conversation memory: one JSON file, rewritten atomically after every message."""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from athena import config


def load(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    path = path or config.MEMORY_FILE
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def save(messages: List[Dict[str, Any]], path: Optional[Path] = None) -> None:
    path = path or config.MEMORY_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(messages, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def for_model(messages: List[Dict[str, Any]], max_chars: int) -> List[Dict[str, str]]:
    """The most recent turns that fit in max_chars, as plain chat messages.

    Paintings are noted in the text so Athena remembers what she showed.
    """
    out: List[Dict[str, str]] = []
    total = 0
    for msg in reversed(messages):
        if msg.get("role") not in ("user", "assistant"):
            continue
        content = msg.get("content", "")
        for image in msg.get("images", []):
            content += f"\n[You painted: {image['prompt']}]"
        content = content.strip()
        if not content:
            continue
        if out and total + len(content) > max_chars:
            break
        out.append({"role": msg["role"], "content": content})
        total += len(content)
    out.reverse()
    return out
