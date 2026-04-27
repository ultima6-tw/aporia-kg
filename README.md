# Ragraphe

**A conversation-driven knowledge graph that grows with you.**

You tell Ragraphe your goal. It builds a visual map of everything you need to get there — including the things you didn't know you needed.

> *"You don't know what you don't know."* Ragraphe is an AI mentor that surfaces the gaps you can't see yet.

---

## What it does

Most tools answer questions you already know how to ask. Ragraphe works differently: it starts from your goal and reverse-plans the path.

Tell it **"I want to climb Mt. Fuji"** or **"I want to learn machine learning"** or **"I want to launch a product"** — and it builds a knowledge graph of everything required, including prerequisites you never thought to mention.

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

Small orbiting dots around nodes are **knowledge satellites** — real content fragments pulled from the local RAG database, relevant to that node.

---

## Features

- **Organic graph growth** — starts empty, grows through conversation
- **Dual LLM pipeline** — ChatExtract (dialogue + concept extraction) runs in parallel with Planner (RAG-driven gap detection)
- **Semantic edges** — nodes connect automatically via cosine similarity (threshold 0.28), no manual wiring
- **Deep-dive exploration** — click any node or satellite to auto-send a sub-topic breakdown request to the AI
- **Dynamic theme anchor** — deep-dive uses the most important node in that area as context, not just the initial goal
- **RAG knowledge satellites** — orbiting dots show real snippets from the local knowledge base
- **Session persistence** — SQLite-backed, survives server restarts
- **Session history panel** — switch between or restore past sessions
- **Cross-session memory** — what you've already learned doesn't get re-suggested
- **Undo / rollback** — snapshot before each round, restore up to 5 steps back
- **Quality feedback loop** — 👍/👎 on AI-suggested nodes; bad suggestions filtered in future rounds
- **Popularity heatmap** — nodes completed by many users get an amber ring + ★ indicator
- **Coverage visualization** — glass-ball nodes fill up as a topic gets discussed
- **Markdown export** — done/todo/skip checklist for Notion, Obsidian, etc.
- **Knowledge base import** — PDF, URL, plain text, topic crawl
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
| LLM | Gemini 2.5 Flash (default) or Ollama |
| Embeddings | Gemini embedding-2 (3072d) or nomic-embed-text (768d) |
| Vector DB | ChromaDB (local) |
| Relational DB | SQLite (default) or PostgreSQL |
| Backend | FastAPI + SSE streaming |
| Frontend | force-graph (canvas 2D), vanilla JS — no build step |

The entire frontend is embedded in a single Python file (`ragraphe/api/main.py`). No npm, no bundler, no separate build process.

---

## Quick Start

### Prerequisites

- Python 3.11+
- A [Gemini API key](https://aistudio.google.com/) — free tier works fine

### 1. Clone and install

```bash
git clone https://github.com/YOUR_USERNAME/ragraphe.git
cd ragraphe

python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Open `.env` and fill in your Gemini API key:

```
LLM_BACKEND=gemini
GEMINI_API_KEY=your_key_here
```

### 3. Run

```bash
uvicorn ragraphe.api.main:app --reload --port 7860
```

Open [http://localhost:7860](http://localhost:7860), type a goal, and watch the graph grow.

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

Ragraphe works best when the local knowledge base has content relevant to your domain.

Use the **Knowledge Base panel** (📚 icon in the top bar) to import:

| Source | How |
|--------|-----|
| **PDF** | Upload textbooks, papers, manuals |
| **URL** | Paste a URL — the page gets crawled and chunked |
| **Plain text** | Paste notes, documentation, anything |
| **Topic crawl** | Enter a topic — auto-fetches Wikipedia + web results |

All content is chunked, embedded, and stored locally in ChromaDB. Delete any source from the same panel.

**Without any imports**, Ragraphe still works — the AI plans nodes from its own knowledge. The knowledge base just makes the satellite snippets more relevant and the planner more context-aware.

---

## Usage Tips

**Starting a session**
- Type any goal, however broad: *"learn to cook Japanese food"*, *"build a FPGA project"*, *"start a coffee shop"*
- The first response gives you 8–15 nodes right away (Seed Expansion)

**Navigating the graph**
- Click any node → popup with status, description, and action buttons
- Click **🔍 深入探索 / Deep dive** → AI breaks that node into sub-topics
- Click any orbiting dot (satellite) → full knowledge snippet in the right panel
- Hover nodes for a tooltip summary

**Managing the map**
- ✓ **Mark done** — click a node → "Mark complete"
- ↩ **Skip** — dismiss nodes you don't need; skipping one option auto-collapses sibling choices
- ⎌ **Undo** — restore the previous graph state (up to 5 steps)
- 📥 **Export** — when the map is complete, export as Markdown checklist

**Switching layout**
Use the ⊞ button (bottom right) to switch between force-directed, tree (top-down / left-right), and radial layouts.

---

## How It Solves "Unknown Unknowns"

Most people planning a complex goal don't know what they don't know. They can't Google what they haven't thought of.

Ragraphe's AI acts like an experienced mentor:
1. Listens to what you say → extracts your explicit concepts
2. Checks the knowledge base → finds what experienced people consider necessary
3. Shows you the gap → adds nodes for the things you didn't mention

The more people use it for similar goals, the more useful the popularity heatmap becomes — showing which nodes nearly everyone needs.

---

## Project Structure

```
ragraphe/
├── api/
│   └── main.py          # FastAPI app + entire frontend (HTML/JS/CSS)
├── core/
│   ├── crawler.py       # Web crawler (Wikipedia + DuckDuckGo fallback)
│   ├── conversation.py  # Conversation utilities
│   └── category.py      # Content category inference
├── db/
│   └── store.py         # SQLite / PostgreSQL abstraction layer
├── llm/
│   ├── gemini_client.py # Gemini API client (chat + embed + retry)
│   └── ollama_client.py # Ollama client
└── data/
    ├── enrich_nodes.py  # Batch node enrichment script
    └── seed_travel.py   # Travel domain seed data
```

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

- Domain-specific knowledge bases (import via the UI or `seed_*.py` scripts)
- Improved LLM prompts for specific fields
- New export formats
- UI improvements

---

## License

MIT
