import requests
import json
from typing import Iterator


OLLAMA_BASE = "http://localhost:11434"
CHAT_MODEL = "gemma4:e4b"
EMBED_MODEL = "nomic-embed-text"


def embed(text: str) -> list[float]:
    resp = requests.post(f"{OLLAMA_BASE}/api/embeddings", json={
        "model": EMBED_MODEL,
        "prompt": text,
    })
    resp.raise_for_status()
    return resp.json()["embedding"]


def chat(messages: list[dict], system: str = "") -> str:
    payload = {
        "model": CHAT_MODEL,
        "messages": messages,
        "stream": False,
        "think": False,
    }
    if system:
        payload["system"] = system
    resp = requests.post(f"{OLLAMA_BASE}/api/chat", json=payload)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


def chat_stream(messages: list[dict], system: str = "") -> Iterator[str]:
    """Streaming version: yields one token at a time so the caller can display progress in real time."""
    payload = {
        "model": CHAT_MODEL,
        "messages": messages,
        "stream": True,
        "think": False,
    }
    if system:
        payload["system"] = system
    with requests.post(f"{OLLAMA_BASE}/api/chat", json=payload, stream=True) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            chunk = json.loads(line)
            token = chunk.get("message", {}).get("content", "")
            if token:
                yield token
            if chunk.get("done"):
                break
