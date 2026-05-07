# AGENT.md — Aporia KG Interface Guide for AI Agents

This document tells AI agents how to use Aporia KG via MCP.
It is written for agents, not humans — dense, precise, no prose padding.

---

## What Aporia KG Is

Aporia KG is an external memory and verification system for AI agents.
It stores knowledge as embedded chunks in ChromaDB, tracks what concepts
are documented and how well they connect, and tells you what work is missing.

Two primary uses:
1. **Goal decomposition + task tracking** — break a goal into a node graph,
   mark tasks done, stay focused on what remains.
2. **Knowledge hub + verification** — import documents, search semantically,
   verify that design concepts are mutually documented, audit for gaps.

---

## Setup

### Register MCP server

```bash
claude mcp add aporia-kg -s user \
  -- /path/to/aporia-kg/.venv/bin/python -m ragraphe.client.aporia_mcp
```

Or add to MCP config:

```json
{
  "mcpServers": {
    "aporia-kg": {
      "command": "/path/to/aporia-kg/.venv/bin/python",
      "args": ["-m", "ragraphe.client.aporia_mcp"],
      "cwd": "/path/to/aporia-kg"
    }
  }
}
```

The Aporia KG server must be running:

```bash
uvicorn ragraphe.api.main:app --port 7860
```

### CLI (alternative to MCP)

If MCP is not available, use the CLI directly:

```bash
python -m ragraphe.client.aporia_cli kb sync <file_path> [--source <name>] [--force]
python -m ragraphe.client.aporia_cli kb sources
python -m ragraphe.client.aporia_cli kb watch <concept1> <concept2> ...
python -m ragraphe.client.aporia_cli kb unwatch <concept>
python -m ragraphe.client.aporia_cli kb audit
python -m ragraphe.client.aporia_cli kb search <query> [--limit N]
python -m ragraphe.client.aporia_cli kb ask <question>
```

### Session startup sequence

```
1. kb_status()                    → check KB has content
2. kb_audit_status()              → see current gaps (if watchlist is set)
   OR kb_report()                 → full state snapshot if starting fresh
3. proceed based on gaps / plan
```

---

## Tool Reference

### Planning Tools (9)

**`plan_goal(goal, lang="en")`**
Decompose a goal into an atomic task graph. Returns `session_id`, AI reply, and initial nodes.
Call this first. Use `session_id` in all subsequent planning calls.

```
→ { session_id, reply, nodes: [{id, name, status, source, description}] }
```

**`get_todo_nodes(session_id)`**
Return only nodes with status `todo` or `unknown`. Use this to decide what to work on next.
```
→ { remaining: int, nodes: [...] }
```

**`get_nodes(session_id, status_filter="")`**
All nodes, optionally filtered by `todo/done/skip/unknown/deferred`.
```
→ { nodes: [...], summary: {done, todo, unknown, skip, deferred} }
```

**`mark_done(session_id, node_id)`**
Mark a task complete. Supports short node IDs (first 8 chars).
```
→ { done: true, node: {id, name, status}, remaining_tasks: int }
```

**`mark_skip(session_id, node_id)`**
Mark a task as not needed.

**`add_node(session_id, name, description="")`**
Add a task the AI didn't suggest. Auto-embeds and connects via proximity edges.

**`send_message(session_id, message, lang="en")`**
Continue the planning conversation. Returns new nodes and `planning_complete` flag.
```
→ { reply, new_nodes: [...], planning_complete: bool }
```

**`export_markdown(session_id)`**
Export the task graph as a Markdown checklist (done/todo/skip sections).

**`list_sessions()`**
List all past planning sessions with goals and node counts.

---

### Knowledge Base Tools (13)

**`kb_import_text(text, source_name="", ttl_days=None)`**
Add plain text to the KB. `ttl_days=0` = never expires (default). `ttl_days=N` = expires after N days.
```
→ { ok: true, chunks: int, source: str }
```

**`kb_import_url(url, source_name="", ttl_days=None)`**
Crawl a URL and import its content.

**`kb_update_url(url, source_name="", ttl_days=None)`**
Re-crawl a URL, replacing existing chunks. Use when the page has been updated.

**`kb_import_pdf(pdf_url, source_name="")`**
Download a PDF and import it in page batches. Handles large documents (tested: 1866 pages).

**`kb_import_jsonl(content, source_name="", ttl_days=None)`**
Batch import. Each line must be `{"text": "...", "source": "optional"}`.

**`kb_search(query, n=5, group_by_source=False)`**
Semantic search. `group_by_source=False` → raw chunks with text snippets.
`group_by_source=True` → results grouped by source, best similarity score per source.
Use `group_by_source=True` to discover which documents cover a concept.

**`kb_ask(query, lang="en")`**
RAG Q&A grounded in KB content. Returns answer with source citations. No hallucination.
```
→ { answer: str, sources: [str], chunks_used: int }
```

**`kb_set_credibility(source, credibility)`**
Set trust weight (0.0–1.0) for a source. Affects `weighted_source_score` in verify/audit.
Defaults: pdf/text=0.9, jsonl=0.8, url=0.7, crawler=0.4.

**`kb_list_sources()`**
List all imported sources: name, chunk count, credibility.

**`kb_delete_source(source)`**
Delete all chunks for a source. Use `kb_list_sources` first to get exact names.

**`kb_status()`**
KB health check: total chunk count, URL count, recently crawled sources.

---

### Verification & Audit Tools (7)

**`kb_verify(concept_a, concept_b, verifier_id="system")`**
Verify the connection between two concepts using only KB evidence. No LLM involved.
All numbers are system-computed from embeddings and document statistics.
Stores report in ChromaDB; `prior_verifications` accumulates across distinct `verifier_id` values.

```
→ {
    kb_support_score: float,          # 0–1, weighted formula (see below)
    details: {
      embedding_similarity: float,    # cosine similarity of concept vectors
      bidirectional: bool,            # each concept found in other's neighborhood
      co_mention_count: int,          # chunks containing both concepts
      weighted_source_score: float,   # sum of credibility weights of supporting sources
      kb_coverage_a: float,           # how well KB covers concept_a (0–1)
      kb_coverage_b: float,
    },
    prior_verifications: int,         # distinct verifier_ids that confirmed this pair
    data_sufficient: bool             # False if KB has too little content on either concept
  }
```

**`kb_audit(concepts=[], pairs=[], pre_filter_threshold=0.3, verifier_id="system")`**
Batch audit for a set of concepts or explicit pairs. Two-stage pipeline:

Stage 1 — Pre-filter: batch embed all concepts (one API call), compute pairwise cosine.
Pairs below `pre_filter_threshold` → skipped (semantically unrelated, gap is expected).

Stage 2 — Full verify: run `kb_verify` on each passing pair.

```
→ {
    run_id: str,
    summary: { total_pairs, skipped_by_prefilter, verified, gaps, weak, strong },
    gaps:   [{ concept_a, concept_b, kb_support_score, details, fix_hints }],
    weak:   [{ concept_a, concept_b, kb_support_score, details }],
    strong: [{ concept_a, concept_b, kb_support_score, details }],
    skipped: [{ concept_a, concept_b, embedding_similarity, reason }]
  }
```

`fix_hints` in each gap:
```
{
  sources_with_a_only: [str],    # KB sources covering concept_a but not concept_b
  sources_with_b_only: [str],    # KB sources covering concept_b but not concept_a
  sources_with_both: [str],      # sources already covering both
  suggested_action: str          # e.g. "Add mention of 'B' to: source-X"
}
```

**`kb_audit_history(concept_a, concept_b, limit=20)`**
Return audit history for a concept pair, newest first.
Shows whether a gap was open or closed across past runs.
```
→ [{ run_at, concept_a, concept_b, status, score, co_mention, fix_hint }]
```

**`kb_watch_concepts(concepts)`**
Add concepts to the persistent audit watchlist.
The watchlist survives server restarts; use `kb_audit_status` to query it.

**`kb_unwatch_concept(concept)`**
Remove a concept from the watchlist.

**`kb_audit_status(verifier_id="watchlist")`**
Run `kb_audit` on the current watchlist. Returns live gap status.
Call at session start to know what documentation work remains.

**`kb_report(format="markdown", verifier_id="report")`**
Generate a full KB completeness report:
- All knowledge sources with chunk counts and credibility
- Live audit of watchlist (gaps, weak, strong with fix_hints)
- Audit history summary (trends across all runs)
- Synced files and staleness status

`format="markdown"` → human-readable string (like a PROJECT.md)
`format="json"` → structured dict for programmatic processing

---

### File Sync Tools (2)

**`kb_sync_file(file_path, source_name="", force=False)`**
Sync a local file into the KB. Compares file mtime to last-synced mtime.
If unchanged → returns `{changed: false}` without re-importing (no wasted embed calls).
If changed → deletes old chunks and re-imports. Registers file in sync registry.

```
→ { ok: true, changed: bool, chunks: int, source: str }
```

**`kb_list_file_watches()`**
List all registered files with path, source name, last sync time, and staleness.

---

## Standard Workflows

### Workflow 1 — Task tracking agent

```python
# Start
result = plan_goal("write a paper on transformer attention mechanisms")
session_id = result["session_id"]

# Work loop
while True:
    remaining = get_todo_nodes(session_id)
    if remaining["remaining"] == 0:
        break
    node = remaining["nodes"][0]
    # ... do work on node["name"] ...
    mark_done(session_id, node["id"])

# Export
export_markdown(session_id)
```

### Workflow 2 — Self-directed work loop (documentation gap closure)

```python
# Setup watchlist once
kb_watch_concepts(["concept_a", "concept_b", "concept_c", "concept_d"])

# At session start — know what's missing
status = kb_audit_status()
gaps = status["gaps"]

# Fix each gap
for gap in gaps:
    hint = gap["fix_hints"]["suggested_action"]
    # e.g. "Add mention of 'concept_b' to: my-source-file"
    # → edit the file → sync it back
    kb_sync_file("/path/to/source_file.py", source_name="my-source-file")

# Confirm gaps closed
status = kb_audit_status()
# gaps should be empty or reduced
```

### Workflow 3 — Company knowledge hub

```python
# Agent A: ingest documents
kb_import_url("https://internal-wiki/onboarding", source_name="Onboarding", ttl_days=30)
kb_import_pdf("https://docs/api-reference.pdf", source_name="API Docs")
kb_import_jsonl(
    '{"text":"Deploy via: docker run ...", "source":"ops"}\n'
    '{"text":"Rollback: kubectl rollout undo ...", "source":"ops"}',
    source_name="Ops Runbook"
)
kb_set_credibility("Onboarding", 0.9)

# Agent B: query at work time
answer = kb_ask("How do I deploy a hotfix?")
# → grounded answer with source citations

chunks = kb_search("authentication flow", n=5)
# → top relevant KB chunks
```

### Workflow 4 — Bulk agent evaluation (ground-truth-free)

Use when an agent makes factual claims about concept connections and you want
to verify them without asking another LLM (avoids circular trust).

```python
# Agent claims: "deployment is connected to monitoring"
result = kb_verify("deployment", "monitoring", verifier_id="agent-run-001")

if result["details"]["co_mention_count"] == 0:
    # Connection only exists in agent's claim, not in KB evidence
    print("Weak claim — not supported by KB")
elif result["kb_support_score"] >= 0.6:
    print("Strong claim — KB evidence supports connection")

# Audit all claims at once
audit = kb_audit(
    pairs=[
        {"a": "deployment", "b": "rollback procedure"},
        {"a": "monitoring", "b": "on-call runbook"},
        {"a": "incident response", "b": "alerting"},
    ],
    verifier_id="agent-eval-batch-001"
)
```

---

## Interpreting Results

### `kb_support_score`

Weighted formula: `0.4 × embedding_similarity + 0.3 × min(co_mention/5, 1) + 0.3 × min(weighted_source/2, 1)`

| Score | Meaning |
|-------|---------|
| ≥ 0.6 | **Strong** — concepts well-connected in KB |
| 0.3–0.6 | **Weak** — some evidence but connection not fully documented |
| < 0.3 | **No support** — effectively unrelated in KB |

### Status categories

| Status | Condition | Action |
|--------|-----------|--------|
| `gap` | `co_mention_count == 0` | Follow `fix_hints.suggested_action` |
| `weak` | `co_mention > 0`, score < 0.6 | Import more content linking the two concepts |
| `strong` | score ≥ 0.6 | No action needed |
| `skipped` | embedding_similarity < `pre_filter_threshold` | Pair is semantically unrelated — gap is expected, not a problem |

### `co_mention_count`

Number of KB chunks that contain both concept strings in the same text block.
`co_mention_count == 0` means the connection exists in design intent but is not
documented anywhere in the KB — the gap will confuse future agents and readers.

### `fix_hints.suggested_action`

Direct instruction: which KB source to add documentation to.
Example: `"Add mention of 'agent evaluation' to: Aporia-MCP"`
→ edit that source file → call `kb_sync_file` to update KB → re-run audit to confirm.

### `prior_verifications`

Count of distinct `verifier_id` values that have confirmed a concept pair.
Higher = more independent confirmation = higher confidence.
Use different `verifier_id` values across agents and sessions to accumulate evidence.

### `data_sufficient`

`False` means the KB has too little content about one or both concepts.
In this case, `kb_support_score` is unreliable — import more relevant documents first.

---

## Source Credibility

Sources have a trust weight (0.0–1.0) that affects `weighted_source_score`.

| Import method | Default credibility | Typical use |
|---------------|--------------------:|-------------|
| pdf / text | 0.9 | Internal docs, manuals, curated content |
| jsonl | 0.8 | Structured knowledge, runbooks |
| url | 0.7 | External web pages |
| crawler | 0.4 | Auto-crawled, lower trust |

Override with `kb_set_credibility(source_name, weight)`.

---

## TTL (Content Freshness)

`ttl_days` controls when content expires:
- `ttl_days=0` — never expires (default for text imports)
- `ttl_days=1` — live data (prices, news)
- `ttl_days=30` — monthly updates (internal wikis)
- `ttl_days=365` — stable reference docs
- `ttl_days=None` — use category default from `freshness.yaml`

---

## File Sync vs. Manual Import

| Situation | Use |
|-----------|-----|
| New content | `kb_import_text` / `kb_import_url` |
| File changes frequently (code, docs) | `kb_sync_file` — skips if unchanged |
| URL content updated | `kb_update_url` — deletes old chunks, re-crawls |
| Delete a source | `kb_delete_source` |
