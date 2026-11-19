"""
Local image generation with mflux (FLUX.2 [klein] 4B, 4-bit) on Apple Silicon.

Each render runs in its own process so all of its memory goes back to the
system when it finishes. Unload the chat model first (llm.unload): the two
don't fit in 16 GB at the same time.
"""

import fcntl
import json
import random
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from athena import config

# Machine-wide: other tools that render with mflux can take the same lock, so two renders never overlap.
LOCK_FILE = Path.home() / ".cache" / "local-image-mcp.lock"

# Sizes are multiples of 16 and about one megapixel, except the panorama.
ASPECTS = {
    "Landscape 3:2": (1216, 816),
    "Square 1:1": (1024, 1024),
    "Portrait 2:3": (816, 1216),
    "Wide 16:9": (1344, 768),
    "Tall 9:16": (768, 1344),
    "Panoramic 5:2": (1600, 640),
}


class RenderError(Exception):
    pass


@contextmanager
def render_lock(timeout: float = 900.0) -> Iterator[None]:
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK_FILE, "w") as f:
        deadline = time.time() + timeout
        while True:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.time() > deadline:
                    raise RenderError("another image is still rendering; try again shortly")
                time.sleep(1)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def build_command(prompt: str, width: int, height: int, steps: int, seed: int, output: Path) -> List[str]:
    return [
        str(config.MFLUX_BIN),
        "--model", config.IMAGE_MODEL, "--base-model", config.IMAGE_BASE_MODEL,
        "--prompt", prompt,
        "--width", str(width), "--height", str(height),
        "--steps", str(steps), "--seed", str(seed),
        "--output", str(output),
    ]


def render(prompt: str, *, aspect: str, steps: int = 4, seed: Optional[int] = None, **meta: Any) -> Dict[str, Any]:
    """Render one image; returns its record, also saved as a JSON file next to the PNG."""
    width, height = ASPECTS[aspect]
    seed = random.randint(0, 2**31 - 1) if seed is None else int(seed)
    config.IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    image_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{seed}"
    path = config.IMAGES_DIR / f"{image_id}.png"

    started = time.time()
    try:
        with render_lock():
            proc = subprocess.run(build_command(prompt, width, height, steps, seed, path),
                                  capture_output=True, text=True, timeout=config.RENDER_TIMEOUT)
    except FileNotFoundError as exc:
        raise RenderError("mflux isn't installed: run ./launch.sh") from exc
    except subprocess.TimeoutExpired as exc:
        raise RenderError(f"render took longer than {config.RENDER_TIMEOUT:.0f}s") from exc
    if proc.returncode != 0 or not path.exists():
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-4:]
        raise RenderError("render failed: " + " | ".join(tail))

    record = {
        "id": image_id, "path": str(path), "prompt": prompt,
        "aspect": aspect, "width": width, "height": height, "steps": steps, "seed": seed,
        "model": config.IMAGE_MODEL, "seconds": round(time.time() - started, 1),
        "created": time.strftime("%Y-%m-%d %H:%M:%S"), **meta,
    }
    path.with_suffix(".json").write_text(json.dumps(record, indent=2))
    return record


def gallery(limit: int = 60) -> List[Dict[str, Any]]:
    """Saved renders, newest first (file names start with a timestamp)."""
    records = []
    for sidecar in sorted(config.IMAGES_DIR.glob("*.json"), reverse=True)[:limit]:
        try:
            record = json.loads(sidecar.read_text())
        except ValueError:
            continue
        if Path(record.get("path", "")).exists():
            records.append(record)
    return records
