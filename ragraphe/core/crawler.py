"""
Web crawler + RAG architecture for automatically expanding node knowledge

Crawl priority order:
  1. priority_sources (vendor/curated sources, sorted by priority number ascending)
  2. Wikipedia (general knowledge fallback)
  3. DuckDuckGo (last resort)

Pipeline:
  get_matching_sources() → crawl priority sources
  → insufficient → Wikipedia API
  → still insufficient → DuckDuckGo
  → all chunks → embed → store in raw_chunks
"""
import re
import uuid
import time
import threading
import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
import chromadb

from datetime import datetime, timedelta
import os as _os
_LLM_BACKEND = _os.getenv("LLM_BACKEND", "ollama").lower()
if _LLM_BACKEND == "gemini":
    from ragraphe.llm.gemini_client import chat, embed
else:
    from ragraphe.llm.ollama_client import chat, embed
from ragraphe.db.store import (
    get_node, upsert_node, get_matching_sources, _chroma,
    is_url_cached, mark_url_crawled,
)
from ragraphe.core.category import infer_category, CATEGORY_TTL, TIME_SENSITIVE

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Ragraphe/0.1)"}
CHUNK_SIZE    = 400
CHUNK_OVERLAP = 80
RAG_THRESHOLD = 0.6
MIN_CHUNKS    = 3   # Minimum target chunk count; falls through to the next source tier if not met

# Raw knowledge base (collection name is tied to embedding backend to avoid dimension conflicts)
_CHUNK_COLLECTION = f"raw_chunks_{_LLM_BACKEND}"   # e.g. raw_chunks_gemini / raw_chunks_ollama
raw_chunks = _chroma.get_or_create_collection(
    _CHUNK_COLLECTION,
    metadata={"hnsw:space": "cosine"}
)

_ALL_BACKENDS = ["gemini", "ollama"]

def _sync_from_other_backends():
    """
    Background thread: scans raw_chunks collections from other backends
    and re-embeds any chunks missing from the current collection before importing them.
    Text content is shared; only the vector representations differ.
    """
    other_backends = [b for b in _ALL_BACKENDS if b != _LLM_BACKEND]
    current_ids = set(raw_chunks.get(include=[])["ids"])

    for backend in other_backends:
        col_name = f"raw_chunks_{backend}"
        try:
            other_col = _chroma.get_collection(col_name)
        except Exception:
            continue  # This backend has never been used, skip it

        other_result = other_col.get(include=["documents", "metadatas"])
        missing = [
            (id_, doc, meta)
            for id_, doc, meta in zip(
                other_result["ids"],
                other_result["documents"],
                other_result["metadatas"],
            )
            if id_ not in current_ids
        ]
        if not missing:
            continue

        print(f"[sync] importing {len(missing)} entries from {col_name} into {_CHUNK_COLLECTION}...", flush=True)
        ok = 0
        for id_, doc, meta in missing:
            try:
                new_emb = embed(doc[:2000])
                raw_chunks.upsert(
                    ids=[id_],
                    embeddings=[new_emb],
                    documents=[doc],
                    metadatas=[meta],
                )
                current_ids.add(id_)
                ok += 1
                time.sleep(0.2)   # Avoid API rate limiting
            except Exception as e:
                print(f"[sync] skip {id_}: {e}", flush=True)
        print(f"[sync] done {ok}/{len(missing)} entries", flush=True)

# Run sync in the background at startup (non-blocking)
threading.Thread(target=_sync_from_other_backends, daemon=True).start()


# ── Crawler Utilities ────────────────────────────────────────────────────────────────

def _fix_mojibake(text: str) -> str:
    """Fix UTF-8 text incorrectly decoded as Latin-1 (common with requests on CJK pages).
    Handles chunks that were sliced mid-sequence by skipping leading continuation bytes."""
    try:
        raw = text.encode('latin-1')
    except UnicodeEncodeError:
        return text  # Contains non-Latin-1 chars → already correct Unicode
    # Skip leading UTF-8 continuation bytes (0x80-0xBF) caused by mid-sequence chunk cuts
    i = 0
    while i < min(3, len(raw)) and 0x80 <= raw[i] <= 0xBF:
        i += 1
    try:
        return raw[i:].decode('utf-8', errors='replace')
    except Exception:
        return text


def fetch_text(url: str, max_chars: int = 5000) -> str:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        resp.raise_for_status()
        # Always decode as UTF-8 from raw bytes to avoid requests' Latin-1 fallback
        try:
            body = resp.content.decode('utf-8')
        except UnicodeDecodeError:
            body = resp.text
        soup = BeautifulSoup(body, "lxml")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text[:max_chars]
    except Exception:
        return ""


def chunk_text(text: str, source_url: str) -> list[dict]:
    chunks = []
    start = 0
    while start < len(text):
        end   = start + CHUNK_SIZE
        chunk = text[start:end].strip()
        if len(chunk) > 50:
            chunks.append({
                "id":     str(uuid.uuid4()),
                "text":   chunk,
                "source": source_url,
            })
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


def _compute_expires(category: str, ttl_days: int | None) -> str | None:
    days = ttl_days if ttl_days is not None else CATEGORY_TTL.get(category, 30)
    if days <= 0:
        return None
    return (datetime.now() + timedelta(days=days)).isoformat()


def delete_chunks_by_source(source: str) -> int:
    """Delete all chunks from the specified source; returns the number deleted"""
    try:
        result = raw_chunks.get(where={"source": source}, include=[])
        ids = result.get("ids", [])
        if ids:
            raw_chunks.delete(ids=ids)
        return len(ids)
    except Exception:
        return 0


def list_chunk_sources() -> list[dict]:
    """List all unique sources in ChromaDB (including chunk count and source_name)"""
    try:
        result = raw_chunks.get(include=["metadatas"])
        sources: dict[str, dict] = {}
        for meta in result.get("metadatas", []):
            src = meta.get("source", "")
            if not src:
                continue
            if src not in sources:
                sources[src] = {
                    "source":      src,
                    "source_name": meta.get("source_name", "") or src,
                    "category":    meta.get("category", "general"),
                    "count":       0,
                }
            sources[src]["count"] += 1
        return sorted(sources.values(), key=lambda x: x["count"], reverse=True)
    except Exception:
        return []


def store_chunks(chunks: list[dict], category: str = "general", ttl_days: int | None = None):
    """
    chunks: list of {id, text, source}
    category / ttl_days determine expires_at, which is stored in ChromaDB metadata.
    """
    if not chunks:
        return
    expires_at = _compute_expires(category, ttl_days) or ""
    raw_chunks.upsert(
        ids        = [c["id"] for c in chunks],
        embeddings = [embed(c["text"]) for c in chunks],
        documents  = [c["text"] for c in chunks],
        metadatas  = [{
            "source":      c["source"],
            "source_name": c.get("source_name", ""),
            "category":    c.get("category", category),
            "expires_at":  c.get("expires_at", expires_at),
        } for c in chunks],
    )
    # Mark each source URL as crawled
    source_counts: dict[str, int] = {}
    for c in chunks:
        source_counts[c["source"]] = source_counts.get(c["source"], 0) + 1
    for url, count in source_counts.items():
        mark_url_crawled(url, count, category=category, ttl_days=ttl_days)


# ── PDF Parsing ─────────────────────────────────────────────────────────────────

def parse_pdf(file_path: str, max_chars: int = 30000) -> str:
    """Extract text from a local PDF file"""
    try:
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        pages = []
        total = 0
        for page in reader.pages:
            text = page.extract_text() or ""
            pages.append(text)
            total += len(text)
            if total >= max_chars:
                break
        return "\n".join(pages)[:max_chars]
    except Exception as e:
        print(f"[pdf error] {e}")
        return ""


# ── Wikipedia ───────────────────────────────────────────────────────────────

def fetch_wikipedia(query: str, lang: str = "zh") -> list[dict]:
    """
    Search and fetch summary + content via the Wikipedia API.
    Searches the specified language first; falls back to English if no results.
    """
    chunks = []
    for l in [lang, "en"] if lang != "en" else ["en"]:
        try:
            # Search
            search_url = f"https://{l}.wikipedia.org/w/api.php"
            _wiki_headers = {"User-Agent": "Ragraphe/0.1 (https://github.com/ragraphe; research bot)"}
            r = requests.get(search_url, headers=_wiki_headers, params={
                "action": "query", "list": "search",
                "srsearch": query, "srlimit": 2,
                "utf8": 1, "format": "json",
            }, timeout=8)
            hits = r.json().get("query", {}).get("search", [])
            if not hits:
                continue

            # Fetch the full text of the first result
            title = hits[0]["title"]
            r2 = requests.get(search_url, headers=_wiki_headers, params={
                "action": "query", "prop": "extracts",
                "titles": title, "explaintext": 1,
                "exsectionformat": "plain", "format": "json",
            }, timeout=10)
            pages = r2.json().get("query", {}).get("pages", {})
            for page in pages.values():
                text = page.get("extract", "")
                if text:
                    source = f"https://{l}.wikipedia.org/wiki/{title.replace(' ', '_')}"
                    chunks = chunk_text(text[:6000], source)
                    break

            if chunks:
                break
        except Exception:
            continue
    return chunks


# ── DuckDuckGo ──────────────────────────────────────────────────────────────

def search_urls(query: str, max_results: int = 3) -> list[str]:
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        return [r["href"] for r in results if "href" in r]
    except Exception:
        return []


def crawl_urls(urls: list[str]) -> list[dict]:
    chunks = []
    for url in urls:
        if is_url_cached(url):
            continue
        text = fetch_text(url)
        if text:
            chunks.extend(chunk_text(text, url))
    return chunks


# ── Query Generation (goal_type aware) ─────────────────────────────────────────────

_QUERY_TEMPLATES = {
    "travel":   ["{name} 旅遊資訊", "{name} 景點交通", "{name} 注意事項"],
    "learning": ["{name} 學習指南", "{name} 教學資源", "{name} 入門"],
    "project":  ["{name} 開發指南", "{name} 最佳實踐", "{name} 教學"],
    "research": ["{name} 研究資料", "{name} 文獻", "{name} overview"],
    "prompt":   ["{name} prompt 範例", "{name} AI 指令", "{name} template"],
    "general":  ["{name} 完整介紹", "{name} 步驟", "{name} 資訊"],
}

def generate_queries(node_name: str, goal_type: str = "general") -> list[str]:
    templates = _QUERY_TEMPLATES.get(goal_type, _QUERY_TEMPLATES["general"])
    return [t.format(name=node_name) for t in templates]


# ── Main Pipeline ──────────────────────────────────────────────────────────────────

def crawl_node_smart_stream(node: dict, goal_type: str = "general", wiki_lang: str = "zh"):
    """
    Smart crawl generator: priority_sources → Wikipedia → DuckDuckGo.
    wiki_lang: Wikipedia language to search first (e.g. "ja" for Japan goals, "ko" for Korea).
               Falls back to "en" if the specified language has no results.
    yield ("progress", text) | ("done", chunk_count)
    """
    name = node.get("name", "")
    desc = node.get("description", "")
    all_chunks: list[dict] = []

    # 1. Priority sources
    sources = get_matching_sources(name, goal_type)
    if sources:
        yield ("progress", f"Priority sources: {len(sources)} found...")
        for s in sources:
            if is_url_cached(s["url"]):
                yield ("progress", f"⏩ cached: {s['name']}")
                continue
            yield ("progress", f"fetching: {s['name']}...")
            text = fetch_text(s["url"])
            if text:
                cat    = s.get("category", "general")
                ttl    = s.get("ttl_days", None)
                chunks = chunk_text(text, s["url"])
                store_chunks(chunks, category=cat, ttl_days=ttl)
                all_chunks.extend(chunks)
                yield ("progress", f"✓ {s['name']}: {len(chunks)} chunks")

    # 2. Wikipedia (use wiki_lang for geo-specific goals)
    if len(all_chunks) < MIN_CHUNKS:
        query = name if name else desc[:30]
        yield ("progress", f"searching Wikipedia ({wiki_lang}): {query}...")
        wiki_chunks = fetch_wikipedia(query, lang=wiki_lang)
        if wiki_chunks:
            store_chunks(wiki_chunks, category="concept", ttl_days=0)
            all_chunks.extend(wiki_chunks)
            yield ("progress", f"✓ Wikipedia ({wiki_lang}): {len(wiki_chunks)} chunks")
        else:
            yield ("progress", f"Wikipedia ({wiki_lang}): no results")

    # 3. DuckDuckGo
    if len(all_chunks) < MIN_CHUNKS:
        queries = generate_queries(name, goal_type)
        yield ("progress", f"searching web (DuckDuckGo)...")
        for q in queries[:2]:
            urls = search_urls(q, max_results=2)
            for url in urls:
                if is_url_cached(url):
                    continue
                text = fetch_text(url)
                if text:
                    cat    = infer_category(url)
                    chunks = chunk_text(text, url)
                    store_chunks(chunks, category=cat)
                    all_chunks.extend(chunks)
                    yield ("progress", f"✓ {url[:50]} [{cat}]: {len(chunks)} chunks")
            if len(all_chunks) >= MIN_CHUNKS:
                break

    yield ("done", len(all_chunks))


def crawl_node_smart(node: dict, goal_type: str = "general",
                     verbose: bool = False, wiki_lang: str = "zh") -> int:
    """Synchronous wrapper around crawl_node_smart_stream. Returns the number of chunks added."""
    count = 0
    for ev_type, ev_data in crawl_node_smart_stream(node, goal_type, wiki_lang=wiki_lang):
        if ev_type == "progress" and verbose:
            print(f"  {ev_data}")
        elif ev_type == "done":
            count = ev_data
    return count

    if verbose:
        print(f"  ✅ stored {len(all_chunks)} chunks total")
    return len(all_chunks)


def query_raw_chunks(node_embedding: list[float], n: int = 5) -> list[dict]:
    if raw_chunks.count() == 0:
        return []
    now = datetime.now().isoformat()
    results = raw_chunks.query(
        query_embeddings=[node_embedding],
        n_results=min(n * 2, raw_chunks.count())   # Fetch more than needed so after filtering we still have n results
    )
    chunks = []
    for i, chunk_id in enumerate(results["ids"][0]):
        meta       = results["metadatas"][0][i]
        expires_at = meta.get("expires_at", "")
        # Filter out expired data (empty expires_at = never expires)
        if expires_at and expires_at < now:
            continue
        chunks.append({
            "id":          chunk_id,
            "text":        _fix_mojibake(results["documents"][0][i]),
            "source":      meta.get("source", ""),
            "source_name": meta.get("source_name", ""),
            "category":    meta.get("category", "general"),
            "expires_at":  expires_at,
            "distance":    results["distances"][0][i],
        })
        if len(chunks) >= n:
            break
    return chunks


# ── Legacy API (backward compatibility) ─────────────────────────────────────────────────────

def crawl_node(node_id: str, verbose: bool = True) -> int:
    node = get_node(node_id)
    if not node:
        return 0
    return crawl_node_smart(node, verbose=verbose)


def enrich_node_from_rag(node_id: str, verbose: bool = True) -> int:
    node = get_node(node_id)
    if not node:
        return 0
    node_vec = embed(node["description"][:500])
    candidates = query_raw_chunks(node_vec, n=8)
    relevant = [c for c in candidates if c["distance"] < RAG_THRESHOLD]
    if not relevant:
        return 0
    new_knowledge = "\n\n".join(
        f"[source: {c['source'][:40]}]\n{c['text']}" for c in relevant
    )
    updated = node["description"] + "\n\n---\n\n" + new_knowledge
    upsert_node(node_id, node["name"], updated, embed(updated[:2000]))
    if verbose:
        print(f"  {node['name']}: enriched with {len(relevant)} chunks")
    return len(relevant)


def crawl_and_enrich(node_id: str, verbose: bool = True):
    crawl_node(node_id, verbose)
    enrich_node_from_rag(node_id, verbose)
