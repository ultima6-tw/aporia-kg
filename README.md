# Aporia KG

**A conversation-driven knowledge graph that grows with you.**

You tell Aporia KG your goal. It builds a visual map of everything you need to get there — including the things you didn't know you needed.

> *"You don't know what you don't know."* Aporia KG acts as an AI mentor that surfaces the gaps you can't see yet.

---

## What it does

Most tools answer questions you already know how to ask. Aporia KG works differently: it starts from your goal and reverse-plans the path.

Tell it **"I want to climb Mt. Fuji"** or **"I want to learn machine learning"** or **"I want to launch a product"** — and it builds a knowledge graph of everything required, including prerequisites you never thought to mention.

It's especially useful for **academic research**: upload your papers, then tell it your research topic. Aporia KG pulls relevant concepts, methods, and connections from your literature and maps them visually — so you can see where your contribution fits before you write a single sentence.

> *"I'm writing a paper on transformer attention mechanisms — help me map the literature"*

As you talk, the graph evolves organically. Every message adds nodes, resolves unknowns, and tightens the map.

### Node types

| Color | Meaning |
|-------|---------|
| 🔵 Blue | Concepts you've confirmed |
| 🟠 Orange (large) | Things the AI planned as necessary — confirm to add |
| 🟠 Orange (small) | Exclusive choice options from the AI — pick one |
| 🟢 Green | Completed |
| ⚪ Grey | Skipped or ruled out by a prior choice |
| 🟣 Purple dashed | Deferred — you said "not sure yet" |

Small orbiting dots around nodes are **knowledge satellites** — content fragments scored for relevance and freshness. Only content that genuinely adds value over what the LLM already knows appears as a satellite.

---

## Features

- **Organic graph growth** — starts empty, grows through conversation
- **Dual LLM pipeline** — ChatExtract (dialogue + concept extraction) runs in parallel with Planner (RAG-driven gap detection)
- **Semantic edges** — nodes connect automatically via cosine similarity (threshold 0.38), no manual wiring
- **Node inline editing** — click ✏️ in any node popup to rename or edit the description; the node is re-embedded and proximity edges recalculated automatically
- **Real-time search** — time-sensitive queries ("today's rate", "latest news") automatically bypass the cache and pull live results
- **Deep-dive exploration** — click any node or satellite to auto-send a sub-topic breakdown request to the AI
- **Dynamic theme anchor** — deep-dive uses the most important node in that area as context, not just the initial goal
- **RAG knowledge satellites** — orbiting dots show snippets scored for relevance + freshness; generic content the LLM already knows is filtered out
- **Satellite scoring** — multi-category bonuses (a node can belong to travel + news simultaneously; best bonus + fastest decay applied), exponential time-decay for time-sensitive content, auto re-crawl when content goes stale
- **Content-language filter** — EN / ZH / JA toggle buttons filter which knowledge base languages appear as satellites
- **KB source filter** — per-session checkbox to select which imported documents contribute to satellite knowledge
- **Note Mode** — toggle off automatic node generation; AI still responds, you build the map manually
- **Manual node creation** — add a node via toolbar button or right-click on the graph canvas
- **Session persistence** — SQLite-backed, survives server restarts
- **Session history panel** — switch between or restore past sessions
- **Cross-session memory** — what you've already learned doesn't get re-suggested
- **Undo / rollback** — snapshot before each round, restore up to 5 steps back
- **Quality feedback loop** — 👍/👎 on AI-suggested nodes; bad suggestions filtered in future rounds
- **Popularity heatmap** — nodes completed by many users get an amber ring + ★ indicator
- **Coverage visualization** — glass-ball nodes fill up as a topic gets discussed
- **Markdown export** — done/todo/skip checklist for Notion, Obsidian, etc.
- **Knowledge base import** — PDF, URL, plain text, JSONL; content is extracted into Obsidian-style atomic notes by Gemini (title + summary + explicit concept links), not raw text chunks — large PDFs use map-reduce with TOC-based splitting
- **MCP server** — use Aporia KG as a goal-decomposition + task-tracking tool inside Claude Code or any MCP-compatible AI agent
- **Multi-language** — Traditional Chinese, English, Japanese (UI + AI responses)
- **PostgreSQL support** — set `DATABASE_URL` to switch from SQLite

---

## Architecture

```
User input
    ├── [Thread A] LLM-ChatExtract
    │     reply + user_concepts + ai_suggestions + decision_reason
    └── [Thread B] LLM-Plan  (uses previous graph snapshot, runs in parallel)
          RAG query → necessary node suggestions
                    ↓ join threads
          Code-based expansion (location × concept matrix)
                    ↓
          Semantic edge calculation (cosine distance < 0.38)
                    ↓
          Completion check → SSE stream to frontend
```

**Stack:**

| Component | Technology |
|-----------|-----------|
| LLM | Gemini 2.5 Flash (default) or Ollama (fully local) |
| Embeddings | Gemini embedding-2 (3072d) or nomic-embed-text via Ollama (768d) |
| Vector DB | ChromaDB (local) — notes collection + satellite raw_chunks |
| Relational DB | SQLite (default) or PostgreSQL — notes, audit history, credibility |
| Backend | FastAPI + SSE streaming |
| Frontend | force-graph (canvas 2D), vanilla JS — no build step |

**Designed to be lightweight.** The dual-LLM pipeline (ChatExtract + Planner) is optimized for minimal token usage — each conversation round makes exactly two LLM calls. With Ollama, the entire system runs locally with no API costs and no data leaving your machine, which matters for sensitive research materials.

---

## Quick Start

### Prerequisites

- Python 3.11+
- A [Gemini API key](https://aistudio.google.com/) (free tier) — or [Ollama](https://ollama.ai) for fully local mode

### One-line install (macOS / Linux)

```bash
git clone https://github.com/ultima6-tw/aporia-kg.git
cd aporia-kg
bash install.sh
```

The script checks your Python version, creates a virtual environment, installs dependencies, asks whether you want Gemini or Ollama, writes `.env`, and optionally starts the server and opens your browser.

### Manual install

```bash
git clone https://github.com/ultima6-tw/aporia-kg.git
cd aporia-kg

python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: set LLM_BACKEND=gemini and GEMINI_API_KEY=your_key_here

uvicorn ragraphe.api.main:app --port 7860
```

Open [http://localhost:7860](http://localhost:7860). The welcome screen shows 5 example cards — click one to start immediately, or type your own goal.

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_BACKEND` | `gemini` | `gemini` or `ollama` |
| `GEMINI_API_KEY` | — | Required when `LLM_BACKEND=gemini` |
| `DATABASE_URL` | — | PostgreSQL URL — omit to use SQLite |

### Using Ollama instead of Gemini

If you have [Ollama](https://ollama.ai) running locally:

```bash
# In .env:
LLM_BACKEND=ollama
# GEMINI_API_KEY not needed

# Pull a model (example):
ollama pull gemma3
ollama pull nomic-embed-text
```

> Note: Ollama uses nomic-embed-text (768d) for embeddings. If you switch between Gemini and Ollama, clear the ChromaDB data first (`data/chroma`) to avoid dimension conflicts.

---

## Adding Knowledge

Aporia KG works best when the local knowledge base has content relevant to your domain.

Use the **Knowledge Base panel** (📚 icon in the top bar) to import:

| Source | How |
|--------|-----|
| **PDF** | Upload textbooks, papers, manuals |
| **URL** | Paste a URL — the page gets crawled and chunked |
| **Plain text** | Paste notes, documentation, anything |
| **Topic crawl** | Enter a topic — auto-fetches Wikipedia + web results |

All content is passed through Gemini at import time and extracted into **Obsidian-style atomic notes** (title + 1–3 sentence summary + explicit concept links). Notes are embedded and stored locally in ChromaDB + SQLite. The content language (EN / ZH / JA) is auto-detected and tagged, so you can filter which languages appear as knowledge satellites per session.

**Without any imports**, Aporia KG still works — the AI plans nodes from its own knowledge. The knowledge base just makes the satellite snippets more relevant and the planner more context-aware.

---

## Usage Tips

**Starting a session**
- Type any goal, however broad: *"learn to cook Japanese food"*, *"build a FPGA project"*, *"start a coffee shop"*, *"write a paper on transformer attention mechanisms"*
- The first response gives you 8–15 nodes right away (Seed Expansion)

**Navigating the graph**
- Click any node → popup with status, description, and action buttons
- Click **🔍 Deep dive** → AI breaks that node into sub-topics
- Click any orbiting dot (satellite) → full knowledge snippet in the right panel
- Hover nodes for a tooltip summary

**Managing the map**
- ✓ **Mark done** — click a node → "Mark complete"
- ✏️ **Edit** — click the pencil button in any node popup to rename or update the description inline; edges recalculate automatically
- ↩ **Skip** — dismiss nodes you don't need; skipping one option auto-collapses sibling choices
- ⎌ **Undo** — restore the previous graph state (up to 5 steps)
- 📥 **Export** — when the map is complete, export as Markdown checklist

**Switching layout**
Use the ⊞ button (zoom controls, right side) to switch between force-directed, tree (top-down / left-right), and radial layouts.

---

## How It Solves "Unknown Unknowns"

Most people planning a complex goal don't know what they don't know. They can't Google what they haven't thought of.

Aporia KG's AI acts like an experienced mentor:
1. Listens to what you say → extracts your explicit concepts
2. Checks the knowledge base → finds what experienced people consider necessary
3. Shows you the gap → adds nodes for the things you didn't mention

The more people use it for similar goals, the more useful the popularity heatmap becomes — showing which nodes nearly everyone needs.

---

## Project Structure

```
ragraphe/
├── api/
│   └── main.py          # FastAPI app + API endpoints
├── frontend/
│   ├── index.html       # App shell
│   ├── style.css        # Styles
│   └── app.js           # Graph + chat logic (force-graph, SSE, i18n)
├── core/
│   ├── extractor.py     # Obsidian-style note extraction (Gemini, map-reduce for large docs)
│   ├── crawler.py       # Web crawler (Wikipedia + DuckDuckGo) + satellite raw_chunks
│   ├── verifier.py      # KB connection verifier (kb_verify + kb_audit, no LLM)
│   ├── conversation.py  # Conversation utilities
│   └── category.py      # Content category inference
├── config/
│   ├── freshness.yaml   # 25-topic TTL configuration (including default)
│   └── freshness.py     # Topic detection + TTL resolution
├── db/
│   └── store.py         # SQLite / PostgreSQL abstraction layer
├── client/
│   ├── aporia_client.py # Python HTTP/SSE client library
│   ├── aporia_cli.py    # CLI tool (plan / nodes / done / skip / add / chat / export / sessions / kb)
│   └── aporia_mcp.py    # FastMCP server exposing KB + graph tools to AI agents
└── llm/
    ├── gemini_client.py # Gemini API client (chat + embed + retry)
    └── ollama_client.py # Ollama client
```

---

## MCP Integration

Aporia KG ships a FastMCP server (`ragraphe/client/aporia_mcp.py`) that exposes 29 tools across two categories: **goal-planning** and **knowledge base**. Any MCP-compatible agent (Claude Code, Cursor, or a custom script) can use these tools to decompose goals, manage tasks, import knowledge, verify concept connections, and audit documentation gaps.

### Register the server

```bash
claude mcp add aporia-kg -s user \
  -- /path/to/aporia-kg/.venv/bin/python -m ragraphe.client.aporia_mcp
```

Or add to your MCP config manually:

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

### Planning tools

| Tool | Description |
|------|-------------|
| `plan_goal` | Decompose a goal into an atomic task graph; returns `session_id` + nodes |
| `get_nodes` | List all nodes with status; optionally filter by `todo/done/skip/unknown` |
| `get_todo_nodes` | Get only remaining tasks — use this to stay focused |
| `mark_done` | Mark a task node as completed |
| `mark_skip` | Mark a task node as skipped |
| `add_node` | Manually add a task node the AI didn't suggest |
| `send_message` | Continue the planning conversation to refine or expand the graph |
| `export_markdown` | Export the task graph as a Markdown checklist |
| `list_sessions` | List all past planning sessions |

### Knowledge base tools — Import & Search

| Tool | Description |
|------|-------------|
| `kb_import_url` | Crawl a webpage and add its content to the KB |
| `kb_update_url` | Re-crawl an existing URL source to refresh its content |
| `kb_import_pdf` | Download a PDF from a URL and import it |
| `kb_import_text` | Add plain text directly to the KB |
| `kb_import_jsonl` | Batch-import structured knowledge (JSONL, one `{"text":"..."}` per line) |
| `kb_search` | Semantic search; set `group_by_source=True` for concept-neighbor view |
| `kb_ask` | Get a grounded answer from the KB — no hallucination, cites sources |
| `kb_set_credibility` | Set the trust weight (0.0–1.0) for a knowledge source |
| `kb_list_sources` | List all imported sources with note counts and credibility |
| `kb_delete_source` | Delete all notes belonging to a source |
| `kb_status` | KB health check: total notes, source count, URL count |

### Knowledge base tools — Verification & Audit

| Tool | Description |
|------|-------------|
| `kb_verify` | Verify the connection between two concepts using KB evidence (no LLM) — returns `kb_support_score` + 5 detail signals |
| `kb_audit` | Batch audit a set of concepts — two-stage pipeline (pre-filter by embedding similarity, then full verify) |
| `kb_audit_history` | Return the audit history for a concept pair, newest first — track whether a gap was open or closed |
| `kb_watch_concepts` | Add concepts to the persistent audit watchlist (survives restarts) |
| `kb_unwatch_concept` | Remove a concept from the watchlist |
| `kb_audit_status` | Run `kb_audit` on the current watchlist — call at session start to see live gap status |
| `kb_report` | Generate a full KB completeness report (sources, watchlist gaps with fix_hints, audit trends) |

### Knowledge base tools — File Sync

| Tool | Description |
|------|-------------|
| `kb_sync_file` | Sync a local file into the KB — skips if unchanged (mtime check), re-extracts on change |
| `kb_list_file_watches` | List all registered files with path, source name, last sync time, and staleness |

---

## Automated Usage Patterns

### Pattern 1 — Task tracking agent

An agent building a research paper calls `plan_goal` once, then loops:

```
plan_goal("write a paper on transformer attention mechanisms")
  → session_id, initial nodes

loop:
  get_todo_nodes(session_id)     → what's left
  ... do work on the next task ...
  mark_done(session_id, node_id)
  → repeat until remaining == 0

export_markdown(session_id)      → paste into Notion / Obsidian
```

### Pattern 2 — Company knowledge hub

Any MCP-capable tool can push knowledge into Aporia KG and any other agent can query it out. Aporia KG acts as the protocol layer — it handles chunking, embedding, semantic search, and freshness tracking.

```
# Agent A (document ingestion):
kb_import_url("https://internal-wiki/onboarding", source_name="Onboarding Guide", ttl_days=30)
kb_import_pdf("https://docs/api-reference.pdf", source_name="API Reference")
kb_import_jsonl('{"text":"Deploy with: docker run ...","source":"ops-runbook"}', source_name="Runbooks")

# Agent B (query at work time):
kb_ask("How do I deploy a hotfix to production?")
  → grounded answer with source citations, no hallucination

kb_search("authentication flow", n=5)
  → top relevant notes across all imported sources (title + summary + links)
```

TTL (`ttl_days`) makes content self-expiring. Set `ttl_days=1` for live prices, `ttl_days=365` for stable docs.

Source credibility weights let you rank signal over noise:

```
kb_set_credibility("Onboarding Guide", 0.9)   # internal docs — high trust
kb_set_credibility("web-crawler-news", 0.3)   # scraped news — lower trust
```

### Pattern 3 — KB verification and audit

`kb_verify` checks whether two concepts are actually connected in the KB — without asking an LLM. All numbers come from embedding arithmetic and document statistics.

```
kb_verify("deployment", "rollback procedure", verifier_id="ops-agent")
→ {
    kb_support_score: 0.72,
    details: { embedding_similarity: 0.61, co_mention_count: 3, ... },
    prior_verifications: 1
  }
```

`kb_audit` runs this check for an entire set of concepts at once, using a two-stage pipeline to avoid unnecessary work:

```
kb_audit(
  concepts=["deployment", "rollback procedure", "monitoring", "on-call runbook", "incident response"],
  pre_filter_threshold=0.3   # skip pairs that are semantically unrelated
)
→ {
    summary: { total_pairs: 10, verified: 8, gaps: 3, weak: 2, strong: 3 },
    gaps: [
      {
        concept_a: "monitoring",
        concept_b: "on-call runbook",
        fix_hints: {
          sources_with_a_only: ["Runbooks"],
          suggested_action: "Add mention of 'on-call runbook' to: Runbooks"
        }
      },
      ...
    ]
  }
```

**Use kb_audit for code and documentation coverage:** import your codebase and design docs, then audit key concept pairs. `co_mention_count == 0` means the connection exists in your head but not in the code — the gap will cause confusion for future readers and downstream agents.

**How the two-stage pre-filter works:**

```
Stage 1 — Pre-filter (fast):
  Batch-embed all N concepts in one API call.
  Compute pairwise cosine similarity (pure math, no KB queries).
  Pairs below pre_filter_threshold → skipped (semantically unrelated).

Stage 2 — Full verify (only for passing pairs):
  Run kb_verify: explicit link check, co-mention count, source credibility, neighborhood check.
  Store each report in SQLite audit_history for future reference.
  prior_verifications accumulates across independent verifier_ids.
```

This keeps the audit tractable for large concept sets — a 20-concept audit (190 pairs) might only need 40–60 full verifications after pre-filtering.

---

## Roadmap

- [ ] **Conversation coverage visualization** — fill glass-ball nodes with color saturation as topics are discussed (backend `node_coverage` tracking already in place)

---

## Contributing

Pull requests welcome. Useful contributions:

- Domain-specific knowledge bases (import via the UI)
- Improved LLM prompts for specific fields
- New export formats
- UI improvements

---

## License

MIT
