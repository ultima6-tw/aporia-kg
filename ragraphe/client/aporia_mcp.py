"""
Aporia KG MCP Server
Exposes Aporia KG as tools for AI agents (Claude Code, etc.)

Run:
  python -m ragraphe.client.aporia_mcp

Then add to Claude Code settings:
  {
    "mcpServers": {
      "aporia-kg": {
        "command": "/path/to/.venv/bin/python",
        "args": ["-m", "ragraphe.client.aporia_mcp"],
        "cwd": "/path/to/Aporia KG"
      }
    }
  }
"""
from __future__ import annotations

from fastmcp import FastMCP
from ragraphe.client.aporia_client import AporiaClient

mcp = FastMCP(
    name="aporia-kg",
    instructions=(
        "Aporia KG decomposes goals into atomic task nodes and tracks progress. "
        "Use plan_goal to start, get_todo_nodes to see what's left, "
        "mark_done when a task is complete, and send_message to refine the plan."
    ),
)
_client = AporiaClient()


# ── Tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def plan_goal(goal: str, lang: str = "en") -> dict:
    """
    Decompose a goal into an atomic task graph.
    Returns session_id, AI reply, and list of nodes.
    Call this first to start planning.

    Args:
        goal: The goal to decompose (e.g. "write a machine learning paper")
        lang: Response language — "en", "zh-TW", or "ja"
    """
    result = _client.plan_goal(goal, lang=lang)
    return {
        "session_id": result.session_id,
        "reply": result.reply,
        "nodes": [
            {"id": n.id, "name": n.name, "status": n.status,
             "source": n.source, "description": n.description}
            for n in result.nodes
        ],
    }


@mcp.tool()
def get_nodes(session_id: str, status_filter: str = "") -> dict:
    """
    Get all nodes in the session with their current status.
    Useful for checking what tasks remain or have been completed.

    Args:
        session_id: Session ID from plan_goal
        status_filter: Optional filter — "todo", "done", "skip", "unknown", "deferred"
    """
    nodes = _client.get_nodes(session_id)
    if status_filter:
        nodes = [n for n in nodes if n.status == status_filter]
    stats = _client.summary(session_id)
    return {
        "nodes": [
            {"id": n.id, "name": n.name, "status": n.status,
             "source": n.source, "description": n.description}
            for n in nodes
        ],
        "summary": stats,
    }


@mcp.tool()
def get_todo_nodes(session_id: str) -> dict:
    """
    Get only the nodes that still need to be done (todo + unknown).
    Use this to decide what to work on next and stay focused.

    Args:
        session_id: Session ID from plan_goal
    """
    nodes = _client.get_todo_nodes(session_id)
    return {
        "remaining": len(nodes),
        "nodes": [
            {"id": n.id, "name": n.name, "status": n.status, "description": n.description}
            for n in nodes
        ],
    }


@mcp.tool()
def mark_done(session_id: str, node_id: str) -> dict:
    """
    Mark a task node as completed.
    Call this after finishing work on a specific task.

    Args:
        session_id: Session ID
        node_id: Node ID (full or first 8 characters)
    """
    # Support short IDs
    all_nodes = _client.get_nodes(session_id)
    matched = [n for n in all_nodes if n.id.startswith(node_id)]
    if not matched:
        return {"error": f"No node found matching '{node_id}'"}
    node = _client.mark_done(session_id, matched[0].id)
    remaining = len(_client.get_todo_nodes(session_id))
    return {
        "done": True,
        "node": {"id": node.id, "name": node.name, "status": node.status},
        "remaining_tasks": remaining,
    }


@mcp.tool()
def mark_skip(session_id: str, node_id: str) -> dict:
    """
    Skip a task node (mark as not needed).

    Args:
        session_id: Session ID
        node_id: Node ID (full or first 8 characters)
    """
    all_nodes = _client.get_nodes(session_id)
    matched = [n for n in all_nodes if n.id.startswith(node_id)]
    if not matched:
        return {"error": f"No node found matching '{node_id}'"}
    node = _client.mark_skip(session_id, matched[0].id)
    return {"skipped": True, "node": {"id": node.id, "name": node.name}}


@mcp.tool()
def add_node(session_id: str, name: str, description: str = "") -> dict:
    """
    Manually add a task node to the graph.
    Use this when you identify a subtask the AI didn't suggest.

    Args:
        session_id: Session ID
        name: Short task name (2–12 words)
        description: Optional description of what this task involves
    """
    node = _client.add_node(session_id, name, description)
    return {"node": {"id": node.id, "name": node.name, "status": node.status}}


@mcp.tool()
def send_message(session_id: str, message: str, lang: str = "en") -> dict:
    """
    Continue the planning conversation to refine or expand the graph.
    Use this to add context, ask for sub-task breakdown, or adjust scope.

    Args:
        session_id: Session ID
        message: Your message (e.g. "focus on NLP transformer models")
        lang: Response language — "en", "zh-TW", or "ja"
    """
    result = _client.send_message(session_id, message, lang=lang)
    return {
        "reply": result.reply,
        "new_nodes": [
            {"id": n.id, "name": n.name, "status": n.status, "description": n.description}
            for n in result.new_nodes
        ],
        "planning_complete": result.ready,
    }


@mcp.tool()
def export_markdown(session_id: str) -> str:
    """
    Export the task graph as a Markdown checklist.
    Returns done/todo/skip sections suitable for Notion, Obsidian, etc.

    Args:
        session_id: Session ID
    """
    return _client.export_markdown(session_id)


@mcp.tool()
def list_sessions() -> list[dict]:
    """
    List all existing planning sessions with their goals and node counts.
    Use this to find a session_id for a previous planning run.
    """
    return _client.list_sessions()


# ── Knowledge Base tools ──────────────────────────────────────────────────────

@mcp.tool()
def kb_import_url(url: str, source_name: str = "") -> dict:
    """
    Crawl a webpage and add its content to the knowledge base.
    Use this for documentation pages, wikis, or any web resource.

    Args:
        url: URL to crawl and import
        source_name: Human-readable label for this source (defaults to URL)
    """
    return _client.import_url(url, source_name)


@mcp.tool()
def kb_import_pdf(pdf_url: str, source_name: str = "") -> dict:
    """
    Download a PDF from a URL and add it to the knowledge base.
    Ideal for instrument manuals, datasheets, research papers, etc.

    Args:
        pdf_url: Direct URL to the PDF file
        source_name: Human-readable label (e.g. "Keysight 33500B User Guide")
    """
    return _client.import_pdf_from_url(pdf_url, source_name)


@mcp.tool()
def kb_import_text(text: str, source_name: str = "") -> dict:
    """
    Add plain text directly to the knowledge base.
    Use this for pasting in notes, specs, or any text content.

    Args:
        text: The text content to import
        source_name: Human-readable label for this source
    """
    return _client.import_text(text, source_name)


@mcp.tool()
def kb_search(query: str, n: int = 5) -> list[dict]:
    """
    Search the knowledge base for relevant chunks.
    Use this to verify imported content or look up specific information.

    Args:
        query: Search query (semantic search)
        n: Number of results to return (default 5)
    """
    return _client.search_kb(query, n)


if __name__ == "__main__":
    mcp.run()
