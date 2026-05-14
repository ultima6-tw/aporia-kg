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
def kb_import_url(url: str, source_name: str = "",
                  ttl_days: int | None = None) -> dict:
    """
    Crawl a webpage and add its content to the knowledge base.
    Use this for documentation pages, wikis, or any web resource.

    Args:
        url: URL to crawl and import
        source_name: Human-readable label for this source (defaults to URL)
        ttl_days: Days until content expires (None = category default, 0 = never expires)
    """
    return _client.import_url(url, source_name, ttl_days=ttl_days)


@mcp.tool()
def kb_update_url(url: str, source_name: str = "",
                  ttl_days: int | None = None) -> dict:
    """
    Re-crawl an existing URL source to refresh its content in the knowledge base.
    Deletes all existing notes for this source before re-importing.
    Use this when a page has been updated and you want the latest version.

    Args:
        url: URL to re-crawl
        source_name: Must match the label used when originally imported (defaults to URL)
        ttl_days: Days until content expires (None = category default, 0 = never expires)
    """
    return _client.update_url(url, source_name, ttl_days=ttl_days)


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
def kb_import_text(text: str, source_name: str = "",
                   ttl_days: int | None = None) -> dict:
    """
    Add plain text directly to the knowledge base.
    Use this for pasting in notes, specs, or any text content.

    Args:
        text: The text content to import
        source_name: Human-readable label for this source
        ttl_days: Days until content expires (None/omitted = never expires, matches original behaviour)
    """
    return _client.import_text(text, source_name, ttl_days=ttl_days)


@mcp.tool()
def kb_search(query: str, n: int = 5, group_by_source: bool = False) -> list[dict]:
    """
    Search the knowledge base for relevant notes or concept-level neighbors.

    Args:
        query: Search query (semantic search)
        n: Number of results to return (default 5)
        group_by_source: False (default) → notes with title+summary snippets;
                         True → results grouped by source with best similarity score,
                         useful for discovering which knowledge sources are related to a concept
    """
    return _client.search_kb(query, n, group_by_source=group_by_source)


@mcp.tool()
def kb_verify(concept_a: str, concept_b: str, verifier_id: str = "system") -> dict:
    """
    Verify the connection between two concepts using KB evidence only — no LLM involved.
    Primary use case: ground-truth-free agent evaluation. When an agent claims two
    concepts are related, kb_verify measures that claim against KB evidence without
    asking another LLM to judge — breaking the circular trust problem of LLM-as-judge.

    Agent evaluation workflow: import domain knowledge → run agent → call kb_verify
    on each claim → accumulate reports across verifier_ids to build consensus.

    All measurements are system-computed (embedding similarity, co-mention count,
    weighted source credibility score, KB coverage).

    Each call stores a verification report in the KB. Confidence accumulates across
    independent verifications: the more distinct verifier_ids confirm the connection,
    the higher prior_verifications becomes.

    Returns:
        kb_support_score:    overall support score (0–1), default weighted formula
        details:             raw measurements — use these to apply your own weights
          embedding_similarity:   cosine similarity of the two concept embeddings
          bidirectional:          True if each concept appears in the other's neighborhood
          co_mention_count:       notes mentioning both concepts (verify:// excluded)
          weighted_source_score:  sum of credibility weights of supporting sources
          kb_coverage_a/b:        how well KB covers each concept independently (0–1)
        prior_verifications: number of distinct prior verifier_ids that confirmed this pair
        data_sufficient:     False if KB has too little content about either concept

    Args:
        concept_a:   First concept (free text)
        concept_b:   Second concept (free text)
        verifier_id: Identifier for the caller — used to count independent verifications
    """
    return _client.verify_connection(concept_a, concept_b, verifier_id)


@mcp.tool()
def kb_set_credibility(source: str, credibility: float) -> dict:
    """
    Set the credibility weight for a knowledge source.
    Affects weighted_source_score in future kb_verify calls.

    Use kb_list_sources to find exact source names.

    Args:
        source:      Exact source name (as returned by kb_list_sources)
        credibility: Weight from 0.0 (untrusted) to 1.0 (fully trusted).
                     Defaults: pdf/text=0.9, jsonl=0.8, url=0.7, crawler=0.4
    """
    return _client.set_source_credibility(source, credibility)


@mcp.tool()
def kb_list_sources() -> list[dict]:
    """
    List all knowledge sources currently in the knowledge base.
    Shows source names and note counts — useful for auditing what's been imported.
    """
    return _client.list_kb_sources()


@mcp.tool()
def kb_delete_source(source: str) -> dict:
    """
    Delete all notes belonging to a specific knowledge source.
    Use kb_list_sources first to find the exact source name.

    Args:
        source: Exact source name as returned by kb_list_sources
    """
    return _client.delete_kb_source(source)


@mcp.tool()
def kb_status() -> dict:
    """
    Return knowledge base statistics: total note count, URL count, and recently crawled URLs.
    Use this to get a quick health check of the knowledge base.
    """
    return _client.kb_status_info()


@mcp.tool()
def kb_import_jsonl(content: str, source_name: str = "",
                    ttl_days: int | None = None) -> dict:
    """
    Batch-import structured knowledge as JSONL into the knowledge base.
    Each line must be a JSON object with a "text" field and optional "source" field.
    Example line: {"text": "The API key expires after 90 days.", "source": "security-policy"}

    Args:
        content: JSONL string (one JSON object per line)
        source_name: Fallback source label if individual lines don't specify one
        ttl_days: Days until content expires (None = category default, 0 = never expires)
    """
    return _client.import_jsonl(content, source_name, ttl_days=ttl_days)


@mcp.tool()
def kb_ask(query: str, lang: str = "en") -> dict:
    """
    Ask a question and get a grounded answer from the knowledge base.
    Unlike plain LLM, the answer is based on imported manuals/documents — not guessed.
    Use this for instrument operation, SCPI commands, datasheet specs, or any domain-specific question.

    Args:
        query: Your question (e.g. "How do I set edge trigger holdoff on the MXO4?")
        lang: Answer language — "en", "zh-TW", or "ja"

    Returns:
        answer: Grounded answer with source citations
        sources: List of source documents used
        notes_used: Number of context notes retrieved
    """
    return _client.kb_ask(query, lang=lang)


@mcp.tool()
def kb_audit(concepts: list[str] = [], pairs: list[dict] = [],
             pre_filter_threshold: float = 0.3,
             verifier_id: str = "system") -> dict:
    """
    Audit KB coverage for a set of concepts or concept pairs.

    Two-stage pipeline for agent evaluation and documentation gap detection:
      Stage 1 — Pre-filter: batch embed all concepts and compute pairwise
        cosine similarity. Pairs below pre_filter_threshold are skipped
        (semantically distant pairs are expected to have no co-mention).
      Stage 2 — Full verify: run kb_verify on each passing pair, storing
        reports in ChromaDB for future reference.

    Results are grouped as:
      gaps   — co_mention_count == 0: design intent not reflected in KB.
               Each gap includes fix_hints: which sources to add docs to.
      weak   — co_mention > 0 but kb_support_score < 0.6
      strong — kb_support_score >= 0.6, connection well-supported
      skipped — filtered out by pre_filter_threshold

    Use this to find documentation gaps, verify agent claims in bulk, or
    audit that key design concepts are mutually documented in your KB.

    Args:
        concepts:             List of concepts — all pairs checked automatically
        pairs:                Explicit pairs as [{"a": "...", "b": "..."}, ...]
                              (use instead of concepts for targeted checks)
        pre_filter_threshold: Min embedding similarity to run full verify (default 0.3)
        verifier_id:          Caller identifier for tracking independent verifications
    """
    return _client.kb_audit(
        concepts=concepts or None,
        pairs=pairs or None,
        pre_filter_threshold=pre_filter_threshold,
        verifier_id=verifier_id,
    )


@mcp.tool()
def kb_audit_history(concept_a: str, concept_b: str, limit: int = 20) -> list[dict]:
    """
    Return the audit history for a specific concept pair, newest first.
    Shows whether a gap was present in past runs and when it was resolved.
    Useful for tracking documentation completeness over time.

    Args:
        concept_a: First concept
        concept_b: Second concept
        limit:     Max number of historical entries to return (default 20)
    """
    return _client.kb_audit_history(concept_a, concept_b, limit)


@mcp.tool()
def kb_watch_concepts(concepts: list[str]) -> dict:
    """
    Add concepts to the audit watchlist.
    The watchlist is persistent — use kb_audit_status to run a live audit
    on all watched concepts at any time, without re-specifying the list.

    Args:
        concepts: List of concepts to monitor (e.g. ["kb_verify", "agent evaluation"])
    """
    return _client.kb_watch_concepts(concepts)


@mcp.tool()
def kb_unwatch_concept(concept: str) -> dict:
    """
    Remove a concept from the audit watchlist.

    Args:
        concept: Exact concept name to remove
    """
    return _client.kb_unwatch_concept(concept)


@mcp.tool()
def kb_audit_status(verifier_id: str = "watchlist") -> dict:
    """
    Run kb_audit on the current watchlist and return live gap status.
    Use this at the start of a work session to know what connections are
    still missing from the KB — the system tells you what to do next.

    Returns the same structure as kb_audit: gaps / weak / strong / skipped,
    with fix_hints for each gap pointing to where documentation should be added.

    Args:
        verifier_id: Identifier for this audit run (default "watchlist")
    """
    return _client.kb_audit_status(verifier_id)


@mcp.tool()
def kb_sync_file(file_path: str, source_name: str = "", force: bool = False) -> dict:
    """
    Sync a local file into the KB.
    Compares file modification time against last sync — skips if unchanged.
    On change: deletes old chunks and re-imports the updated content.
    Registers the file for future sync tracking (visible in kb_list_file_watches).

    Use this after editing a source file to keep the KB current without
    manually deleting and re-importing.

    Args:
        file_path:   Absolute path to the file
        source_name: KB source label (defaults to filename)
        force:       Re-import even if file is unchanged (default False)
    """
    return _client.kb_sync_file(file_path, source_name, force)


@mcp.tool()
def kb_list_file_watches() -> list[dict]:
    """
    List all files registered for KB sync tracking.
    Shows file path, source name, last sync time, and whether the file
    has been modified since the last sync.
    """
    return _client.kb_list_file_watches()


@mcp.tool()
def kb_report(format: str = "markdown", verifier_id: str = "report") -> str | dict:
    """
    Generate a KB completeness report combining all system state into one document.

    The report covers:
    - Knowledge sources: all imported content, chunk counts, credibility weights
    - Audit watchlist + live coverage: current gaps / weak / strong with fix_hints
    - Audit history summary: trend across all past runs (total runs, status breakdown)
    - Synced files: registered files and whether they're stale since last sync

    Use this at the start of a session to understand the full state of the KB,
    or share it as a structured handoff document for other agents or humans.

    Args:
        format:      "markdown" (default) — human-readable document like PROJECT.md
                     "json" — structured dict for further processing
        verifier_id: Identifier for the audit run triggered by this report
    """
    return _client.kb_report(format=format, verifier_id=verifier_id)


if __name__ == "__main__":
    mcp.run()
