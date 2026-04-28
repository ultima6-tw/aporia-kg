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
- **Semantic edges** — nodes connect automatically via cosine similarity (threshold 0.28), no manual wiring
- **Deep-dive exploration** — click any node or satellite to auto-send a sub-topic breakdown request to the AI
- **Dynamic theme anchor** — deep-dive uses the most important node in that area as context, not just the initial goal
- **RAG knowledge satellites** — orbiting dots show snippets scored for relevance + freshness; generic content the LLM already knows is filtered out
- **Satellite scoring** — multi-category bonuses (a chunk can belong to travel + news simultaneously; best bonus + fastest decay applied), exponential time-decay for time-sensitive content, auto re-crawl when content goes stale
- **Content-language filter** — EN / ZH / JA toggle buttons filter which knowledge base languages appear as satellites
- **Session persistence** — SQLite-backed, survives server restarts
- **Session history panel** — switch between or restore past sessions
- **Cross-session memory** — what you've already learned doesn't get re-suggested
- **Undo / rollback** — snapshot before each round, restore up to 5 steps back
- **Quality feedback loop** — 👍/👎 on AI-suggested nodes; bad suggestions filtered in future rounds
- **Popularity heatmap** — nodes completed by many users get an amber ring + ★ indicator
- **Coverage visualization** — glass-ball nodes fill up as a topic gets discussed
- **Markdown export** — done/todo/skip checklist for Notion, Obsidian, etc.
- **Knowledge base import** — PDF, URL, plain text, topic crawl (large PDFs supported — tested with 1866-page instrument manuals)
- **Grounded node answers** — click any node → KB-backed answer with source citations, not LLM guessing
- **MCP client** — use Aporia KG as a tool inside Claude Code or any MCP-compatible AI agent
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
          Semantic edge calculation (cosine distance < 0.28)
                    ↓
          Completion check → SSE stream to frontend
```

**Stack:**

| Component | Technology |
|-----------|-----------|
| LLM | Gemini 2.5 Flash (default) or Ollama (fully local) |
| Embeddings | Gemini embedding-2 (3072d) or nomic-embed-text via Ollama (768d) |
| Vector DB | ChromaDB (local) |
| Relational DB | SQLite (default) or PostgreSQL |
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
| `LLM_BACKEND` | `ollama` | `gemini` or `ollama` |
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

All content is chunked, embedded, and stored locally in ChromaDB. The content language (EN / ZH / JA) is auto-detected and tagged, so you can filter which languages appear as knowledge satellites per session.

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
│   ├── crawler.py       # Web crawler (Wikipedia + DuckDuckGo fallback)
│   ├── conversation.py  # Conversation utilities
│   └── category.py      # Content category inference
├── config/
│   ├── freshness.yaml   # 24-topic TTL configuration
│   └── freshness.py     # Topic detection + TTL resolution
├── db/
│   └── store.py         # SQLite / PostgreSQL abstraction layer
├── client/
│   ├── aporia_client.py # Python client (KB import, search, kb_ask)
│   └── aporia_mcp.py    # FastMCP server exposing KB tools to AI agents
└── llm/
    ├── gemini_client.py # Gemini API client (chat + embed + retry)
    └── ollama_client.py # Ollama client
```

---

## MCP Integration (Claude Code)

Aporia KG ships a FastMCP client (`ragraphe/client/aporia_mcp.py`) that exposes KB import and Q&A as MCP tools — use it inside Claude Code or any MCP-compatible agent.

### Register the server

```bash
claude mcp add aporia-kg -s user \
  -e APORIA_URL=http://localhost:7860 \
  -- /path/to/aporia-kg/.venv/bin/python -m ragraphe.client.aporia_mcp
```

### Available MCP tools

| Tool | Description |
|------|-------------|
| `kb_import_url` | Crawl a URL and add it to the KB |
| `kb_import_pdf` | Download a PDF and import page-by-page |
| `kb_import_text` | Import raw text directly |
| `kb_search` | Semantic search over KB chunks |
| `kb_ask` | Grounded Q&A — search KB, build context, answer via Gemini with source citations |

**Example use case:** Import a 1800-page instrument manual, then ask `kb_ask("How do I set up a SCPI trigger on MXO4?")` — you get an answer based on the actual manual content, not LLM guessing.

---

## Roadmap

- [ ] Shareable read-only session links
- [ ] Goal-similarity matching (suggest paths from similar past sessions)
- [ ] Multi-format export (Mermaid, JSON)
- [ ] YouTube transcript ingestion
- [ ] User authentication

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
