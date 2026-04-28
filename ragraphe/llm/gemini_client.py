"""
Gemini Flash LLM client (replacement for ollama_client).
The chat() / embed() interface is identical to ollama_client, so main.py can switch transparently.

Retry strategy:
  503 UNAVAILABLE (service temporarily unavailable due to high traffic) → retry up to 4 times with exponential backoff (2/4/8/16 seconds)
  Other errors → raise immediately
"""
import os
import time
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import ServerError

# Load .env from project root (search upward from this file)
load_dotenv(Path(__file__).parent.parent.parent / ".env")

CHAT_MODEL  = "gemini-2.5-flash"
EMBED_MODEL = "gemini-embedding-2"

_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

_MAX_RETRIES  = 4
_RETRY_DELAYS = [2, 4, 8, 16]   # seconds, exponential backoff


def _with_retry(fn):
    """Retry fn() up to _MAX_RETRIES times, only on 503 UNAVAILABLE."""
    last_exc = None
    for attempt, delay in enumerate([0] + _RETRY_DELAYS, start=1):
        if delay:
            print(f"[Gemini] 503 重試 {attempt}/{_MAX_RETRIES}，等待 {delay}s…")
            time.sleep(delay)
        try:
            return fn()
        except ServerError as e:
            if e.code == 503:
                last_exc = e
                continue
            raise   # re-raise any other server error immediately
    raise last_exc


def chat(messages: list[dict], system: str = "") -> str:
    """
    messages: [{"role": "user"/"assistant", "content": "..."}]
    Returns plain text string.
    """
    contents = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append(types.Content(
            role=role,
            parts=[types.Part(text=m["content"])]
        ))

    config = types.GenerateContentConfig(
        system_instruction=system if system else None,
        temperature=0.7,
    )

    def _call():
        resp = _client.models.generate_content(
            model=CHAT_MODEL,
            contents=contents,
            config=config,
        )
        return resp.text or ""

    return _with_retry(_call)


FILTER_MODEL = "gemini-2.5-flash-lite"   # Lighter model for satellite filtering (less overloaded than 2.5)

def chat_quick(messages: list[dict], system: str = "") -> str:
    """Like chat() but with NO retry — fails immediately on 503.
    Uses a lighter model (FILTER_MODEL) to avoid competing with main LLM calls.
    Use for best-effort calls (e.g. satellite filter) where a fast fallback is preferred over waiting."""
    contents = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append(types.Content(
            role=role,
            parts=[types.Part(text=m["content"])]
        ))
    config = types.GenerateContentConfig(
        system_instruction=system if system else None,
        temperature=0.3,  # Lower temp for structured JSON output
    )
    resp = _client.models.generate_content(
        model=FILTER_MODEL,
        contents=contents,
        config=config,
    )
    return resp.text or ""


def embed(text: str) -> list[float]:
    """Returns an embedding vector for a single text."""
    resp = _client.models.embed_content(
        model=EMBED_MODEL,
        contents=text,
    )
    return resp.embeddings[0].values


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Batch embed multiple texts in a single API call. Much faster than calling embed() in a loop."""
    if not texts:
        return []
    def _call():
        resp = _client.models.embed_content(model=EMBED_MODEL, contents=texts)
        return [e.values for e in resp.embeddings]
    return _with_retry(_call)
