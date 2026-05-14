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

    def import_url(self, url: str, source_name: str = "",
                   ttl_days: int | None = None) -> dict:
        """Crawl a URL and add its content to the knowledge base."""
        r = httpx.post(
            f"{self.base}/api/knowledge/url",
            json={"url": url, "source": source_name or url, "ttl_days": ttl_days},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def import_text(self, text: str, source_name: str = "",
                    ttl_days: int | None = None) -> dict:
        """Add plain text directly to the knowledge base."""
        r = httpx.post(
            f"{self.base}/api/knowledge/text",
            json={"text": text, "source": source_name, "ttl_days": ttl_days},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def update_url(self, url: str, source_name: str = "",
                   ttl_days: int | None = None) -> dict:
        """Delete existing chunks for a URL and re-crawl with a new TTL."""
        r = httpx.post(
            f"{self.base}/api/knowledge/update_url",
            json={"url": url, "source": source_name, "ttl_days": ttl_days},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def import_pdf_from_url(self, pdf_url: str, source_name: str = "") -> dict:
        """Download a PDF and import it as notes using TOC-based extraction."""
        import tempfile, pathlib

        resp = httpx.get(pdf_url, timeout=self.timeout, follow_redirects=True)
        resp.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(resp.content)
            tmp_path = f.name
        try:
            label = source_name or pdf_url
            filename = pathlib.Path(pdf_url.split("?")[0]).name or "document.pdf"
            with open(tmp_path, "rb") as pdf_file:
                r = httpx.post(
                    f"{self.base}/api/knowledge/pdf",
                    data={"source_name": label},
                    files={"file": (filename, pdf_file, "application/pdf")},
                    timeout=self.timeout,
                )
            r.raise_for_status()
            return r.json()
        finally:
            pathlib.Path(tmp_path).unlink(missing_ok=True)

    def search_kb(self, query: str, n: int = 5,
                  group_by_source: bool = False) -> list[dict]:
        """Search the knowledge base; set group_by_source=True for concept-neighbor view."""
        r = httpx.get(
            f"{self.base}/api/knowledge/search",
            params={"q": query, "n": n, "group_by_source": group_by_source},
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        if group_by_source:
            return data.get("neighbors", [])
        return data.get("results", data.get("chunks", []))

    def kb_ask(self, query: str, n: int = 8, lang: str = "en") -> dict:
        """Ask a question grounded in KB content; returns answer + sources."""
        r = httpx.post(
            f"{self.base}/api/knowledge/ask",
            json={"query": query, "n": n, "lang": lang},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def verify_connection(self, concept_a: str, concept_b: str,
                          verifier_id: str = "system") -> dict:
        """Verify KB-based connection between two concepts (no LLM)."""
        r = httpx.post(
            f"{self.base}/api/knowledge/verify",
            json={"concept_a": concept_a, "concept_b": concept_b,
                  "verifier_id": verifier_id},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def set_source_credibility(self, source: str, credibility: float) -> dict:
        """Set the credibility weight (0.0–1.0) for a knowledge source."""
        r = httpx.post(
            f"{self.base}/api/knowledge/set_source_credibility",
            json={"source": source, "credibility": credibility},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def list_kb_sources(self) -> list[dict]:
        """List all imported knowledge sources."""
        r = httpx.get(f"{self.base}/api/knowledge/sources", timeout=self.timeout)
        r.raise_for_status()
        return r.json().get("sources", [])

    def delete_kb_source(self, source: str) -> dict:
        """Delete all chunks for the specified source."""
        r = httpx.post(
            f"{self.base}/api/knowledge/delete_source",
            json={"source": source},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def kb_status_info(self) -> dict:
        """Return KB statistics: chunk count, URL count, recent URLs."""
        r = httpx.get(f"{self.base}/api/knowledge/status", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def import_jsonl(self, content: str, source_name: str = "",
                     ttl_days: int | None = None) -> dict:
        """Import JSONL lines (each: {"text":"...","source":"..."}) into the KB."""
        r = httpx.post(
            f"{self.base}/api/knowledge/jsonl",
            json={"content": content, "source": source_name, "ttl_days": ttl_days},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def kb_audit(self,
                 concepts: list[str] | None = None,
                 pairs: list[dict] | None = None,
                 pre_filter_threshold: float = 0.3,
                 verifier_id: str = "system") -> dict:
        """
        Audit KB coverage for concept pairs using two-stage pipeline:
        batch embed pre-filter → full verify for passing pairs.
        Returns gaps / weak / strong / skipped.
        """
        r = httpx.post(
            f"{self.base}/api/knowledge/audit",
            json={
                "concepts":             concepts or [],
                "pairs":                pairs or [],
                "pre_filter_threshold": pre_filter_threshold,
                "verifier_id":          verifier_id,
            },
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def kb_audit_history(self, concept_a: str, concept_b: str, limit: int = 20) -> list[dict]:
        """Return audit history for a concept pair (newest first)."""
        r = httpx.get(
            f"{self.base}/api/knowledge/audit/history",
            params={"concept_a": concept_a, "concept_b": concept_b, "limit": limit},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json().get("history", [])

    def kb_audit_summary(self) -> dict:
        """Return aggregate stats across all audit runs."""
        r = httpx.get(f"{self.base}/api/knowledge/audit/summary", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def kb_watch_concepts(self, concepts: list[str]) -> dict:
        """Add concepts to the audit watchlist."""
        r = httpx.post(
            f"{self.base}/api/knowledge/audit/watchlist",
            json={"concepts": concepts},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def kb_unwatch_concept(self, concept: str) -> dict:
        """Remove a concept from the audit watchlist."""
        r = httpx.delete(
            f"{self.base}/api/knowledge/audit/watchlist/{concept}",
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def kb_audit_status(self, verifier_id: str = "watchlist") -> dict:
        """Run kb_audit on the current watchlist and return live gap status."""
        r = httpx.get(
            f"{self.base}/api/knowledge/audit/status",
            params={"verifier_id": verifier_id},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def kb_sync_file(self, file_path: str, source_name: str = "", force: bool = False) -> dict:
        """Sync a local file into the KB (skips if unchanged unless force=True)."""
        r = httpx.post(
            f"{self.base}/api/knowledge/sync_file",
            json={"file_path": file_path, "source_name": source_name, "force": force},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()

    def kb_list_file_watches(self) -> list[dict]:
        """List all registered files and their sync state."""
        r = httpx.get(f"{self.base}/api/knowledge/file_watches", timeout=self.timeout)
        r.raise_for_status()
        return r.json().get("files", [])

    def kb_report(self, format: str = "markdown", verifier_id: str = "report") -> str | dict:
        """Generate a KB completeness report."""
        r = httpx.get(
            f"{self.base}/api/knowledge/report",
            params={"format": format, "verifier_id": verifier_id},
            timeout=self.timeout,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("report", data)
