"""
Aporia KG Python client — shared layer used by CLI and MCP server.
Talks to the FastAPI server running at BASE_URL.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Generator

import httpx

BASE_URL = os.environ.get("APORIA_URL", "http://localhost:7860")


# ── Data models ──────────────────────────────────────────────────────────────

@dataclass
class Node:
    id: str
    name: str
    status: str          # todo / done / skip / unknown / deferred
    source: str          # user / ai_suggested / ai_planned
    description: str = ""
    exclusive: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "Node":
        # Support both raw session format and _node_vis (frontend) format
        return cls(
            id=d["id"],
            name=d.get("name") or d.get("label", ""),
            status=d.get("status") or d.get("_status", "unknown"),
            source=d.get("source") or d.get("_source", ""),
            description=d.get("description") or d.get("_description", ""),
            exclusive=d.get("exclusive") or d.get("_exclusive", False),
        )


@dataclass
class PlanResult:
    session_id: str
    goal: str
    reply: str
    nodes: list[Node] = field(default_factory=list)


@dataclass
class MessageResult:
    reply: str
    new_nodes: list[Node] = field(default_factory=list)
    ready: bool = False   # True when all nodes are filled


# ── SSE helper ───────────────────────────────────────────────────────────────

def _iter_sse(response: httpx.Response) -> Generator[dict, None, None]:
    """Yield parsed SSE data dicts from a streaming response."""
    for line in response.iter_lines():
        if line.startswith("data: "):
            raw = line[6:].strip()
            if raw and raw != "[DONE]":
                try:
                    yield json.loads(raw)
                except json.JSONDecodeError:
                    pass


# ── Client class ─────────────────────────────────────────────────────────────

class AporiaClient:
    def __init__(self, base_url: str = BASE_URL, timeout: float = 120.0):
        self.base = base_url.rstrip("/")
        self.timeout = timeout

    # ── Session management ───────────────────────────────────────────────────

    def plan_goal(self, goal: str, lang: str = "en", user_id: str = "cli-agent") -> PlanResult:
        """Start a new session and return the initial knowledge graph."""
        reply_parts: list[str] = []
        nodes: list[Node] = []
        session_id = ""

        with httpx.stream(
            "POST", f"{self.base}/api/start",
            json={"goal": goal, "lang": lang, "user_id": user_id},
            timeout=self.timeout,
        ) as r:
            r.raise_for_status()
            for ev in _iter_sse(r):
                t = ev.get("type", "")
                if t == "graph_init":
                    session_id = ev.get("session_id", "")
                elif t == "reply":
                    reply_parts.append(ev.get("text", ""))
                elif t == "node_add":
                    nodes.append(Node.from_dict(ev["node"]))

        return PlanResult(
            session_id=session_id,
            goal=goal,
            reply="".join(reply_parts),
            nodes=nodes,
        )

    def send_message(self, session_id: str, message: str, lang: str = "en",
                     user_id: str = "cli-agent") -> MessageResult:
        """Continue the conversation and return new nodes + AI reply."""
        reply_parts: list[str] = []
        new_nodes: list[Node] = []
        ready = False

        with httpx.stream(
            "POST", f"{self.base}/api/message",
            json={"session_id": session_id, "message": message,
                  "lang": lang, "user_id": user_id},
            timeout=self.timeout,
        ) as r:
            r.raise_for_status()
            for ev in _iter_sse(r):
                t = ev.get("type", "")
                if t == "reply":
                    reply_parts.append(ev.get("text", ""))
                    ready = ev.get("ready", False)
                elif t == "node_add":
                    new_nodes.append(Node.from_dict(ev["node"]))

        return MessageResult(
            reply="".join(reply_parts),
            new_nodes=new_nodes,
            ready=ready,
        )

    def get_nodes(self, session_id: str) -> list[Node]:
        """Return all nodes in the session (current state)."""
        r = httpx.post(
            f"{self.base}/api/session_data",
            json={"session_id": session_id},
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        raw = data.get("nodes", [])
        if isinstance(raw, dict):
            raw = raw.values()
        return [Node.from_dict(n) for n in raw]

    def list_sessions(self) -> list[dict]:
        """Return summary list of all sessions."""
        r = httpx.get(f"{self.base}/api/sessions", timeout=self.timeout)
        r.raise_for_status()
        return r.json().get("sessions", [])

    # ── Node operations ──────────────────────────────────────────────────────

    def mark_done(self, session_id: str, node_id: str) -> Node:
        """Mark a node as done."""
        return self._set_status(session_id, node_id, "done")

    def mark_skip(self, session_id: str, node_id: str) -> Node:
        """Skip a node."""
        return self._set_status(session_id, node_id, "skip")

    def mark_todo(self, session_id: str, node_id: str) -> Node:
        """Mark a node as todo (reopen)."""
        return self._set_status(session_id, node_id, "todo")

    def _set_status(self, session_id: str, node_id: str, status: str) -> Node:
        r = httpx.post(
            f"{self.base}/api/node_status",
            json={"session_id": session_id, "node_id": node_id, "status": status},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return Node.from_dict(r.json()["node"])

    def add_node(self, session_id: str, name: str, description: str = "") -> Node:
        """Manually add a node to the graph."""
        r = httpx.post(
            f"{self.base}/api/add_node",
            json={"session_id": session_id, "name": name, "description": description},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return Node.from_dict(r.json()["node"])

    # ── Export ───────────────────────────────────────────────────────────────

    def export_markdown(self, session_id: str) -> str:
        """Export the current graph as a Markdown checklist."""
        r = httpx.post(
            f"{self.base}/api/export_markdown",
            json={"session_id": session_id},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json().get("markdown", "")

    # ── Convenience ─────────────────────────────────────────────────────────

    def get_todo_nodes(self, session_id: str) -> list[Node]:
        """Return only nodes that still need to be done."""
        return [n for n in self.get_nodes(session_id)
                if n.status in ("todo", "unknown")]

    def get_done_nodes(self, session_id: str) -> list[Node]:
        return [n for n in self.get_nodes(session_id) if n.status == "done"]

    def summary(self, session_id: str) -> dict:
        """Quick stats: done / todo / skip counts."""
        nodes = self.get_nodes(session_id)
        counts = {"done": 0, "todo": 0, "unknown": 0, "skip": 0, "deferred": 0}
        for n in nodes:
            counts[n.status] = counts.get(n.status, 0) + 1
        return counts

    # ── Knowledge base ───────────────────────────────────────────────────────

    def import_url(self, url: str, source_name: str = "") -> dict:
        """Crawl a URL and add its content to the knowledge base."""
        r = httpx.post(
            f"{self.base}/api/knowledge/url",
            json={"url": url, "source": source_name or url},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def import_text(self, text: str, source_name: str = "") -> dict:
        """Add plain text directly to the knowledge base."""
        r = httpx.post(
            f"{self.base}/api/knowledge/text",
            json={"text": text, "source": source_name},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def import_pdf_from_url(self, pdf_url: str, source_name: str = "") -> dict:
        """Download a PDF from a URL and add it to the knowledge base."""
        import tempfile, pathlib
        resp = httpx.get(pdf_url, timeout=self.timeout, follow_redirects=True)
        resp.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(resp.content)
            tmp_path = f.name
        try:
            with open(tmp_path, "rb") as f:
                r = httpx.post(
                    f"{self.base}/api/knowledge/pdf",
                    files={"file": (pathlib.Path(tmp_path).name, f, "application/pdf")},
                    data={"source_name": source_name or pdf_url, "category": "concept"},
                    timeout=self.timeout,
                )
            r.raise_for_status()
            return r.json()
        finally:
            pathlib.Path(tmp_path).unlink(missing_ok=True)

    def search_kb(self, query: str, n: int = 5) -> list[dict]:
        """Search the knowledge base and return relevant chunks."""
        r = httpx.get(
            f"{self.base}/api/knowledge/search",
            params={"q": query, "n": n},
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("results", data.get("chunks", []))
