"""Ollama client: streaming chat, one-shot completions, and unloading before a render."""

import json
import re
import time
from typing import Any, Dict, Iterator, List, Optional, Tuple

import httpx

from athena import config

# Control tokens a DeepSeek distill can print if a stop token is missed.
_CONTROL = re.compile(r"<\|im_start\|>\w*|<\|[^|<>]{1,40}\|>|<｜[^｜<>]{1,40}｜>|</?think>")


class LLMError(Exception):
    pass


def _client(timeout: float = 600.0) -> httpx.Client:
    # trust_env=False: a system proxy must not intercept calls to localhost.
    return httpx.Client(base_url=config.OLLAMA_URL, trust_env=False,
                        timeout=httpx.Timeout(timeout, connect=5.0))


def _tagged(model: str) -> str:
    """Ollama lists custom models as name:latest."""
    return model if ":" in model else f"{model}:latest"


def clean(text: str) -> str:
    return _CONTROL.sub("", text or "").strip()


def stream_chat(messages: List[Dict[str, str]], *, think: bool = False,
                options: Optional[Dict[str, Any]] = None) -> Iterator[Tuple[str, str]]:
    """Yield ("thinking" | "content", text) chunks as the reply arrives."""
    payload = {
        "model": config.LLM_MODEL, "messages": messages, "stream": True, "think": think,
        "keep_alive": config.KEEP_ALIVE, "options": {**config.CHAT_OPTIONS, **(options or {})},
    }
    try:
        with _client() as client, client.stream("POST", "/api/chat", json=payload) as resp:
            if resp.status_code == 404:
                raise LLMError(f"model {config.LLM_MODEL} isn't installed: run ./launch.sh")
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                data = json.loads(line)
                if data.get("error"):
                    raise LLMError(data["error"])
                msg = data.get("message") or {}
                if msg.get("thinking"):
                    yield "thinking", msg["thinking"]
                if msg.get("content"):
                    yield "content", msg["content"]
    except httpx.HTTPError as exc:
        raise LLMError(f"Ollama unreachable: {type(exc).__name__}: {exc}") from exc


def complete(system: str, user: str, *, temperature: float = 0.7, max_tokens: int = 300) -> str:
    """One non-streaming reply, thinking off."""
    payload = {
        "model": config.LLM_MODEL, "stream": False, "think": False, "keep_alive": config.KEEP_ALIVE,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "options": {**config.CHAT_OPTIONS, "temperature": temperature, "num_predict": max_tokens},
    }
    try:
        with _client() as client:
            resp = client.post("/api/chat", json=payload)
            resp.raise_for_status()
            return clean(resp.json().get("message", {}).get("content", ""))
    except httpx.HTTPError as exc:
        raise LLMError(f"Ollama call failed: {type(exc).__name__}: {exc}") from exc


def loaded_models() -> List[str]:
    with _client(5) as client:
        return [m["name"] for m in client.get("/api/ps").json().get("models", [])]


def unload(wait: float = 15.0) -> None:
    """Free the chat model's memory so the image model has room (16 GB machine)."""
    try:
        with _client(30) as client:
            client.post("/api/generate", json={"model": config.LLM_MODEL, "keep_alive": 0})
        # The request returns before the memory is actually released.
        deadline = time.time() + wait
        while time.time() < deadline and _tagged(config.LLM_MODEL) in loaded_models():
            time.sleep(0.5)
    except httpx.HTTPError:
        pass                                # Ollama down means nothing is loaded either


def status() -> Dict[str, Any]:
    try:
        with _client(3) as client:
            installed = {m["name"] for m in client.get("/api/tags").json().get("models", [])}
        loaded = loaded_models()
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"Ollama isn't running ({type(exc).__name__})"}
    name = _tagged(config.LLM_MODEL)
    return {"ok": name in installed, "installed": name in installed, "loaded": name in loaded,
            "error": "" if name in installed else f"{config.LLM_MODEL} isn't installed: run ./launch.sh"}
