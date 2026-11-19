"""
Settings, overridable through environment variables or a .env file in the project root.

The chat model runs in Ollama, so other local apps can share it; images come
from mflux running FLUX.2 [klein] 4B at 4-bit.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_env_file(path: Path) -> None:
    """KEY=VALUE lines from .env; the real environment wins."""
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_env_file(ROOT / ".env")

# ── Who Athena talks to (optional) ─────────────────────────────────────────
USER_NAME = os.environ.get("ATHENA_USER_NAME", "").strip()
USER_PLACE = os.environ.get("ATHENA_USER_PLACE", "").strip()

DATA_DIR = Path(os.environ.get("ATHENA_DATA_DIR", ROOT / "data"))
IMAGES_DIR = DATA_DIR / "images"
MEMORY_FILE = DATA_DIR / "memory.json"

# ── Chat model (Ollama) ────────────────────────────────────────────────────
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
LLM_MODEL = os.environ.get("ATHENA_MODEL", "dsv4-heretic")
KEEP_ALIVE = "10m"
# Warmer than the model's defaults (0.6) for conversation; the rest matches its Modelfile.
CHAT_OPTIONS = {"temperature": 0.75, "top_p": 0.95, "top_k": 20, "repeat_penalty": 1.08, "num_ctx": 16384}
HISTORY_CHARS = 24_000          # recent conversation sent with each turn (~6k tokens)

# ── Image model (mflux) ────────────────────────────────────────────────────
IMAGE_MODEL = os.environ.get("ATHENA_IMAGE_MODEL", "Runpod/FLUX.2-klein-4B-mflux-4bit")
IMAGE_BASE_MODEL = "flux2-klein-4b"
MFLUX_BIN = Path(sys.executable).parent / "mflux-generate-flux2"
RENDER_TIMEOUT = 900.0
