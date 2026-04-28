"""
Ragraphe Web API
Start: uvicorn ragraphe.api.main:app --reload --port 7860
"""
import re
import uuid
import math
import json as _json
import threading
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Local upload directory
FILES_DIR = Path(__file__).parent.parent.parent / "data" / "files"
FILES_DIR.mkdir(parents=True, exist_ok=True)

import os
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent.parent / ".env")

from ragraphe.core.path_planner import generate_skeleton_stream, plan_path
from ragraphe.core.visualizer import build_graph_data, node_to_vis, edge_to_vis, _is_day_based
from ragraphe.core.crawler import query_raw_chunks, RAG_THRESHOLD, crawl_node_smart, delete_chunks_by_source, list_chunk_sources
from ragraphe.config.freshness import detect_topic, needs_realtime, get_topic_name

# chat + embed backend: ollama (default) or gemini (set LLM_BACKEND=gemini)
_LLM_BACKEND = os.getenv("LLM_BACKEND", "ollama").lower()
if _LLM_BACKEND == "gemini":
    from ragraphe.llm.gemini_client import chat, embed, chat_quick as _chat_quick, CHAT_MODEL as _GEMINI_MODEL
    print(f"[LLM] Backend: Gemini ({_GEMINI_MODEL}), embed: gemini-embedding-2")
    _LLM_LABEL = f"Gemini {_GEMINI_MODEL.replace('gemini-','').replace('-preview','')}"
else:
    from ragraphe.llm.ollama_client import chat, embed
    _chat_quick = chat   # Ollama: no-retry variant is same as chat
    from ragraphe.llm.ollama_client import CHAT_MODEL as _OLLAMA_MODEL
    print(f"[LLM] Backend: Ollama ({_OLLAMA_MODEL}), embed: nomic-embed-text")
    _LLM_LABEL = f"Ollama ({_OLLAMA_MODEL})"

from ragraphe.db.store import (
    init_db, get_profile, upsert_profile, record_goal, get_recent_goals,
    add_priority_source, list_priority_sources, delete_priority_source,
    is_url_cached, mark_url_crawled, list_crawled_urls,
    get_og_image_cache, set_og_image_cache,
    save_session, load_all_sessions, list_sessions, delete_session,
    upsert_user_knowledge, get_user_knowledge,
    record_node_feedback, get_recent_bad_nodes,
    update_node_stats, get_popular_nodes,
)

init_db()

_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

app = FastAPI()
app.mount("/files",  StaticFiles(directory=str(FILES_DIR)),   name="files")
app.mount("/static", StaticFiles(directory=str(_FRONTEND_DIR)), name="static")

# session_id → {
#   "goal", "user_id", "context_parts", "skeleton",
#   "goal_type", "graph_mode", "messages"
# }
sessions: dict[str, dict] = load_all_sessions()

# Limit concurrent LLM filter calls in node_resources (prevent rate-limit 503 storm)
# Satellite requests fire AFTER chat/plan completes, so they don't compete with main LLM calls.
# Semaphore(4) allows 4 concurrent filter calls without overwhelming the API.
_llm_filter_sem = threading.Semaphore(4)

# Per-session lock for satellite claim section: prevents concurrent node_resources calls
# from racing to claim the same source URL (setdefault alone doesn't prevent building duplicate candidates).
_session_sat_locks: dict[str, threading.Lock] = {}

# Country-level keywords that trigger geographic relevance filtering
_GOAL_COUNTRY_RE = re.compile(
    r"(日本|台灣|台湾|韓國|한국|中國|中国|美國|美国|歐洲|英國|法國|德國|義大利|澳洲|紐西蘭|泰國|越南|印度|東南亞|北美|南美)"
)

# Country → Wikipedia language code for targeted crawl
# Chinese goals default to "zh" (handled by crawl_node_smart's default)
_COUNTRY_WIKI_LANG: dict[str, str] = {
    "日本": "ja",
    "韓國": "ko", "한국": "ko",
    "法國": "fr",
    "德國": "de",
    "義大利": "it",
    "泰國": "th",
    "越南": "vi",
    "美國": "en", "英國": "en", "澳洲": "en", "紐西蘭": "en", "北美": "en", "南美": "en",
    "歐洲": "en",
    "印度": "hi",
}


def _save_session(session_id: str):
    """Asynchronously persist session + update user knowledge memory (non-blocking for SSE stream)."""
    data = sessions.get(session_id)
    if not data:
        return
    def _worker():
        save_session(session_id, data)
        # Write done/skip nodes into user_knowledge
        user_id = data.get("user_id", "anonymous")
        nodes   = data.get("nodes", {})
        concepts = [
            {"concept": n["name"], "status": n["status"]}
            for n in nodes.values()
            if n.get("status") in ("done", "skip") and n.get("name")
        ]
        if concepts:
            upsert_user_knowledge(user_id, concepts)
        # Accumulate cross-session popularity for done nodes
        done_names = [n["name"] for n in nodes.values() if n.get("status") == "done" and n.get("name")]
        if done_names:
            update_node_stats(done_names)
    threading.Thread(target=_worker, daemon=True).start()


# ── Models ──────────────────────────────────────────────────────────────────

_LANG_MAP = {
    "zh-TW": "Traditional Chinese",
    "en":    "English",
    "ja":    "Japanese",
}


class StartRequest(BaseModel):
    goal:    str = ""
    user_id: str = "anonymous"
    lang:    str = "zh-TW"


class MessageRequest(BaseModel):
    session_id: str
    text:       str
    lang:       str = "zh-TW"


class ExpandRequest(BaseModel):
    session_id: str
    node_id:    str


class EditRequest(BaseModel):
    session_id: str
    text:       str


class SkipRequest(BaseModel):
    session_id: str
    node_id:    str


class ExportPromptRequest(BaseModel):
    session_id: str


class NodeResourcesRequest(BaseModel):
    session_id: str
    node_id:    str


class ProfileRequest(BaseModel):
    user_id:    str
    name:       str = ""
    background: str = ""
    skills:     list[str] = []


class SourceRequest(BaseModel):
    name:       str
    url:        str
    goal_types: list[str] = []
    keywords:   list[str] = []
    vendor_id:  str = ""
    priority:   int = 100
    category:   str = "general"
    ttl_days:   int = 30


class FeedbackRequest(BaseModel):
    session_id: str
    node_id:    str
    node_name:  str
    feedback:   str  # "good" | "bad"


class KnowledgeDeleteRequest(BaseModel):
    source: str


class KnowledgeCrawlRequest(BaseModel):
    topic:     str
    goal_type: str = "general"


class KnowledgeURLRequest(BaseModel):
    url:        str
    source:     str = ""
    session_id: str = ""


class KnowledgeTextRequest(BaseModel):
    text:       str
    source:     str = "手動輸入"
    session_id: str = ""


class KnowledgeJSONLRequest(BaseModel):
    content:    str
    source:     str = "匯入"
    session_id: str = ""


class KnowledgeAskRequest(BaseModel):
    query:      str
    n:          int = 8     # chunks to retrieve
    lang:       str = "en"  # answer language


_LANG_TO_DB: dict[str, str] = {"en": "en", "zh-TW": "zh", "ja": "ja"}
_ALL_FILTER_LANGS = ["en", "zh", "ja"]


# ── Helpers ─────────────────────────────────────────────────────────────────

_TYPE_LABELS = {
    "travel": "旅行", "learning": "學習", "project": "專案",
    "research": "研究", "prompt": "Prompt 設計", "general": "一般目標",
}


def _sse(data: dict) -> str:
    """Format a dict as an SSE event string."""
    return f"data: {_json.dumps(data, ensure_ascii=False)}\n\n"



def _cosine_dist(a: list, b: list) -> float:
    """Cosine distance (0=identical, 2=opposite)"""
    dot  = sum(x * y for x, y in zip(a, b))
    na   = math.sqrt(sum(x * x for x in a))
    nb   = math.sqrt(sum(x * x for x in b))
    return 1.0 - dot / (na * nb) if na and nb else 1.0


def _interpolate_bridge_rag(
    cluster_a_ids: list, cluster_b_ids: list,
    embeddings: dict, n_probes: int = 3, n_results: int = 3,
    filter_langs: list[str] | None = None,
    filter_sources: list[str] | None = None,
) -> list[dict]:
    """
    Centroid interpolation bridge discovery.
    Compute centroids of two node clusters, sample n_probes points along the
    line between them, and query ChromaDB at each point.
    Returns deduplicated chunks most likely to represent bridging knowledge.
    """
    import numpy as np

    embs_a = [embeddings[nid] for nid in cluster_a_ids if nid in embeddings]
    embs_b = [embeddings[nid] for nid in cluster_b_ids if nid in embeddings]
    if not embs_a or not embs_b:
        return []

    centroid_a = np.mean(embs_a, axis=0)
    centroid_b = np.mean(embs_b, axis=0)

    seen_sources: set[str] = set()
    all_chunks: list[dict] = []

    ts = [i / (n_probes + 1) for i in range(1, n_probes + 1)]  # e.g. [0.25, 0.5, 0.75]
    for t in ts:
        probe = ((1 - t) * centroid_a + t * centroid_b).tolist()
        try:
            chunks = query_raw_chunks(probe, n=n_results, filter_langs=filter_langs, filter_sources=filter_sources)
            for c in chunks:
                key = c.get("source", "") + c.get("text", "")[:80]
                if key not in seen_sources:
                    seen_sources.add(key)
                    all_chunks.append(c)
        except Exception:
            pass

    # Sort by distance (closest to any probe point = most relevant bridge)
    return all_chunks[:6]


def _compute_semantic_layout(embeddings: dict, nodes: dict) -> dict:
    """
    Use MDS to project all node embeddings into 2D semantic coordinates.
    Close distance = semantically related; far distance = intermediate knowledge needed.

    embeddings: {node_id: list[float]}
    nodes:      {node_id: node_dict}
    Returns:    {node_id: {"x": float, "y": float, "cluster": int}}
    """
    import numpy as np

    valid_ids = [nid for nid in nodes if nid in embeddings and embeddings[nid]]
    n = len(valid_ids)
    if n == 0:
        return {}
    if n == 1:
        return {valid_ids[0]: {"x": 0.0, "y": 0.0, "cluster": 0}}

    vecs = np.array([embeddings[nid] for nid in valid_ids], dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    vecs_norm = vecs / np.maximum(norms, 1e-8)

    # Cosine distance matrix
    sim = vecs_norm @ vecs_norm.T
    dist_matrix = np.clip(1.0 - sim, 0.0, 2.0).astype(np.float64)

    SCALE = 350  # canvas units

    if n == 2:
        d = float(dist_matrix[0, 1])
        positions = [(-d * SCALE, 0.0), (d * SCALE, 0.0)]
    else:
        from sklearn.manifold import MDS
        mds = MDS(n_components=2, dissimilarity="precomputed",
                  random_state=42, normalized_stress="auto", n_init=4)
        coords = mds.fit_transform(dist_matrix)
        std = coords.std()
        if std > 0:
            coords = coords / std * SCALE
        positions = [(float(coords[i, 0]), float(coords[i, 1])) for i in range(n)]

    # K-means clustering (determines color cluster)
    k = max(1, min(4, n // 2))
    try:
        from sklearn.cluster import KMeans
        km = KMeans(n_clusters=k, random_state=42, n_init="auto")
        clusters = km.fit_predict(vecs_norm).tolist()
    except Exception:
        clusters = [0] * n

    return {
        valid_ids[i]: {
            "x":       positions[i][0],
            "y":       positions[i][1],
            "cluster": int(clusters[i]),
        }
        for i in range(n)
    }


def _find_duplicate(new_emb: list, embeddings: dict, exclude_ids: set | None = None) -> str | None:
    """
    If the new node's embedding is very close to an existing node (distance < NODE_DEDUP_THRESHOLD),
    return the existing node's ID (the nearest one); otherwise return None.
    Used for cross-language synonym node merging: new replaces old.
    """
    if not new_emb:
        return None
    best_id, best_dist = None, NODE_DEDUP_THRESHOLD
    for nid, emb in embeddings.items():
        if exclude_ids and nid in exclude_ids:
            continue
        if not emb:
            continue
        d = _cosine_dist(new_emb, emb)
        if d < best_dist:
            best_dist = d
            best_id = nid
    return best_id


def _all_filled(nodes: dict) -> bool:
    """Graph completion condition: all nodes are non-unknown and there is at least one node. deferred/skip do not block completion."""
    if not nodes:
        return False
    return all(n.get("status") not in ("unknown",) for n in nodes.values())


def _filter_plan_nodes(candidates: list[dict], goal: str, existing_nodes: dict) -> list[dict]:
    """
    LLM-Plan node quality filter (hard code-layer rules, not prompt-dependent):
    1. Name length: 2-12 chars
    2. Name must not be a substring of the goal string (avoid overly generic nodes like "travel" in "I want to travel to Japan")
    3. Fuzzy deduplication: if new name is contained by or contains any existing node name → skip
    4. Keep at most 3 (prefer fewer, higher quality)
    """
    existing_names = {n["name"] for n in existing_nodes.values()}
    result = []
    for nn in candidates:
        name = nn.get("name", "").strip()
        if not name:
            continue
        # Rule 1: length
        if len(name) < 2 or len(name) > 12:
            continue
        # Rule 2: name is a substring of the goal (too generic)
        if name in goal:
            continue
        # Rule 3: name is identical, or new name is a pure subset of an existing name (e.g. "food" covered by "Tokyo food")
        # Reverse is not filtered: "Tokyo accommodation" is more specific than "accommodation" and should be kept
        if any(name == en or (name in en and len(name) <= len(en) - 2) for en in existing_names):
            continue
        result.append(nn)
        if len(result) >= 3:   # Rule 4: hard cap
            break
    return result


def _specificity_score(new_emb: list, existing_embs: dict) -> float:
    """
    Embedding specificity score: stdev of cosine distances to all existing nodes.
    Generic nodes (e.g. "food", "transport") have uniform distances to all nodes → low stdev;
    Specific nodes (e.g. "Kyoto Kinkakuji") are close to a few nodes and far from others → high stdev.
    Below 0.08 is considered overly generic and should be discarded.
    """
    import statistics
    if not existing_embs or len(existing_embs) < 2:
        return 1.0   # Too few samples; skip filtering
    dists = [_cosine_dist(new_emb, e) for e in existing_embs.values()]
    return statistics.stdev(dists)


# ── Node / Edge visualization helpers ───────────────────────────────────────

EDGE_THRESHOLD      = 0.38   # cosine dist < this value creates an edge (relaxed from 0.28: allows topic-adjacent connections, e.g. 月份↔路線規劃)
NODE_DEDUP_THRESHOLD = 0.22  # semantically near-identical (cross-language synonyms) → new node replaces old

_NODE_COLORS = {
    # status → (bg, border, font)
    "todo":     {"bg": "#0f2744", "border": "#2563eb", "font": "#93c5fd"},  # blue: user mentioned
    "done":     {"bg": "#14532d", "border": "#22c55e", "font": "#4ade80"},  # green: connected
    "skip":     {"bg": "#1c1c1c", "border": "#374151", "font": "#4b5563"},  # grey: skipped
    "deferred": {"bg": "#1a1230", "border": "#7c3aed", "font": "#c4b5fd"},  # purple dashed: undecided
    # unknown is further subdivided by source (see _node_vis)
    "unknown":  {"bg": "#2d1a00", "border": "#f97316", "font": "#fb923c"},  # orange: AI conversation suggestion
}

# AI-detected knowledge gap bridge nodes (source=ai_planned) use a distinct color scheme
_BRIDGE_COLORS = {"bg": "#150d2b", "border": "#a855f7", "font": "#d8b4fe"}  # violet

def _node_vis(node: dict) -> dict:
    status = node.get("status", "todo")
    source = node.get("source", "user")

    # ai_planned (bridge) nodes: status is usually unknown, but visually use the violet color scheme
    if source == "ai_planned" and status == "unknown":
        sc = _BRIDGE_COLORS
        size      = 24   # Larger than regular nodes to emphasize "this is a knowledge gap"
        border_w  = 2
        border_dashes = [4, 3]   # Dashed border: "not yet filled in"
        glow_color = "#a855f7"
    elif source == "ai_suggested":
        sc = _NODE_COLORS.get(status, _NODE_COLORS["unknown"])
        size      = 17   # Smaller: conversation suggestion awaiting confirmation
        border_w  = 1
        border_dashes = False
        glow_color = sc["border"]
    else:
        sc = _NODE_COLORS.get(status, _NODE_COLORS["todo"])
        size      = 22
        border_w  = 2
        border_dashes = [6, 4] if status == "deferred" else False
        glow_color = sc["border"]

    return {
        "id":     node["id"],
        "label":  node["name"],
        "shape":  "dot",
        "size":   size,
        "borderWidth": border_w,
        "borderDashes": border_dashes,
        "color":  {"background": sc["bg"], "border": sc["border"]},
        "font":   {"color": sc["font"], "size": 13},
        "shadow": {"enabled": True, "color": glow_color, "size": 10, "x": 0, "y": 0},
        "hidden": False,
        "_status":     status,
        "_source":     source,
        "_exclusive":  node.get("exclusive", False),
        "_description":node.get("description", ""),
        "_reason":     node.get("reason", ""),
        "_children": [],
        "_parent": None,
        "_level": 1,
    }

def _edge_vis(edge: dict, nodes: dict) -> dict:
    fid = edge["from_id"]
    tid = edge["to_id"]
    fs  = nodes.get(fid, {}).get("status", "unknown")
    ts  = nodes.get(tid, {}).get("status", "unknown")
    active = (fs not in ("unknown",)) and (ts not in ("unknown",))
    is_bridge = edge.get("is_bridge", False)
    if is_bridge:
        # Bridge edge: orange dashed line, indicating "this is an AI-suggested knowledge bridge"
        return {
            "id":    edge["id"],
            "from":  fid, "to": tid,
            "dashes": [5, 5],
            "width":  1.5,
            "color":  {"color": "#f97316", "opacity": 0.7},
        }
    return {
        "id":    edge["id"],
        "from":  fid, "to": tid,
        "dashes": [6, 4] if not active else False,
        "width":  2.5 if active else 1.5,
        "color":  {"color": "#22c55e" if active else "#60a5fa",
                   "opacity": 0.85 if active else 0.65},
        "_is_parent": bool(edge.get("is_parent", False)),
    }

def _compute_new_edges(new_ids: list, embeddings: dict,
                       edge_set: set, nodes: dict,
                       max_per_node: int = 3) -> list:
    """
    For each new node, find the max_per_node semantically nearest neighbors and create edges (K-nearest).
    Avoids threshold-based O(N²) spider-web graphs.
    Neighbors in the same cluster are prioritized (if session already has cluster information).
    """
    new_edges = []
    all_ids = list(embeddings.keys())
    node_clusters = {nid: nodes[nid].get("_cluster", -1) for nid in nodes}

    for nid in new_ids:
        if nid not in embeddings:
            continue
        emb_a = embeddings[nid]
        my_cluster = node_clusters.get(nid, -1)

        candidates = []
        fallback_candidates = []   # Not threshold-constrained; used as a guaranteed fallback
        for oid in all_ids:
            if oid == nid:
                continue
            key = frozenset([nid, oid])
            if key in edge_set:
                continue
            emb_b = embeddings.get(oid)
            if not emb_b:
                continue
            dist = _cosine_dist(emb_a, emb_b)
            same_cluster = (my_cluster >= 0 and node_clusters.get(oid, -1) == my_cluster)
            sort_key = dist * (0.7 if same_cluster else 1.0)
            fallback_candidates.append((dist, oid))
            if dist < EDGE_THRESHOLD:
                candidates.append((sort_key, dist, oid))

        candidates.sort()
        added = 0
        for _, dist, oid in candidates[:max_per_node]:
            key = frozenset([nid, oid])
            edge_set.add(key)
            new_edges.append({"id": f"{nid}→{oid}", "from_id": nid, "to_id": oid})
            added += 1

        # Fallback: if node has no edges, force-connect to nearest neighbor (prevent isolated components from drifting)
        if added == 0 and fallback_candidates:
            fallback_candidates.sort()
            _, oid = fallback_candidates[0]
            key = frozenset([nid, oid])
            if key not in edge_set:
                edge_set.add(key)
                new_edges.append({"id": f"{nid}→{oid}", "from_id": nid, "to_id": oid})

    return new_edges


def _ensure_connected(nodes: dict, embeddings: dict, edge_set: set) -> list:
    """
    Detect disconnected components among main nodes and bridge them with
    minimum-distance cross-component edges (Kruskal-style MST connectivity).
    Resource/satellite nodes are excluded — they are intentionally detached.
    Returns new edges to be yielded to the frontend.
    """
    main_ids = [
        nid for nid, n in nodes.items()
        if n.get("source") != "resource" and nid in embeddings
    ]
    if len(main_ids) < 2:
        return []

    # ── Union-Find ────────────────────────────────────────────────────
    parent = {nid: nid for nid in main_ids}

    def _find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(x, y):
        parent[_find(x)] = _find(y)

    for key in edge_set:
        ids = list(key)
        if len(ids) == 2 and ids[0] in parent and ids[1] in parent:
            _union(ids[0], ids[1])

    # ── Group into components ─────────────────────────────────────────
    comp_map: dict[str, list[str]] = {}
    for nid in main_ids:
        comp_map.setdefault(_find(nid), []).append(nid)
    comp_list = list(comp_map.values())

    if len(comp_list) <= 1:
        return []   # Already one connected component

    # ── Merge components by minimum embedding distance ────────────────
    new_edges: list[dict] = []
    while len(comp_list) > 1:
        best_dist, best_a, best_b, best_i, best_j = float("inf"), None, None, 0, 1
        for i, ca in enumerate(comp_list):
            for j, cb in enumerate(comp_list):
                if j <= i:
                    continue
                for a in ca:
                    for b in cb:
                        key = frozenset([a, b])
                        if key in edge_set:
                            continue
                        dist = _cosine_dist(embeddings[a], embeddings[b])
                        if dist < best_dist:
                            best_dist, best_a, best_b, best_i, best_j = dist, a, b, i, j

        if best_a is None:
            break   # No valid pair found (shouldn't happen)

        key = frozenset([best_a, best_b])
        edge_set.add(key)
        eid = f"{best_a}→{best_b}"
        new_edges.append({"id": eid, "from_id": best_a, "to_id": best_b})
        # Merge the two components
        merged = comp_list[best_i] + comp_list[best_j]
        comp_list = [c for k, c in enumerate(comp_list) if k != best_i and k != best_j]
        comp_list.append(merged)

    return new_edges


# ── LLM Prompts ──────────────────────────────────────────────────────────────

# LLM-ChatExtract: conversation reply + user concept extraction + suggestions, merged into a single LLM call
_CHAT_EXTRACT_SYSTEM = (
    "You are a friendly conversational assistant and concept extractor. "
    "Output strict JSON only, no markdown."
)
_CHAT_EXTRACT_PROMPT = """Language: {reply_lang}
Goal (may be empty — that's OK, just explore freely): {goal}
Conversation history:
{history}
User: "{message}"

Existing node names: {existing_names}
{known_concepts_block}
Do ALL four tasks:

Task A — Reply: 2-3 sentences in {reply_lang}.
- First: directly engage with what the user just said — acknowledge, add a relevant fact, or connect it to the goal.
- Then (optional): suggest how this topic might relate to the goal or other concepts IF non-obvious.
- Do NOT just ask "tell me more" or end with a generic open question every time. Only ask a follow-up question if it would genuinely help clarify direction.

Task B — user_concepts: Extract every concept the user EXPLICITLY mentioned (not implied).
- name: short, 2-8 chars/letters. Use {node_lang} for general concepts; keep original spelling for proper nouns, tools, or technical terms (e.g. "Docker", "Python", "AWS", "React")
- parent_name: EXACT existing node name if this concept is clearly related to one in the current conversation context, else null.
  Use parent_name broadly — not just for strict "is-a" hierarchies but for any meaningful connection:
  e.g. existing "日本", user says "京都 and 大阪" → parent_name: "日本" for each
  e.g. existing "登山健行", user says "月份" (in context of planning a hike) → parent_name: "登山健行"
  e.g. existing "路線規劃", user says "出發時間" → parent_name: "路線規劃"

Task C — ai_suggestions: List specific options/items YOUR REPLY mentions (so user sees them visually).
- exclusive: true if alternatives (pick one), false if all relevant
- parent_name: EXACT existing name or null

Task D — Decision context (only when user makes a clear choice among alternatives):
- decision_reason: 1 short phrase explaining WHY the user chose this option (e.g. "想看寺廟"). null if no clear choice.
- deferred_nodes: names of nodes the user explicitly said "not sure yet" / "maybe later" / "undecided" about. [] if none.

Output JSON:
{{
  "reply": "...",
  "user_concepts": [
    {{"name": "...", "parent_name": "existing or null", "description": "max 20 chars"}}
  ],
  "ai_suggestions": [
    {{"name": "...", "parent_name": "existing or null", "exclusive": true, "description": "max 20 chars"}}
  ],
  "decision_reason": null,
  "deferred_nodes": []
}}
user_concepts and ai_suggestions can be [].
Output JSON only."""

_SEED_EXPAND_SYSTEM = (
    "You are a knowledge prerequisite finder. Given a concept, list what a learner must know first. "
    "Output strict JSON only, no markdown."
)

_SEED_EXPAND_PROMPT = """Node language: {node_lang}
Goal: {goal}
New concept: "{concept_name}" — {concept_desc}
Existing nodes (do NOT repeat these): {existing_names}

List 2-4 prerequisite concepts a learner needs BEFORE understanding "{concept_name}".
Rules:
- Only genuinely necessary prerequisites (not loosely related topics)
- Names: 2-8 chars in {node_lang}, specific and concrete
- Skip any concept already in existing nodes
- If no clear prerequisites exist, return empty list

Output JSON:
{{"prerequisites": [{{"name": "...", "description": "max 20 chars"}}]}}
Output JSON only."""

_PLANNER_SYSTEM = (
    "You are a creative knowledge connector. Your job: given two topic clusters the user is exploring, "
    "find the hidden concept that bridges them. Think like a curious teacher who loves unexpected connections. "
    "Output strict JSON only, no markdown."
)

_PLANNER_PROMPT = """Node language: {node_lang}
User's goal: {goal}

The user has been exploring these topic clusters:
{cluster_summary}

Most disconnected node pairs across clusters (no edge yet):
{disconnected_pairs}

All current nodes (for deduplication):
{existing_nodes}
{rag_context_section}
{bad_nodes_hint}
Your task: find 1-3 bridge concepts that meaningfully connect nodes from DIFFERENT clusters.

What makes a great bridge concept:
- Clearly relates to BOTH sides (not just one)
- Reveals an "unknown unknown" — something the user didn't know they needed
- Concrete and specific (e.g. "東京貓咖啡廳" beats "關係"; "登山月份" beats "時間")
- Not already in the existing nodes

Rules:
- Bridge names: {node_lang}, 2-8 chars
- Max 3 bridge nodes total
- You MUST suggest at least 1 bridge — the topics are always connectable if you think creatively
- "connects" must use EXACT names from existing nodes

Output JSON:
{{
  "bridge_nodes": [
    {{
      "name": "...",
      "description": "why it bridges (max 20 chars)",
      "connects": ["exact_name_a", "exact_name_b"]
    }}
  ]
}}
Output JSON only."""


# ── Graph expansion helper ───────────────────────────────────────────────────

def _expand_by_location_siblings(concepts: list[dict], nodes: dict, edges: list) -> list[dict]:
    """
    Code-based location expansion (no extra LLM call needed):
    - Find sibling groups on the graph with 2+ todo nodes at the same level (sharing the same is_parent parent node)
    - For each "generic concept" (parent_name=None and name contains no sibling name),
      automatically expand into sibling × concept combinations, setting parent_name to the corresponding sibling
    - Concepts that already have a parent_name or whose name already contains a location name pass through unchanged
    """
    # Build parent_id → [child todo nodes]
    parent_to_children: dict[str, list[dict]] = {}
    for edge in edges:
        if not edge.get("is_parent"):
            continue
        pid = edge["from_id"]
        cid = edge["to_id"]
        child = nodes.get(cid)
        if child and child.get("status") == "todo":
            parent_to_children.setdefault(pid, []).append(child)

    # Extract groups with 2+ todo children (candidates for location sibling groups)
    sibling_groups = [children for children in parent_to_children.values()
                      if len(children) >= 2]

    if not sibling_groups:
        return concepts   # No expandable groups → return as-is

    # Set of all sibling names, used to check whether a concept already contains a location name
    all_sibling_names = {s["name"] for g in sibling_groups for s in g}
    existing_node_names = {n["name"] for n in nodes.values()}

    result: list[dict] = []
    for c in concepts:
        name        = c.get("name", "")
        parent_name = c.get("parent_name")
        desc        = c.get("description", "")

        # Already has parent_name or name itself contains a location → pass through
        if parent_name or any(sn in name for sn in all_sibling_names):
            result.append(c)
            continue

        # Generic concept → expand (using the first and largest sibling group)
        target_group = max(sibling_groups, key=len)
        expanded_any = False
        for sib in target_group:
            expanded_name = f"{sib['name']}{name}"
            if expanded_name not in existing_node_names:
                result.append({
                    "name":        expanded_name,
                    "parent_name": sib["name"],
                    "description": desc,
                })
                expanded_any = True
        # If all expanded versions already exist, keep the original concept
        if not expanded_any:
            result.append(c)

    return result


# ── Core message processor ───────────────────────────────────────────────────

def _process_message(session_id: str, user_text: str):
    """
    Core processing generator:
    1. LLM-ChatExtract (conversation + extraction merged into a single call)
    2. Code expansion: generic concepts × sibling location groups
    3. RAG query
    4. LLM-Plan (planner) → supplement necessary nodes (unknown)
    5. Create proximity edges + parent resolve
    6. Completion check
    Yields SSE event strings (excluding the final done event).
    """
    session    = sessions[session_id]
    goal       = session["goal"]
    lang       = session.get("lang", "zh-TW")
    reply_lang = _LANG_MAP.get(lang, "Traditional Chinese")
    node_lang  = reply_lang
    nodes: dict      = session["nodes"]
    embeddings: dict = session["embeddings"]
    edge_set: set    = session["edge_set"]
    edges: list      = session["edges"]
    topic: str       = session.get("topic", "default")

    # ── Realtime web search (triggered by temporal keywords like "latest", "today", "now") ──────
    realtime_context = ""
    if needs_realtime(topic, user_text):
        yield _sse({"type": "realtime_search", "query": user_text[:60]})
        try:
            from ddgs import DDGS as _DDGS
            _rt_query = f"{user_text} {goal}"[:120]
            with _DDGS() as _ddgs:
                _rt_results = list(_ddgs.text(_rt_query, max_results=5))
            realtime_context = "\n".join(
                f"- {r.get('title', '')} ({r.get('href', '')[:60]}): {r.get('body', '')[:200]}"
                for r in _rt_results if r.get("body")
            )
            yield _sse({"type": "realtime_done", "count": len(_rt_results)})
            print(f"[realtime] {len(_rt_results)} results for: {_rt_query[:60]}", flush=True)
        except Exception as _e:
            print(f"[realtime] search failed: {_e}", flush=True)
            yield _sse({"type": "realtime_done", "count": 0})

    # ── Step 4: Snapshot current state before processing (for undo), keep up to 5 rounds ──────
    import copy as _copy
    _snapshot = {
        "nodes":      _copy.deepcopy(nodes),
        "edges":      _copy.deepcopy(edges),
        "embeddings": {k: list(v) for k, v in embeddings.items()},
        "messages":   list(session.get("messages", [])),
        "decisions":  _copy.deepcopy(session.get("decisions", [])),
    }
    _snaps = session.setdefault("snapshots", [])
    _snaps.append(_snapshot)
    if len(_snaps) > 5:
        _snaps.pop(0)

    from datetime import datetime as _dtm
    session["messages"].append({"role": "user", "content": user_text, "ts": _dtm.now().isoformat()})

    # Keep only the most recent 12 messages (6 rounds) as LLM context to prevent prompt bloat on long conversations
    _ctx_msgs = session["messages"][:-1][-12:]
    history_text = "\n".join(
        f"{'AI' if m['role'] == 'assistant' else 'User'}: {m['content']}"
        for m in _ctx_msgs
    ) or "(none)"

    existing_names_json = _json.dumps(
        [n["name"] for n in nodes.values()], ensure_ascii=False
    ) if nodes else "[]"

    # ── Cross-session knowledge memory: load user's known concepts ──────────
    user_id = session.get("user_id", "anonymous")
    _prior_knowledge = get_user_knowledge(user_id)
    _done_concepts = [k["concept"] for k in _prior_knowledge if k["status"] == "done"]
    _skip_concepts = [k["concept"] for k in _prior_knowledge if k["status"] == "skip"]
    if _done_concepts or _skip_concepts:
        _known_lines = []
        if _done_concepts:
            _known_lines.append(f"User has already mastered: {', '.join(_done_concepts[:20])}")
        if _skip_concepts:
            _known_lines.append(f"User explicitly skipped (do not suggest): {', '.join(_skip_concepts[:10])}")
        known_concepts_block = "\n" + "\n".join(_known_lines) + "\nDo NOT re-add these as new nodes.\n"
    else:
        known_concepts_block = ""

    # ── P4 speculative planning: launch LLM-Plan concurrently with LLM-ChatExtract (using previous graph snapshot) ──
    # Snapshot graph state for Thread B (not affected by Thread A writes)
    snap_nodes = {nid: dict(n) for nid, n in nodes.items()}

    ce_result:   dict = {}   # Thread A — ChatExtract result
    plan_result: dict = {}   # Thread B — Plan result

    # ── Thread A: LLM-ChatExtract ─────────────────────────────────────
    def _run_chat_extract():
        _reply           = "（AI 暫時無法回應，請稍後再試）"
        _off_topic       = False
        _raw_concepts:   list = []
        _suggested_raw:  list = []
        _decision_reason: str | None = None
        _deferred_names:  list = []
        try:
            _ce_prompt = _CHAT_EXTRACT_PROMPT.format(
                reply_lang=reply_lang, node_lang=node_lang,
                goal=goal, history=history_text,
                message=user_text, existing_names=existing_names_json,
                known_concepts_block=known_concepts_block,
            )
            if realtime_context:
                _ce_prompt += (
                    f"\n\nREAL-TIME WEB SEARCH RESULTS (fetched just now — use these for current facts):\n"
                    f"{realtime_context}\n"
                    f"Prioritize these results when answering questions about current prices, schedules, or recent events."
                )
            raw = chat(
                system=_CHAT_EXTRACT_SYSTEM,
                messages=[{"role": "user", "content": _ce_prompt}],
            )
            mx = re.search(r'\{[\s\S]+\}', raw or "")
            if mx:
                parsed = _json.loads(mx.group())
                _off_topic       = bool(parsed.get("off_topic", False))
                _reply           = (parsed.get("reply") or "").strip() or _reply
                # Always extract concepts regardless of off_topic — seemingly unrelated topics
                # may be intentionally building toward future connections.
                _raw_concepts    = parsed.get("user_concepts", [])
                _suggested_raw   = parsed.get("ai_suggestions", [])
                _decision_reason = parsed.get("decision_reason") or None
                _deferred_names  = [d for d in parsed.get("deferred_nodes", []) if d]
            else:
                _reply = (raw or "").strip() or _reply
        except Exception as _e:
            print(f"[ChatExtract error] {_e}")
            ce_result["error"] = str(_e)
            _reply = f"⚠️ {type(_e).__name__}: {_e}"
        ce_result.update({
            "off_topic":       _off_topic,
            "reply":           _reply,
            "raw_concepts":    _raw_concepts,
            "suggested_raw":   _suggested_raw,
            "decision_reason": _decision_reason,
            "deferred_names":  _deferred_names,
        })

    # ── Thread B: RAG query + LLM-Plan (using snapshot, parallel with Thread A) ────
    def _run_plan_speculative():
        import time as _time
        import numpy as np
        _rag_ctx = ""
        _parsed2 = {}
        _t0 = _time.time()

        snap_embs = {nid: embeddings.get(nid) for nid in snap_nodes if embeddings.get(nid)
                     and snap_nodes[nid].get("source") != "resource"}
        snap_main_ids = list(snap_embs.keys())
        snap_edge_set = set(edge_set)

        if len(snap_main_ids) < 3:
            plan_result.update({"parsed": {}, "rag_context": "", "top_pairs": [],
                                "interp_chunks": 0, "cluster_count": 0, "disconnected": False})
            return

        # ── 1. Detect disconnected components (union-find) ─────────────
        parent = {nid: nid for nid in snap_main_ids}
        def _uf_find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]; x = parent[x]
            return x
        def _uf_union(x, y):
            parent[_uf_find(x)] = _uf_find(y)

        for key in snap_edge_set:
            ids = list(key)
            if len(ids) == 2 and ids[0] in parent and ids[1] in parent:
                _uf_union(ids[0], ids[1])

        components: dict[str, list[str]] = {}
        for nid in snap_main_ids:
            components.setdefault(_uf_find(nid), []).append(nid)

        is_disconnected = len(components) > 1
        print(f"[P4] components={len(components)}, disconnected={is_disconnected}", flush=True)

        if not is_disconnected:
            # Graph is already connected — skip bridge planning this round
            plan_result.update({"parsed": {}, "rag_context": "", "top_pairs": [],
                                "interp_chunks": 0, "cluster_count": len(components),
                                "disconnected": False})
            return

        # ── 2. Find farthest component pair by centroid distance ────────
        comp_list = list(components.values())
        best_dist, best_ca, best_cb = -1.0, comp_list[0], comp_list[1]

        for ci in range(len(comp_list)):
            for cj in range(ci + 1, len(comp_list)):
                ids_i, ids_j = comp_list[ci], comp_list[cj]
                embs_i = [snap_embs[n] for n in ids_i if n in snap_embs]
                embs_j = [snap_embs[n] for n in ids_j if n in snap_embs]
                if not embs_i or not embs_j:
                    continue
                cent_i = np.mean(embs_i, axis=0)
                cent_j = np.mean(embs_j, axis=0)
                d = _cosine_dist(cent_i.tolist(), cent_j.tolist())
                if d > best_dist:
                    best_dist, best_ca, best_cb = d, ids_i, ids_j

        names_a = [snap_nodes[nid]["name"] for nid in best_ca]
        names_b = [snap_nodes[nid]["name"] for nid in best_cb]
        cluster_summary = (
            f"Cluster A ({len(best_ca)} nodes): {', '.join(names_a[:6])}\n"
            f"Cluster B ({len(best_cb)} nodes): {', '.join(names_b[:6])}"
        )

        # Farthest cross-component pairs (for LLM context)
        cross_pairs = []
        for a in best_ca:
            for b in best_cb:
                if frozenset([a, b]) not in snap_edge_set and a in snap_embs and b in snap_embs:
                    cross_pairs.append((_cosine_dist(snap_embs[a], snap_embs[b]), a, b))
        cross_pairs.sort(reverse=True)
        top_pairs = cross_pairs[:3]
        plan_result["top_pairs"] = [
            {"a": snap_nodes[a]["name"], "b": snap_nodes[b]["name"], "dist": round(d, 2)}
            for d, a, b in top_pairs
        ]
        disconnected_pairs_json = _json.dumps(
            [{"a": snap_nodes[a]["name"], "b": snap_nodes[b]["name"], "distance": round(d, 2)}
             for d, a, b in top_pairs], ensure_ascii=False
        )

        # ── 3. Centroid interpolation → ChromaDB ────────────────────────
        # Primary: probe embedding space between cluster centroids
        interp_chunks: list[dict] = []
        try:
            interp_chunks = _interpolate_bridge_rag(
                best_ca, best_cb, snap_embs, n_probes=3, n_results=3,
                filter_langs=session.get("filter_langs", _ALL_FILTER_LANGS),
                filter_sources=session.get("filter_sources") or None,
            )
            print(f"[P4] interp done: {_time.time()-_t0:.1f}s, "
                  f"chunks={len(interp_chunks)}, centroid_dist={best_dist:.3f}", flush=True)
        except Exception as e:
            print(f"[P4] interp error: {e}", flush=True)

        if interp_chunks:
            _rag_ctx = "\n\n".join(
                f"[{c.get('source_name') or c['source'][:40]}]\n{c['text'][:200]}"
                for c in interp_chunks[:5]
            )

        if realtime_context:
            _rt_section = f"[LIVE WEB]\n{realtime_context[:600]}"
            _rag_ctx = (_rt_section + "\n\n" + _rag_ctx) if _rag_ctx else _rt_section

        # ── 4. LLM: name bridge nodes ────────────────────────────────────
        # RAG-grounded when ChromaDB has data; general knowledge as fallback
        rag_section = (
            f"Knowledge found between the two clusters (from knowledge base):\n{_rag_ctx}\n"
            "Base your bridge concept names on this knowledge."
            if _rag_ctx else
            "(Knowledge base has no data between these clusters — use your general knowledge.)"
        )
        try:
            existing_summary_snap = _json.dumps(
                [{"name": n["name"], "status": n["status"]}
                 for n in snap_nodes.values() if n.get("status") != "skip"],
                ensure_ascii=False,
            ) if snap_nodes else "(no nodes yet)"
            _bad_nodes = get_recent_bad_nodes(limit=15)
            _bad_hint = (
                "\nUser-marked low-quality nodes (avoid): " + ", ".join(_bad_nodes) + "\n"
            ) if _bad_nodes else ""
            raw2 = chat(
                system=_PLANNER_SYSTEM,
                messages=[{"role": "user", "content": _PLANNER_PROMPT.format(
                    goal=goal or "(free exploration)",
                    cluster_summary=cluster_summary,
                    disconnected_pairs=disconnected_pairs_json,
                    existing_nodes=existing_summary_snap,
                    rag_context_section=rag_section,
                    node_lang=node_lang,
                    bad_nodes_hint=_bad_hint,
                )}],
            )
            m2 = re.search(r'\{[\s\S]+\}', raw2)
            _parsed2 = _json.loads(m2.group()) if m2 else {}
            print(f"[P4] bridge done: {_time.time()-_t0:.1f}s, "
                  f"bridges={len(_parsed2.get('bridge_nodes', []))}", flush=True)
        except Exception as e:
            print(f"[P4] plan error: {e}", flush=True)
            plan_result["error"] = str(e)

        plan_result.update({
            "parsed": _parsed2,
            "rag_context": _rag_ctx,
            "interp_chunks": len(interp_chunks),
            "cluster_count": len(components),
            "disconnected": is_disconnected,
        })

    # Launch both threads simultaneously
    t_ce   = threading.Thread(target=_run_chat_extract,       daemon=True)
    t_plan = threading.Thread(target=_run_plan_speculative,   daemon=True)
    t_ce.start()
    t_plan.start()
    t_ce.join()    # Wait only for ChatExtract; Plan keeps running in the background

    # ── Unpack ChatExtract results ────────────────────────────────────
    off_topic       = ce_result.get("off_topic", False)
    reply           = ce_result.get("reply", "繼續告訴我更多吧！")
    raw_concepts    = ce_result.get("raw_concepts", [])
    suggested_nodes_raw = ce_result.get("suggested_raw", [])
    decision_reason = ce_result.get("decision_reason")
    deferred_names  = ce_result.get("deferred_names", [])

    # ── Code constraint: deferred is only valid for ai_suggested siblings ─────
    # Rule 1: names explicitly mentioned in user_concepts must not be marked deferred
    _user_concept_names = {c["name"] for c in raw_concepts if c.get("name")}
    deferred_names = [d for d in deferred_names if d not in _user_concept_names]
    # Rule 2: deferred semantically means "not sure about a suggested option",
    # only names appearing in ai_suggestions are allowed to be marked deferred
    _suggested_names = {s.get("name") for s in suggested_nodes_raw if s.get("name")}
    deferred_names = [d for d in deferred_names if d in _suggested_names]

    # ── 1b. Debug event: ChatExtract result ──────────────────────────
    yield _sse({
        "type": "debug",
        "stage": "chat_extract",
        "reply": reply,
        "user_concepts": raw_concepts,
        "ai_suggestions": suggested_nodes_raw,
        "decision_reason": decision_reason,
        "deferred_names": deferred_names,
        "error": ce_result.get("error"),
    })

    # ── 2. Code expansion: generic concepts × sibling location groups ────────
    concepts = _expand_by_location_siblings(raw_concepts, nodes, edges)

    # ── 3. Add expanded nodes (todo/deferred, source=user) + create parent strong edges ──
    if not session.get("auto_nodes", True):
        # Note mode: AI replies only, skip all node generation
        return
    added_ids: list[str] = []
    newly_confirmed_ids: list[str] = []  # nodes transitioning unknown → todo, used for sibling-skip
    # Set of concept names the user explicitly marked as "not sure" (→ deferred status)
    deferred_name_set = set(deferred_names)
    # name → id lookup table (used for parent strong edges)
    name_to_id = {n["name"]: nid for nid, n in nodes.items()}

    for nn in concepts:
        if not nn.get("name"):
            continue
        try:
            new_emb = embed(f"{nn['name']} {nn.get('description', '')}"[:400])
        except Exception:
            new_emb = None
        # Semantic deduplication: exclude nodes added in this batch to avoid intra-round merges
        # User-marked "not sure" concepts → deferred; others → todo
        new_status = "deferred" if nn["name"] in deferred_name_set else "todo"

        dup_id = _find_duplicate(new_emb, embeddings, exclude_ids=set(added_ids)) if new_emb else None
        if dup_id:
            existing = nodes[dup_id]
            was_unknown = existing.get("status") == "unknown"
            existing["name"]   = nn["name"]
            existing["source"] = "user"
            if nn.get("description"):
                existing["description"] = nn["description"]
            existing["status"] = new_status
            if new_emb:
                embeddings[dup_id] = new_emb
            name_to_id[nn["name"]] = dup_id
            added_ids.append(dup_id)
            if was_unknown and new_status == "todo":
                newly_confirmed_ids.append(dup_id)
            yield _sse({"type": "node_update", "id": dup_id, "node": _node_vis(existing)})
            continue
        if any(n["name"] == nn["name"] for n in nodes.values()):
            continue
        nid  = str(uuid.uuid4())[:8]
        node = {
            "id":          nid,
            "name":        nn["name"],
            "description": nn.get("description", ""),
            "status":      new_status,
            "source":      "user",
            "exclusive":   False,
        }
        nodes[nid] = node
        if new_emb:
            embeddings[nid] = new_emb
        name_to_id[nn["name"]] = nid
        added_ids.append(nid)
        yield _sse({"type": "node_add", "node": _node_vis(node)})

        parent_name = nn.get("parent_name")
        if parent_name and parent_name in name_to_id:
            pid = name_to_id[parent_name]
            key = frozenset({pid, nid})
            if key not in edge_set:
                edge_set.add(key)
                eid  = str(uuid.uuid4())[:8]
                edge = {"id": eid, "from_id": pid, "to_id": nid, "is_parent": True}
                edges.append(edge)
                yield _sse({"type": "edge_add", "edge": _edge_vis(edge, nodes)})

    # ── 3b. Sibling-skip + Decision Point recording ──────────────────

    for confirmed_id in newly_confirmed_ids:
        skipped_ids_this: list[str] = []
        deferred_ids_this: list[str] = []

        for edge in edges:
            if not edge.get("is_parent") or edge["to_id"] != confirmed_id:
                continue
            parent_id = edge["from_id"]
            for edge2 in edges:
                if not edge2.get("is_parent") or edge2["from_id"] != parent_id:
                    continue
                sib_id = edge2["to_id"]
                if sib_id == confirmed_id:
                    continue
                sib = nodes.get(sib_id)
                if sib and sib.get("status") == "unknown" and (
                    sib.get("exclusive") or sib.get("source") == "ai_suggested"
                ):
                    if sib["name"] in deferred_name_set:
                        # User said "not sure" → deferred (purple dashed, keep possibility open)
                        sib["status"] = "deferred"
                        deferred_ids_this.append(sib_id)
                    else:
                        # Normal sibling-skip → grey out
                        sib["status"] = "skip"
                        skipped_ids_this.append(sib_id)
                    yield _sse({"type": "node_update", "id": sib_id, "node": _node_vis(sib)})
            break  # Each node has at most one is_parent parent

        # Record Decision Point
        if skipped_ids_this or deferred_ids_this:
            session["decisions"].append({
                "selected_ids":  [confirmed_id],
                "skipped_ids":   skipped_ids_this,
                "deferred_ids":  deferred_ids_this,
                "reason":        decision_reason,
            })
            yield _sse({
                "type":     "decision_recorded",
                "selected": [nodes[confirmed_id]["name"]],
                "skipped":  [nodes[i]["name"] for i in skipped_ids_this],
                "deferred": [nodes[i]["name"] for i in deferred_ids_this],
                "reason":   decision_reason,
            })

    # ── 3c. Add AI-suggested nodes (suggested_nodes, source=ai_suggested) ────
    suggested_nodes = _expand_by_location_siblings(
        [s for s in suggested_nodes_raw if s.get("name")], nodes, edges
    )
    for nn in suggested_nodes:
        if not nn.get("name"):
            continue
        if any(n["name"] == nn["name"] for n in nodes.values()):
            continue
        try:
            new_emb = embed(f"{nn['name']} {nn.get('description', '')}"[:400])
        except Exception:
            new_emb = None
        # Deduplicate against unknown nodes only (avoid overwriting confirmed todo nodes)
        unknown_embs = {nid: emb for nid, emb in embeddings.items()
                        if nodes.get(nid, {}).get("status") == "unknown"}
        dup_id = _find_duplicate(new_emb, unknown_embs, exclude_ids=set(added_ids)) if new_emb else None
        if dup_id:
            existing = nodes[dup_id]
            existing["name"]      = nn["name"]
            existing["source"]    = "ai_suggested"
            existing["exclusive"] = nn.get("exclusive", True)
            if nn.get("description"):
                existing["description"] = nn["description"]
            if new_emb:
                embeddings[dup_id] = new_emb
            added_ids.append(dup_id)
            yield _sse({"type": "node_update", "id": dup_id, "node": _node_vis(existing)})
            continue
        nid  = str(uuid.uuid4())[:8]
        node = {
            "id":          nid,
            "name":        nn["name"],
            "description": nn.get("description", ""),
            "status":      "unknown",
            "source":      "ai_suggested",
            "exclusive":   nn.get("exclusive", True),   # AI suggestions default to exclusive; parallel items explicitly set to false by LLM
        }
        nodes[nid] = node
        if new_emb:
            embeddings[nid] = new_emb
        name_to_id[nn["name"]] = nid
        added_ids.append(nid)
        yield _sse({"type": "node_add", "node": _node_vis(node)})

        parent_name = nn.get("parent_name")
        if parent_name and parent_name in name_to_id:
            pid = name_to_id[parent_name]
            key = frozenset({pid, nid})
            if key not in edge_set:
                edge_set.add(key)
                eid  = str(uuid.uuid4())[:8]
                edge = {"id": eid, "from_id": pid, "to_id": nid, "is_parent": True}
                edges.append(edge)
                yield _sse({"type": "edge_add", "edge": _edge_vis(edge, nodes)})

    # ── 3d. Seed Expansion: for early graphs (≤8 nodes) expand prerequisites for each new node ──
    # Goal: grow 8-15 nodes from the first conversation round, solving the problem of Planner not triggering early
    if len(nodes) <= 8 and added_ids:
        _existing_names_for_seed = _json.dumps(
            [n["name"] for n in nodes.values()], ensure_ascii=False
        )
        for _seed_id in added_ids[:2]:   # Expand at most 2 nodes to avoid combinatorial explosion
            _seed_node = nodes.get(_seed_id)
            if not _seed_node or _seed_node.get("status") not in ("todo", "unknown"):
                continue
            try:
                _seed_raw = chat(
                    system=_SEED_EXPAND_SYSTEM,
                    messages=[{"role": "user", "content": _SEED_EXPAND_PROMPT.format(
                        node_lang=node_lang, goal=goal,
                        concept_name=_seed_node["name"],
                        concept_desc=_seed_node.get("description", "")[:80],
                        existing_names=_existing_names_for_seed,
                    )}],
                )
                _sm = re.search(r'\{[\s\S]+\}', _seed_raw or "")
                _seed_parsed = _json.loads(_sm.group()) if _sm else {}
                for _prereq in _seed_parsed.get("prerequisites", [])[:3]:
                    _pname = (_prereq.get("name") or "").strip()
                    _pdesc = (_prereq.get("description") or "").strip()
                    if not _pname:
                        continue
                    if any(n["name"] == _pname for n in nodes.values()):
                        continue
                    _pid = str(uuid.uuid4())[:8]
                    _pnode = {
                        "id": _pid, "name": _pname, "status": "unknown",
                        "source": "ai_planned", "exclusive": False,
                        "description": _pdesc, "reason": f"prerequisite for {_seed_node['name']}",
                        "children": [], "parent": _seed_id, "level": 2,
                    }
                    nodes[_pid] = _pnode
                    try:
                        _pemb = embed(f"{_pname} {_pdesc}"[:300])
                        embeddings[_pid] = _pemb
                    except Exception:
                        _pemb = None
                    # Connect to seed node
                    _eid = f"{_pid[:4]}-{_seed_id[:4]}"
                    _pedge = {"id": _eid, "from_id": _pid, "to_id": _seed_id, "is_parent": True}
                    edges.append(_pedge)
                    edge_set.add(frozenset({_pid, _seed_id}))
                    yield _sse({"type": "node_add", "node": _node_vis(_pnode)})
                    yield _sse({"type": "edge_add", "edge": _edge_vis(_pedge, nodes)})
                    _existing_names_for_seed = _json.dumps(
                        [n["name"] for n in nodes.values()], ensure_ascii=False
                    )
            except Exception as _se:
                print(f"[seed] error for {_seed_node['name']}: {_se}", flush=True)

    # ── 4+5. Wait for speculative planning to finish, then apply results ──────
    # t_ce is done and nodes are in the graph; t_plan may still be running (or finished).
    # join waits at most 20s; skip bridge nodes on timeout to avoid blocking the frontend.
    t_plan.join(timeout=20)
    parsed2 = plan_result.get("parsed", {})

    # ── Debug event: Plan result ──────────────────────────────────────
    yield _sse({
        "type": "debug",
        "stage": "plan",
        "disconnected": plan_result.get("disconnected", False),
        "cluster_count": plan_result.get("cluster_count", 0),
        "interp_chunks": plan_result.get("interp_chunks", 0),
        "rag_context_len": len(plan_result.get("rag_context", "")),
        "top_pairs": plan_result.get("top_pairs", []),
        "bridge_nodes": parsed2.get("bridge_nodes", []),
        "error": plan_result.get("error"),
    })

    # Code-layer quality filter: name rules + hard cap of 3 (validated against current graph state)
    plan_candidates = _filter_plan_nodes(
        parsed2.get("bridge_nodes", []), goal, nodes
    )

    added_ids2: list[str] = []
    bridge_connects: dict[str, list[str]] = {}  # nid → [endpoint_name_a, endpoint_name_b]
    for nn in plan_candidates:
        if not nn.get("name"):
            continue
        # Embed first for semantic deduplication + specificity check
        try:
            new_emb = embed(f"{nn['name']} {nn.get('description', '')}"[:400])
        except Exception:
            new_emb = None
        # Specificity check: discard overly generic nodes
        if new_emb and len(embeddings) >= 5:  # stdev needs enough samples to be meaningful
            score = _specificity_score(new_emb, embeddings)
            if score < 0.08:
                continue
        # Semantic deduplication: LLM2 compares against unknown nodes only, avoid overwriting confirmed todo nodes
        unknown_embs = {nid: emb for nid, emb in embeddings.items()
                        if nodes.get(nid, {}).get("status") == "unknown"}
        dup_id = _find_duplicate(new_emb, unknown_embs) if new_emb else None
        if dup_id:
            existing = nodes[dup_id]
            existing["name"] = nn["name"]   # Update name, keep unknown status
            if nn.get("description"):
                existing["description"] = nn["description"]
            if new_emb:
                embeddings[dup_id] = new_emb
            added_ids2.append(dup_id)
            yield _sse({"type": "node_update", "id": dup_id, "node": _node_vis(existing)})
            continue
        # Skip if name is identical to an existing node
        if any(n["name"] == nn["name"] for n in nodes.values()):
            continue
        nid  = str(uuid.uuid4())[:8]
        node = {
            "id":          nid,
            "name":        nn["name"],
            "description": nn.get("description", ""),
            "status":      "unknown",
            "source":      "ai_planned",
            "exclusive":   False,
        }
        nodes[nid] = node
        if new_emb:
            embeddings[nid] = new_emb
        added_ids2.append(nid)
        # Remember bridge relationships (endpoint names) for adding explicit edges later
        connects = nn.get("connects", [])
        if connects:
            bridge_connects[nid] = connects
        yield _sse({"type": "node_add", "node": _node_vis(node)})

    # ── 6. Proximity edge computation ────────────────────────────────
    all_new_ids = added_ids + added_ids2
    new_edges = _compute_new_edges(all_new_ids, embeddings, edge_set, nodes)
    for edge in new_edges:
        edges.append(edge)
        yield _sse({"type": "edge_add", "edge": _edge_vis(edge, nodes)})

    # ── 6a. Connectivity guarantee: bridge isolated components ────────
    # After proximity edges, check if any node groups are still disconnected.
    # Connect them with the minimum-distance cross-component edge (MST bridge).
    conn_edges = _ensure_connected(nodes, embeddings, edge_set)
    for edge in conn_edges:
        edges.append(edge)
        yield _sse({"type": "edge_add", "edge": _edge_vis(edge, nodes)})
    if conn_edges:
        print(f"[connect] bridged {len(conn_edges)} isolated component(s)", flush=True)

    # ── 6b-pre. Bridge node explicit wiring ──────────────────────────
    # Bridge nodes: LLM-specified endpoint names → create direct edges (threshold relaxed to 0.55)
    BRIDGE_EDGE_THRESHOLD = 0.55
    name_to_nid = {n["name"]: nid for nid, n in nodes.items()}
    for bridge_nid, endpoint_names in bridge_connects.items():
        if bridge_nid not in embeddings:
            continue
        bridge_emb = embeddings[bridge_nid]
        for ep_name in endpoint_names:
            ep_nid = name_to_nid.get(ep_name)
            if not ep_nid or ep_nid not in embeddings:
                continue
            key = frozenset([bridge_nid, ep_nid])
            if key in edge_set:
                continue
            dist = _cosine_dist(bridge_emb, embeddings[ep_nid])
            if dist <= BRIDGE_EDGE_THRESHOLD:
                edge_set.add(key)
                eid  = f"{bridge_nid}→{ep_nid}"
                edge = {"id": eid, "from_id": bridge_nid, "to_id": ep_nid, "is_bridge": True}
                edges.append(edge)
                yield _sse({"type": "edge_add", "edge": _edge_vis(edge, nodes)})

    # ── 6b. Semantic coordinate layout ────────────────────────────────────────
    # After each round, recompute all node semantic positions (MDS) so graph distance = knowledge distance
    layout = _compute_semantic_layout(embeddings, nodes)
    if layout:
        # Store cluster info back into node for use by _compute_new_edges in the next round
        for nid, pos in layout.items():
            if nid in nodes:
                nodes[nid]["_cluster"] = pos.get("cluster", -1)
        yield _sse({"type": "layout_update", "positions": layout})

    # ── 6c. Parent auto-resolve: unknown node with a confirmed child via is_parent edge → done ──
    # Only inspect is_parent strong edges, not proximity edges (avoid false positives from semantic similarity)
    nodes_with_todo_child = set()
    for edge in edges:
        if not edge.get("is_parent"):
            continue
        from_node = nodes.get(edge["from_id"], {})
        to_node   = nodes.get(edge["to_id"],   {})
        # Only promote parent to done when parent(from_node) is unknown and child(to_node) is confirmed
        # Not bidirectional: a child having a todo parent does not mean the child is confirmed
        if from_node.get("status") == "unknown" and to_node.get("status") in ("todo", "done"):
            nodes_with_todo_child.add(edge["from_id"])

    for nid in nodes_with_todo_child:
        node = nodes.get(nid)
        if not node or node.get("status") != "unknown":
            continue
        node["status"] = "done"
        yield _sse({"type": "node_update", "id": nid, "node": _node_vis(node)})
        for edge in edges:
            if edge["from_id"] == nid or edge["to_id"] == nid:
                yield _sse({"type": "edge_update", "edge": _edge_vis(edge, nodes)})

    # ── 7. Completion check ──────────────────────────────────────────
    ready = _all_filled(nodes)
    if ready:
        try:
            record_goal(
                user_id     = session.get("user_id", "anonymous"),
                description = goal,
                context     = "; ".join(n["name"] for n in nodes.values()),
                goal_type   = "general",
            )
        except Exception:
            pass

    # ── 8. Node coverage update (text mention + status floor) ────────
    _node_cov = session.setdefault("node_coverage", {})
    _cov_updates: dict[str, float] = {}
    for _nid, _node_obj in nodes.items():
        _status = _node_obj.get("status", "unknown")
        _name   = _node_obj.get("name", "")
        _prev   = _node_cov.get(_nid, 0.0)
        _new    = _prev
        # User directly mentions node name → +30% (capped at 1.0)
        if _name and len(_name) >= 2 and _name in user_text:
            _new = min(1.0, _new + 0.30)
        # Status floor: done≥0.85, todo≥0.40, deferred≥0.15
        _floor = {"done": 0.85, "todo": 0.40, "deferred": 0.15}.get(_status, 0.0)
        _new = max(_new, _floor)
        _new = round(_new, 3)
        if abs(_new - _prev) > 0.005:
            _node_cov[_nid] = _new
            _cov_updates[_nid] = _new
    if _cov_updates:
        yield _sse({"type": "coverage_update", "coverages": _cov_updates})

    from datetime import datetime as _dtm2
    session["messages"].append({"role": "assistant", "content": reply, "ts": _dtm2.now().isoformat()})
    yield _sse({"type": "reply", "text": reply, "ready": ready})


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return FileResponse(_FRONTEND_DIR / "index.html")


@app.post("/api/start")
def start(req: StartRequest):
    from datetime import datetime as _dt
    session_id = str(uuid.uuid4())[:8]
    _topic = detect_topic(req.goal)
    sessions[session_id] = {
        "goal":         req.goal,
        "topic":        _topic,   # detected from freshness.yaml for TTL-aware crawling
        "user_id":      req.user_id,
        "lang":         req.lang,
        "filter_langs":    _ALL_FILTER_LANGS[:],  # show all languages by default
        "filter_sources":  [],                    # [] = all sources; non-empty = only listed sources
        "auto_nodes":      True,                  # when False: AI replies only, no nodes added to graph
        "created_at":   _dt.now().isoformat(),
        "messages":     [],
        "nodes":        {},      # id → {id, name, description, status, source, exclusive}
        "embeddings":   {},      # id → list[float]
        "edge_set":     set(),   # frozenset({id1, id2}) for dedup
        "edges":        [],      # [{id, from_id, to_id, is_parent?}]
        "decisions":    [],      # [{selected_ids, skipped_ids, deferred_ids, reason}]
        "node_coverage":{},      # id → float (0.0~1.0), degree to which node is covered by conversation
    }
    print(f"[session] {session_id} topic={_topic} ({get_topic_name(_topic)})", flush=True)

    def event_stream():
        yield _sse({"type": "graph_init", "mode": "network", "llm": _LLM_LABEL, "session_id": session_id})
        if req.goal:
            yield from _process_message(session_id, req.goal)
        _save_session(session_id)
        yield _sse({"type": "done", "session_id": session_id})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/message")
def message(req: MessageRequest):
    if req.session_id not in sessions:
        return {"error": "Session not found"}
    # Update lang if user switched language mid-session
    sessions[req.session_id]["lang"] = req.lang

    def event_stream():
        yield from _process_message(req.session_id, req.text.strip())
        _save_session(req.session_id)
        yield _sse({"type": "done"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


_EXPORT_SYSTEM = (
    "You generate a concise knowledge context prompt from a user's learning graph. "
    "The output will be pasted directly into an AI chat to continue the learning journey. "
    "Output only the ready-to-use prompt text, no meta-commentary."
)

_EXPORT_TMPL = """User's original goal: {goal}

Knowledge graph — node status and descriptions:

COMPLETED ({done_count}):
{done_nodes}

SKIPPED ({skip_count}):
{skip_nodes}

STILL TO LEARN ({todo_count}):
{todo_nodes}

Generate a prompt in {reply_lang} the user can paste into Claude / ChatGPT to continue learning.
The prompt should:
1. Briefly state the background they already know (from completed nodes, with key concepts)
2. Mention what was skipped, if any
3. Ask the AI to help with what remains (todo nodes), or if all done, to deepen understanding
Be concise but complete. Output ONLY the prompt text, ready to copy-paste."""


_EDIT_SYSTEM = (
    "You are a planning editor assistant. You can update existing graph nodes OR add new ones. "
    "Output strict JSON only, no markdown."
)

_EDIT_PROMPT = """Reply language: {reply_lang}

Current graph nodes:
{skeleton}

User said: "{message}"

Output JSON:
{{
  "updates": [
    {{"id": "existing_node_id", "name": "Updated name (5-15 chars)", "description": "Updated description", "status": "todo|done|skip"}}
  ],
  "new_nodes": [
    {{"name": "Node name (5-15 chars)", "description": "Detailed description (1-2 sentences)"}}
  ],
  "reply": "Brief confirmation in {reply_lang} (max 40 chars)"
}}

Rules:
- Use "updates" to modify existing nodes by their exact id; "status" is optional
- Use "new_nodes" for brand-new concepts NOT yet in the graph
- 'name' on the graph must be short and specific (5-15 chars)
- 'status': use "done" if user says they've learned it, "skip" to drop it
- Both arrays may be empty if nothing applies
- Reply in {reply_lang}"""


@app.post("/api/edit")
def edit_graph(req: EditRequest):
    """Natural-language node editing by the user after planning is complete."""
    data = sessions.get(req.session_id)
    if not data:
        return {"error": "Session not found"}

    nodes: dict = data.get("nodes", {})

    # Compact node summary for LLM
    skeleton_summary = _json.dumps([{
        "id":          nid,
        "name":        n.get("name"),
        "description": (n.get("description") or "")[:80],
        "status":      n.get("status"),
    } for nid, n in nodes.items()], ensure_ascii=False)

    lang = data.get("lang", "zh-TW")
    reply_lang = _LANG_MAP.get(lang, "Traditional Chinese")
    prompt = _EDIT_PROMPT.format(
        skeleton=skeleton_summary,
        message=req.text.strip(),
        reply_lang=reply_lang,
    )

    raw = chat(system=_EDIT_SYSTEM, messages=[{"role": "user", "content": prompt}])

    try:
        m = re.search(r'\{[\s\S]+\}', raw)
        edit = _json.loads(m.group()) if m else {}
    except Exception:
        edit = {}

    updates   = edit.get("updates", [])
    new_nodes = edit.get("new_nodes", [])
    reply     = edit.get("reply", "已更新。")

    # Apply updates (modify existing nodes)
    for u in updates:
        uid = u.get("id")
        if not uid or uid not in nodes:
            continue
        n = nodes[uid]
        if "name" in u and u["name"]:        n["name"]        = u["name"]
        if "description" in u and u["description"]: n["description"] = u["description"]
        if "status" in u and u["status"] in ("todo", "done", "skip"): n["status"] = u["status"]

    # Handle newly added nodes
    embeddings: dict = data.get("embeddings", {})
    edges: list      = data.get("edges", [])
    edge_set: set    = data.get("edge_set", set())
    node_adds = []
    edge_adds = []

    for nn in new_nodes:
        nn_name = (nn.get("name") or "").strip()
        nn_desc = (nn.get("description") or "").strip()
        if not nn_name:
            continue
        import uuid as _uuid2
        nid = str(_uuid2.uuid4())[:8]
        new_node = {
            "id": nid, "name": nn_name, "status": "todo",
            "source": "user", "exclusive": False,
            "description": nn_desc, "reason": "",
            "children": [], "parent": None, "level": 1,
        }
        nodes[nid] = new_node

        # Use embedding to find the nearest existing node and create an edge
        try:
            new_emb = embed(f"{nn_name} {nn_desc}"[:300])
            embeddings[nid] = new_emb
            best_nid, best_dist = None, 1.0
            for eid, eemb in embeddings.items():
                if eid == nid or not eemb:
                    continue
                d = _cosine_dist(new_emb, eemb)
                if d < best_dist:
                    best_dist, best_nid = d, eid
            if best_nid and best_dist < 0.6:
                key = frozenset({nid, best_nid})
                if key not in edge_set:
                    edge_set.add(key)
                    edge = {"id": f"{best_nid[:4]}-{nid[:4]}", "from_id": best_nid, "to_id": nid}
                    edges.append(edge)
                    edge_adds.append(_edge_vis(edge, nodes))
        except Exception:
            pass

        node_adds.append(_node_vis(new_node))

    _save_session(req.session_id)
    return {
        "message":      reply,
        "node_updates": [_node_vis(n) for n in nodes.values() if n["id"] not in {na["id"] for na in node_adds}],
        "node_adds":    node_adds,
        "edge_adds":    edge_adds,
    }


_SAFE_NODE_ID_RE = re.compile(r'^[a-zA-Z0-9_\-]+$')


@app.post("/api/skip")
def skip_node(req: SkipRequest):
    """User manually skips a node (does not need this item)."""
    if not _SAFE_NODE_ID_RE.match(req.node_id):
        return {"error": "Invalid node_id"}
    data = sessions.get(req.session_id)
    if not data:
        return {"error": "Session not found"}

    nodes: dict = data.get("nodes", {})
    edges: list = data.get("edges", [])

    node = nodes.get(req.node_id)
    if not node:
        return {"error": "Node not found"}

    node["status"] = "skip"

    # Recompute edge activation state
    edge_updates = [_edge_vis(e, nodes) for e in edges
                    if e["from_id"] == req.node_id or e["to_id"] == req.node_id]

    ready = _all_filled(nodes)
    _save_session(req.session_id)

    return {
        "node":         _node_vis(node),
        "edge_updates": edge_updates,
        "ready":        ready,
    }


@app.post("/api/reopen")
def reopen_node(req: SkipRequest):
    """Re-open a previously skipped node as todo (user changed their mind)."""
    if not _SAFE_NODE_ID_RE.match(req.node_id):
        return {"error": "Invalid node_id"}
    data = sessions.get(req.session_id)
    if not data:
        return {"error": "Session not found"}
    nodes: dict = data.get("nodes", {})
    edges: list = data.get("edges", [])
    node = nodes.get(req.node_id)
    if not node:
        return {"error": "Node not found"}
    # Only allow reopening from skip status
    if node.get("status") != "skip":
        return {"error": "Node is not skipped"}
    node["status"] = "todo"
    edge_updates = [_edge_vis(e, nodes) for e in edges
                    if e["from_id"] == req.node_id or e["to_id"] == req.node_id]
    ready = _all_filled(nodes)
    return {
        "node":         _node_vis(node),
        "edge_updates": edge_updates,
        "ready":        ready,
    }


class NodeStatusRequest(BaseModel):
    session_id: str
    node_id:    str
    status:     str   # "todo" | "done" | "skip"


@app.post("/api/node_status")
def set_node_status(req: NodeStatusRequest):
    """Directly set node status (todo/done/skip), for quick toggle on node click."""
    if req.status not in ("todo", "done", "skip"):
        return {"error": "Invalid status"}
    if not _SAFE_NODE_ID_RE.match(req.node_id):
        return {"error": "Invalid node_id"}
    data = sessions.get(req.session_id)
    if not data:
        return {"error": "Session not found"}
    nodes: dict = data.get("nodes", {})
    edges: list = data.get("edges", [])
    node = nodes.get(req.node_id)
    if not node:
        return {"error": "Node not found"}
    node["status"] = req.status
    edge_updates = [_edge_vis(e, nodes) for e in edges
                    if e["from_id"] == req.node_id or e["to_id"] == req.node_id]
    _save_session(req.session_id)
    return {"node": _node_vis(node), "edge_updates": edge_updates}


@app.get("/api/sessions")
def get_sessions():
    """Return a summary list of all sessions."""
    return {"sessions": list_sessions()}


class SessionDataRequest(BaseModel):
    session_id: str


@app.post("/api/session_data")
def get_session_data(req: SessionDataRequest):
    """Return full node, edge, and message data for a session (for frontend graph restoration)."""
    data = sessions.get(req.session_id)
    if not data:
        return {"error": "Session not found"}
    nodes = data.get("nodes", {})
    edges = data.get("edges", [])
    # Return only role + content + ts; exclude heavy fields like embeddings
    messages = [
        {"role": m["role"], "content": m["content"], "ts": m.get("ts", "")}
        for m in data.get("messages", [])
    ]
    return {
        "nodes":    [_node_vis(n) for n in nodes.values()],
        "edges":    [_edge_vis(e, nodes) for e in edges],
        "messages": messages,
    }


class UndoRequest(BaseModel):
    session_id: str

@app.post("/api/undo")
def undo_step(req: UndoRequest):
    """Restore graph to the state before the previous conversation round."""
    data = sessions.get(req.session_id)
    if not data:
        return {"error": "Session not found"}
    snapshots = data.get("snapshots", [])
    if not snapshots:
        return {"error": "No snapshots", "snapshots_remaining": 0}

    snap = snapshots.pop()
    data["nodes"]      = snap["nodes"]
    data["edges"]      = snap["edges"]
    data["embeddings"] = snap["embeddings"]
    data["edge_set"]   = {frozenset({e["from_id"], e["to_id"]}) for e in snap["edges"]}
    data["messages"]   = snap["messages"]
    data["decisions"]  = snap["decisions"]
    _save_session(req.session_id)

    nodes = data["nodes"]
    edges = data["edges"]
    msgs  = [{"role": m["role"], "content": m["content"], "ts": m.get("ts", "")}
             for m in data["messages"]]
    return {
        "ok": True,
        "snapshots_remaining": len(snapshots),
        "nodes":    [_node_vis(n) for n in nodes.values()],
        "edges":    [_edge_vis(e, nodes) for e in edges],
        "messages": msgs,
    }


@app.post("/api/sessions/{session_id}/filter_langs")
def set_filter_langs(session_id: str, body: dict):
    """Update which content languages are visible in this session."""
    data = sessions.get(session_id)
    if not data:
        return {"ok": False, "error": "Session not found"}
    langs = [l for l in body.get("filter_langs", _ALL_FILTER_LANGS) if l in ("en", "zh", "ja")]
    data["filter_langs"] = langs or _ALL_FILTER_LANGS[:]
    return {"ok": True, "filter_langs": data["filter_langs"]}


@app.post("/api/sessions/{session_id}/auto_nodes")
def set_auto_nodes(session_id: str, body: dict):
    """Toggle whether AI conversation automatically adds nodes to the graph."""
    data = sessions.get(session_id)
    if not data:
        return {"ok": False, "error": "Session not found"}
    data["auto_nodes"] = bool(body.get("auto_nodes", True))
    return {"ok": True, "auto_nodes": data["auto_nodes"]}


@app.post("/api/add_node")
def add_node_manual(body: dict):
    """Manually add a node to the graph with auto-embedding and proximity edges."""
    session_id = body.get("session_id")
    name       = (body.get("name") or "").strip()
    description = (body.get("description") or "").strip()
    if not session_id or not name:
        return {"ok": False, "error": "session_id and name required"}
    data = sessions.get(session_id)
    if not data:
        return {"ok": False, "error": "Session not found"}

    nodes:      dict = data["nodes"]
    embeddings: dict = data["embeddings"]
    edge_set:   set  = data["edge_set"]
    edges:      list = data["edges"]

    nid = str(uuid.uuid4())[:8]
    node = {
        "id":          nid,
        "name":        name,
        "description": description,
        "status":      "todo",
        "source":      "user_manual",
        "exclusive":   False,
    }
    try:
        emb = embed(f"{name} {description}"[:400])
    except Exception:
        return {"ok": False, "error": "Embedding failed"}

    nodes[nid]      = node
    embeddings[nid] = emb

    new_edges = _compute_new_edges([nid], embeddings, edge_set, nodes)
    for e in new_edges:
        edges.append(e)

    return {
        "ok":    True,
        "node":  _node_vis(node),
        "edges": [_edge_vis(e, nodes) for e in new_edges],
    }


@app.post("/api/sessions/{session_id}/filter_sources")
def set_filter_sources(session_id: str, body: dict):
    """Update which KB sources are visible in this session. Empty list = all sources."""
    data = sessions.get(session_id)
    if not data:
        return {"ok": False, "error": "Session not found"}
    sources = body.get("filter_sources", [])
    data["filter_sources"] = sources if isinstance(sources, list) else []
    return {"ok": True, "filter_sources": data["filter_sources"]}


@app.delete("/api/sessions/{session_id}")
def remove_session(session_id: str):
    """Delete the specified session."""
    sessions.pop(session_id, None)
    delete_session(session_id)
    return {"ok": True}


@app.post("/api/export_markdown")
def export_markdown(req: ExportPromptRequest):
    """Export the learning graph as a Markdown checklist (pasteable into Notion/Obsidian)."""
    data = sessions.get(req.session_id)
    if not data:
        return {"error": "Session not found"}
    goal  = data.get("goal", "未命名目標")
    nodes = data.get("nodes", {})
    main_nodes = [n for n in nodes.values() if n.get("source") != "resource"]
    done_list  = [n for n in main_nodes if n.get("status") == "done"]
    todo_list  = [n for n in main_nodes if n.get("status") == "todo"]
    unknown_list = [n for n in main_nodes if n.get("status") == "unknown"]
    skip_list  = [n for n in main_nodes if n.get("status") == "skip"]
    lines = [f"# {goal}", ""]
    if done_list:
        lines += ["## ✅ 已完成"] + [f"- [x] {n['name']}" for n in done_list] + [""]
    active = todo_list + unknown_list
    if active:
        lines += ["## 📋 待完成"] + [f"- [ ] {n['name']}" for n in active] + [""]
    if skip_list:
        lines += ["## ⏭ 已跳過"] + [f"- [x] ~~{n['name']}~~" for n in skip_list] + [""]
    lines += [f"> 由 Ragraphe 生成 · 目標：{goal}"]
    return {"markdown": "\n".join(lines), "stats": {
        "done": len(done_list), "todo": len(active), "skip": len(skip_list),
        "total": len(main_nodes),
    }}


@app.post("/api/feedback")
def node_feedback(req: FeedbackRequest):
    """Record node quality feedback (good / bad) for subsequent LLM-Plan prompt correction."""
    data = sessions.get(req.session_id)
    goal = data.get("goal", "") if data else ""
    record_node_feedback(req.session_id, req.node_id, req.node_name, goal, req.feedback)
    return {"ok": True}


@app.get("/api/popular_nodes")
def popular_nodes(min_count: int = 2, limit: int = 30):
    """Cross-session popular nodes (concepts completed by multiple users)."""
    return {"nodes": get_popular_nodes(min_count=min_count, limit=limit)}


@app.post("/api/export_prompt")
def export_prompt(req: ExportPromptRequest):
    """Export the learning graph as a prompt ready to paste into an AI chat."""
    data = sessions.get(req.session_id)
    if not data:
        return {"error": "Session not found"}

    goal  = data.get("goal", "")
    nodes = data.get("nodes", {})
    lang  = data.get("lang", "zh-TW")
    reply_lang = _LANG_MAP.get(lang, "Traditional Chinese")

    done_list  = [n for n in nodes.values() if n.get("status") == "done"]
    skip_list  = [n for n in nodes.values() if n.get("status") == "skip"]
    todo_list  = [n for n in nodes.values() if n.get("status") not in ("done", "skip")]

    def _fmt(lst: list) -> str:
        if not lst:
            return "（無）"
        return "\n".join(
            f"- {n['name']}: {(n.get('description') or '').strip()[:150]}"
            for n in lst
        )

    prompt_body = _EXPORT_TMPL.format(
        goal=goal,
        done_count=len(done_list),
        skip_count=len(skip_list),
        todo_count=len(todo_list),
        done_nodes=_fmt(done_list),
        skip_nodes=_fmt(skip_list),
        todo_nodes=_fmt(todo_list),
        reply_lang=reply_lang,
    )

    result = chat(system=_EXPORT_SYSTEM, messages=[{"role": "user", "content": prompt_body}])
    return {"prompt": result.strip()}


@app.post("/api/expand")
def expand_node(req: ExpandRequest):
    """Query related knowledge/vendor content from raw_chunks when a node is clicked."""
    # Reject invalid node_id (prevent path traversal or injection)
    if not _SAFE_NODE_ID_RE.match(req.node_id):
        return {"chunks": []}

    data = sessions.get(req.session_id)
    if not data:
        return {"chunks": []}

    node = data.get("nodes", {}).get(req.node_id)
    if not node:
        return {"chunks": []}

    # Include session goal as context to improve geographic relevance
    goal_ctx = data.get("goal", "")[:60]
    query_text = " ".join(filter(None, [
        node.get("name", ""), node.get("description", ""), goal_ctx
    ])).strip()
    if not query_text:
        return {"chunks": []}

    try:
        vec = embed(query_text[:500])
        candidates = query_raw_chunks(vec, n=6)
        relevant = [c for c in candidates if c["distance"] < RAG_THRESHOLD]

        # Auto-crawl when RAG is empty (first request)
        if not relevant:
            crawl_node_smart(node, goal_type="general", verbose=False)
            # Re-query after crawl
            candidates = query_raw_chunks(vec, n=6)
            relevant = [c for c in candidates if c["distance"] < RAG_THRESHOLD]

        from ragraphe.core.category import CATEGORY_LABEL, TIME_SENSITIVE
        def _source_type(src: str) -> str:
            if src.startswith("/files/") and src.endswith(".pdf"):
                return "pdf"
            if src.startswith("http"):
                return "url"
            return "text"

        return {
            "chunks": [
                {
                    "text":           c["text"][:400],
                    "source":         c["source"],
                    "source_name":    c.get("source_name", ""),
                    "source_type":    _source_type(c["source"]),
                    "category":       c.get("category", "general"),
                    "category_label": CATEGORY_LABEL.get(c.get("category", "general"), "📄 一般"),
                    "time_sensitive": c.get("category", "general") in TIME_SENSITIVE,
                    "expires_at":     c.get("expires_at", ""),
                    "distance":       round(c["distance"], 3),
                }
                for c in relevant
            ],
            "crawled": len(relevant) > 0,
        }
    except Exception as e:
        print(f"[expand error] {e}")
        return {"chunks": []}


# ── Satellite resources: target city list (for background crawl goal_type inference) ──────
_KNOWN_GOAL_CITIES = [
    # Country-level (checked first so "日本登山" gets goal_city="日本")
    "日本", "台灣", "韓國", "中國",
    # Japanese cities
    "京都", "大阪", "東京", "北海道", "沖縄", "福岡", "神戸", "横浜",
    # Kyoto sub-areas (goal contains these → goal_type=travel)
    "嵐山", "金閣寺", "清水寺", "祇園", "伏見稻荷", "天龍寺", "渡月橋",
    # Tokyo sub-areas
    "淺草", "秋葉原", "新宿", "涉谷",
    # Taiwanese cities
    "台北", "台南", "高雄", "台中", "嘉義", "花蓮", "台東",
    # Korean cities
    "首爾", "釜山", "Seoul", "Busan",
]


_LANG_TO_WIKI: dict[str, str] = {"en": "en", "zh-TW": "zh", "ja": "ja"}

def _do_targeted_crawl(node_name: str, node_desc: str, goal_text: str,
                       goal_type: str, session_data: dict, node_id: str,
                       topic: str = "default", lang: str = "en") -> None:
    """
    Background thread: targeted crawl for a single node.
    Queries using "node name + goal city" combination for better precision than generic crawl.
    When goal has country context, uses LLM to generate a country-appropriate search term
    (e.g. Japan goal + "入山許可" node → LLM suggests "日本登山届" not "入山許可 日本").
    After completion, moves node_id from _crawl_pending to _crawl_done.
    """
    try:
        goal_city = next((c for c in _KNOWN_GOAL_CITIES if c in goal_text), None)
        search_name = (f"{node_name} {goal_city}"
                       if goal_city and goal_city not in node_name
                       else node_name)

        # If goal has country context, ask LLM for a country-appropriate search term.
        # This handles cases like "入山許可" (Taiwan term) in a Japan hiking session.
        if goal_city and _GOAL_COUNTRY_RE.search(goal_text):
            try:
                q = _chat_quick(
                    [{"role": "user", "content":
                      f"用戶目標：{goal_text[:60]}\n"
                      f"知識節點：{node_name}\n"
                      f"請生成一個適合在{goal_city}搜尋引擎上找「{node_name}」等效知識的搜尋詞（5-10字）。"
                      f"重要：使用{goal_city}當地的正確詞彙，不要混用其他國家的術語。"
                      f"只回答搜尋詞，不解釋。"}],
                    system="只輸出搜尋詞，不解釋。",
                )
                q = q.strip().split("\n")[0][:30]
                if q:
                    search_name = q
                    print(f"[crawl] LLM search term for '{node_name}': {search_name!r}", flush=True)
            except Exception:
                pass  # Fallback to original search_name

        # Determine Wikipedia language: country keyword wins, else fall back to session lang
        wiki_lang = next(
            (wl for kw, wl in _COUNTRY_WIKI_LANG.items() if kw in goal_text),
            _LANG_TO_WIKI.get(lang, "en")
        )

        pseudo_node = {"name": search_name, "description": node_desc}
        crawl_node_smart(pseudo_node, goal_type=goal_type, verbose=True,
                         wiki_lang=wiki_lang, topic=topic)
        print(f"[crawl] targeted crawl done: {search_name} (wiki_lang={wiki_lang})", flush=True)
    except Exception as e:
        print(f"[crawl] targeted crawl error for {node_name}: {e}", flush=True)
    finally:
        # Normalize to sets (JSON restore may have made these lists)
        pending = set(session_data.get("_crawl_pending") or [])
        pending.discard(node_id)
        session_data["_crawl_pending"] = pending
        done = set(session_data.get("_crawl_done") or [])
        done.add(node_id)
        session_data["_crawl_done"] = done


@app.post("/api/node_resources")
def node_resources(req: NodeResourcesRequest):
    """
    Called automatically when a node appears: queries existing RAG for related knowledge,
    returns 2-3 resource child nodes.
    If DB has no results, triggers a background crawl and returns crawling=True; frontend retries after waiting.
    """
    if not _SAFE_NODE_ID_RE.match(req.node_id):
        return {"resources": []}
    data = sessions.get(req.session_id)
    if not data:
        return {"resources": []}
    node = data.get("nodes", {}).get(req.node_id)
    if not node:
        return {"resources": []}

    node_name = node.get("name", "")
    node_desc = node.get("description", "")
    session_lang = data.get("lang", "en")

    # Build graph-aware context: use edge-connected nodes as the strongest context signal.
    # The graph already encodes what the user cares about — nodes directly linked to this one
    # reflect the local topic cluster. This lets the embedding naturally filter cross-topic content
    # (e.g. "入山許可" connected to "日本登山" → query biases toward Japan, not Taiwan).
    goal_context = data.get("goal", "")[:80]

    # Direct neighbors via edges (highest relevance — same cluster)
    # edges is a list of {"from_id": ..., "to_id": ...} dicts
    edges = data.get("edges", [])
    connected_ids: set[str] = set()
    for edge in edges:
        s, t = edge.get("from_id", ""), edge.get("to_id", "")
        if s == req.node_id:
            connected_ids.add(t)
        elif t == req.node_id:
            connected_ids.add(s)

    all_nodes = data.get("nodes", {})
    connected_names = [
        all_nodes[nid]["name"]
        for nid in connected_ids
        if nid in all_nodes and all_nodes[nid].get("source") != "resource"
    ][:5]

    # Fallback: any non-resource nodes in session (if isolated node has no edges yet)
    if not connected_names:
        connected_names = [
            n2.get("name", "") for nid2, n2 in all_nodes.items()
            if nid2 != req.node_id
            and n2.get("source") in ("user", "ai_planned")
            and n2.get("name", "")
        ][:3]

    graph_ctx = " ".join(connected_names)
    query_text = " ".join(filter(None, [node_name, node_desc, goal_context, graph_ctx])).strip()
    if not query_text:
        return {"resources": []}

    filter_langs   = data.get("filter_langs", _ALL_FILTER_LANGS)
    filter_sources = data.get("filter_sources") or None

    try:
        vec = embed(query_text[:500])
        chunks = query_raw_chunks(vec, n=12, filter_langs=filter_langs, filter_sources=filter_sources)
    except Exception:
        return {"resources": []}

    # ── Quality filter helper functions ──────────────────────────────────────
    _NAV_KEYWORDS = re.compile(
        r"(追蹤|購物車|登入|登出|訂單查詢|加入購物|同業|企業|粉絲團|Line@|Youtube|Inst|Twitter"
        r"|aclick|click\?|utm_|廣告|贊助|cookie|policy|privacy)",
        re.IGNORECASE
    )
    _BOILERPLATE_DOMAINS = re.compile(
        r"(bing\.com/aclick|google\.com/aclk|yahoo.*click|doubleclick|googlesyndication"
        r"|facebook\.com|twitter\.com|instagram\.com|linkedin\.com"
        r"|ithelp\.ithome\.com\.tw|cakeresume\.com|104\.com\.tw|1111\.com\.tw"
        r"|cheers\.com\.tw|managertoday\.com\.tw|meet\.jobs|yourator\.com)",
        re.IGNORECASE
    )

    _RE_CJK_ALL = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")

    def _lang_matches(text: str) -> bool:
        """Return True if text language is compatible with the session language."""
        cjk_chars = len(_RE_CJK_ALL.findall(text))
        cjk_ratio = cjk_chars / max(len(text), 1)
        if session_lang == "en":
            return cjk_ratio < 0.2   # reject predominantly CJK for English sessions
        if session_lang == "ja":
            jp_chars = len(re.findall(r"[\u3040-\u30ff]", text))
            return jp_chars > 0 or cjk_ratio < 0.2  # accept Japanese kana or Latin
        return True  # zh-TW: accept all

    def _snippet_quality(text: str) -> float:
        """0.0 (garbage) → 1.0 (high quality)"""
        if not text or len(text) < 40:
            return 0.0
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if not lines:
            return 0.0
        # More than half the lines are short items (≤ 5 chars) → navigation menu
        short_lines = sum(1 for l in lines if len(l) <= 5)
        if short_lines / len(lines) > 0.5:
            return 0.0
        # More than 2 ad/navigation keyword hits → garbage
        nav_hits = len(_NAV_KEYWORDS.findall(text))
        if nav_hits >= 2:
            return 0.1
        # Language-aware content ratio signal
        cjk_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        cjk_ratio = cjk_chars / max(len(text), 1)
        if session_lang == "en":
            # For English sessions: reward Latin-heavy text
            latin_ratio = len(re.findall(r"[a-zA-Z]", text)) / max(len(text), 1)
            content_signal = latin_ratio
        else:
            content_signal = cjk_ratio
        score = min(len(text) / 200, 1.0) * 0.4 + content_signal * 0.4 + (0.2 if nav_hits == 0 else 0)
        return round(score, 3)

    # Title quality filter: paragraphs matching these patterns are unsuitable as titles
    _BAD_TITLE_RE = re.compile(
        r"(NT\$|USD|JPY|\$\d|¥\d|每日|每晚|每人|起跳|優惠|折扣|No\.\d|第\d名|\d+天\d+夜)", re.IGNORECASE
    )

    def _extract_title(text: str) -> str:
        """Extract the first meaningful sentence from a snippet as the title."""
        lines = [l.strip() for l in text.split("\n") if len(l.strip()) >= 10]
        for line in lines:
            if _NAV_KEYWORDS.search(line):
                continue
            if _BAD_TITLE_RE.search(line):
                continue
            cut = re.split(r"[。！？，,!?]", line)[0].strip()
            if len(cut) >= 8:
                cjk_ratio = len(re.findall(r"[\u4e00-\u9fff]", cut)) / max(len(cut), 1)
                if session_lang == "en":
                    # Accept lines that are mostly Latin (low CJK ratio)
                    if cjk_ratio < 0.2:
                        return cut[:50]
                else:
                    if cjk_ratio >= 0.25:
                        return cut[:30]
        return ""

    def _domain_label(src: str) -> str:
        try:
            from urllib.parse import urlparse
            host = urlparse(src).hostname or ""
            host = re.sub(r"^www\.", "", host)
            # Take up to the second-level domain (e.g. housefeel.com.tw → housefeel)
            parts = host.split(".")
            return parts[0] if parts else host
        except Exception:
            return src[:12]

    # ── Language detection → travel filter threshold ──────────────────
    _RE_CJK = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")  # CJK characters (Chinese/Japanese/Korean)

    # "Pure theoretical science" keywords: physics, chemistry, mathematics
    # Contamination rate 0.0% → threshold can be relaxed to 5 (filter almost never triggers, but keeps flexibility)
    _HARD_SCIENCE_KW = re.compile(
        r"(量子|相對論|熱力學|電磁學|薛丁格|波粒|超導|核物理|粒子物理|場論|"
        r"有機化學|無機化學|化學鍵|元素週期表?|電化學|高分子|分析化學|"
        r"微積分|線性代數|機率論|數論|拓撲|微分方程|傅立葉|群論|"
        r"quantum|thermodynamic|electromagnetism|particle.physics|"
        r"organic.chem|inorganic.chem|chemical.bond|"
        r"linear.algebra|calculus|topology|number.theory)",
        re.IGNORECASE,
    )

    def _travel_threshold(text: str) -> int:
        """goal language × domain → travel_score filter threshold.
        Source: populate_and_analyze.py 8760 embedding query samples (DB 2367 chunks)

        ┌──────────────────────────┬────────┬─────────────────────────────────────────┐
        │ Domain                   │ Thresh │ Rationale                               │
        ├──────────────────────────┼────────┼─────────────────────────────────────────┤
        │ Pure English (any domain)│   5    │ DB has almost no English travel chunks   │
        │ Pure theory science (CJK)│   5    │ Physics/chem/math contamination 0.0%    │
        │ Other CJK                │   3    │ Food/code etc 0.1-6.4%; 3 is optimal    │
        └──────────────────────────┴────────┴─────────────────────────────────────────┘
        """
        if not _RE_CJK.search(text):
            return 5  # Pure English/Latin goal
        if _HARD_SCIENCE_KW.search(text):
            return 5  # CJK but confirmed pure theoretical science (physics/chem/math)
        return 3       # All other CJK types (programming/biology/food/adjacent to travel)

    # ── Frontend display category inference (from text content) ──────────────
    _TRAVEL_KW  = re.compile(r"(旅遊|景點|交通|住宿|餐廳|美食|景色|寺廟|神社|旅行|觀光|"
                              r"參觀|門票|入場|行程|旅館|溫泉|海灘|博物館|古蹟|tour|sightseeing)", re.IGNORECASE)
    _LEARN_KW   = re.compile(r"(學習|教學|課程|概念|原理|定義|算法|演算|入門|教程|tutorial|guide|learn)", re.IGNORECASE)
    _NEWS_KW    = re.compile(r"(最新|報導|新聞|消息|公告|發佈|更新|2024|2025|2026)", re.IGNORECASE)
    _PRODUCT_KW = re.compile(r"(購買|推薦|評測|比較|價格|促銷|限時|優惠|product|review)", re.IGNORECASE)
    _CONCEPT_KW = re.compile(r"(定義|是指|概念|理論|解釋|包含|分為|指的是)", re.IGNORECASE)

    def _infer_display_category(text: str, db_cat: str) -> str:
        """Convert DB-stored category to the display category used by frontend catColors.
        Text content takes priority; DB category is used only as a fallback."""
        # Direct DB category mapping
        if db_cat == "concept":
            return "concept"
        if db_cat == "how_to":
            return "learning"
        if db_cat == "event":
            return "news"
        # Infer from text content (travel first, then learning, then news)
        travel_score = len(_TRAVEL_KW.findall(text))
        learn_score  = len(_LEARN_KW.findall(text))
        news_score   = len(_NEWS_KW.findall(text))
        prod_score   = len(_PRODUCT_KW.findall(text))
        concept_score = len(_CONCEPT_KW.findall(text))
        scores = {
            "travel": travel_score,
            "learning": learn_score,
            "news": news_score,
            "product": prod_score,
            "concept": concept_score,
        }
        best = max(scores, key=lambda k: scores[k])
        if scores[best] >= 2:
            return best
        if scores[best] == 1:
            return best
        return "general"

    # ── Geographic conflict filter (prevent Kyoto nodes pulling Osaka/Tokyo/Chiayi content) ────
    # Known city → rival city list (if rival city appears in first 200 chars but goal city does not → hard block)
    _TW_CITIES = ["台北", "台南", "高雄", "台中", "花蓮", "台東", "嘉義",
                  "宜蘭", "基隆", "屏東", "桃園", "新竹", "彰化"]
    _KR_CITIES = ["首爾", "釜山", "제주", "Jeju", "Seoul", "Busan"]
    _JP_OTHERS = ["大阪", "東京", "名古屋", "福岡", "神戸", "横浜", "北海道",
                  "沖縄", "札幌", "仙台", "広島", "神奈川", "千葉", "成田",
                  "埼玉", "茨城", "栃木", "群馬", "愛知", "三重", "岐阜",
                  "静岡", "山梨", "長野", "新潟", "富山", "石川", "福井",
                  "岡山", "山口", "鳥取", "島根", "愛媛", "高知", "徳島", "香川",
                  "佐賀", "長崎", "熊本", "大分", "宮崎", "鹿児島",
                  "osaka", "tokyo", "nagoya", "fukuoka", "hiroshima",
                  "chiba", "narita", "aichi"]
    # Sub-area → parent city (for primary_hits compensation: Arashiyama article may say "Kyoto Arashiyama")
    _AREA_TO_CITY = {
        # Kyoto sub-areas
        "嵐山": "京都", "金閣寺": "京都", "清水寺": "京都", "祇園": "京都",
        "伏見稻荷": "京都", "天龍寺": "京都", "渡月橋": "京都", "哲学の道": "京都",
        "嵯峨野": "京都", "錦市場": "京都", "二条城": "京都",
        # Tokyo sub-areas
        "淺草": "東京", "秋葉原": "東京", "新宿": "東京", "涉谷": "東京",
        "渋谷": "東京", "原宿": "東京", "池袋": "東京", "六本木": "東京",
        # Osaka sub-areas
        "道頓堀": "大阪", "心齋橋": "大阪", "通天閣": "大阪",
        # Taipei sub-areas
        "士林": "台北", "九份": "台北", "淡水": "台北",
    }
    _JP_KYOTO_RIVALS = _JP_OTHERS + _TW_CITIES + _KR_CITIES  # Same rival list as Kyoto

    _GEO_RIVALS: dict[str, list[str]] = {
        "京都": _JP_KYOTO_RIVALS,
        # Kyoto sub-areas: apply the same rivals as Kyoto
        "嵐山": _JP_KYOTO_RIVALS, "金閣寺": _JP_KYOTO_RIVALS, "清水寺": _JP_KYOTO_RIVALS,
        "祇園": _JP_KYOTO_RIVALS, "伏見稻荷": _JP_KYOTO_RIVALS, "天龍寺": _JP_KYOTO_RIVALS,
        "渡月橋": _JP_KYOTO_RIVALS, "嵯峨野": _JP_KYOTO_RIVALS,
        "大阪": ["京都", "東京", "名古屋", "福岡", "神戸", "横浜", "北海道", "沖縄",
                 "kyoto", "tokyo", "nagoya", "fukuoka"] + _TW_CITIES + _KR_CITIES,
        "東京": ["京都", "大阪", "名古屋", "福岡", "神戸", "横浜", "北海道", "沖縄",
                 "kyoto", "osaka", "nagoya", "fukuoka"] + _TW_CITIES + _KR_CITIES,
        "北海道": ["京都", "大阪", "東京", "名古屋", "福岡", "沖縄",
                   "kyoto", "osaka", "tokyo"] + _TW_CITIES + _KR_CITIES,
        "沖縄": ["京都", "大阪", "東京", "名古屋", "福岡", "北海道",
                 "kyoto", "osaka", "tokyo"] + _TW_CITIES + _KR_CITIES,
        "福岡": ["京都", "大阪", "東京", "名古屋", "北海道", "沖縄",
                 "kyoto", "osaka", "tokyo"] + _TW_CITIES + _KR_CITIES,
        "台北": ["台南", "高雄", "台中", "花蓮", "台東", "嘉義"] + _JP_OTHERS + _KR_CITIES,
        "台南": ["台北", "高雄", "台中", "花蓮", "台東"] + _JP_OTHERS,
        "高雄": ["台北", "台南", "台中", "花蓮", "台東"] + _JP_OTHERS,
        "台中": ["台北", "台南", "高雄", "花蓮", "台東"] + _JP_OTHERS,
        "嘉義": ["台北", "台南", "高雄", "台中", "花蓮"] + _JP_OTHERS,
    }

    def _geo_penalty(snippet_text: str, goal_text: str) -> float:
        """Geographic conflict penalty (0.0=none, 1.0=hard block).
        Inspects only the first 200 chars: if goal city/area A is absent but rival city B appears → almost certainly off-topic.
        Sub-areas (e.g. Arashiyama) → also count parent city (Kyoto) primary_hits to avoid false positives."""
        preview     = snippet_text[:200]
        low_preview = preview.lower()
        goal_city   = next((c for c in _GEO_RIVALS if c in goal_text), None)
        if not goal_city:
            return 0.0
        rivals      = _GEO_RIVALS[goal_city]
        rival_hits  = sum(1 for r in rivals if r.lower() in low_preview or r in preview)
        # primary_hits: count goal_city itself + parent city (for sub-area case)
        primary_hits = preview.count(goal_city)
        parent_city  = _AREA_TO_CITY.get(goal_city)
        if parent_city:
            primary_hits += preview.count(parent_city)
        if rival_hits >= 1 and primary_hits == 0:
            return 1.0    # Rival city in first 200 chars but no goal city/parent city → hard block
        if rival_hits >= 2 and primary_hits <= 1:
            return 0.70   # List-style article: piggyback mention
        return 0.0

    def _node_relevance_bonus(snippet_text: str, n_name: str) -> float:
        """If the snippet contains the node name, add a quality bonus (boosts ranking of node-relevant content)."""
        if not n_name or len(n_name) < 2:
            return 0.0
        if n_name in snippet_text:
            return 0.15    # Full node name present → clearly relevant
        if n_name[:2] in snippet_text:
            return 0.06    # First two chars present → possibly relevant
        return 0.0

    # (_topic_mismatch_penalty removed: replaced by expanded _GEO_RIVALS + node_relevance_bonus)

    # ── Main filtering logic ───────────────────────────────────────────────────
    RESOURCE_THRESHOLD = 0.40   # Keep consistent with original; rely on quality filter to remove garbage

    # Session-level cross-node deduplication: the same snippet's first 60 chars must not appear on different nodes
    # (Different chunks from the same URL can go to different nodes as long as the text content differs)
    if "_sat_seen_snippets" not in data:
        data["_sat_seen_snippets"] = {}   # snippet_key → node_id
    sat_global = data["_sat_seen_snippets"]

    # Per-session lock: used only at the final claim step (see below) to prevent race conditions.
    if req.session_id not in _session_sat_locks:
        _session_sat_locks[req.session_id] = threading.Lock()
    sat_lock = _session_sat_locks[req.session_id]

    seen_sources: set[str] = set()
    candidates = []

    for c in chunks:
        dist = c.get("distance", 1.0)
        if dist >= RESOURCE_THRESHOLD:
            continue
        src = c.get("source", "")
        if not src.startswith("http"):
            continue
        if _BOILERPLATE_DOMAINS.search(src):
            continue        # Exclude ad/social media links directly
        if src in seen_sources:
            continue
        # Cross-node dedup: same snippet text (first 60 chars) only — same URL on different nodes is OK
        # (one article can cover multiple topics relevant to different nodes)
        text = c.get("text", "")
        snippet_key = text[:60].strip()
        if snippet_key in sat_global and sat_global[snippet_key] != req.node_id:
            continue

        goal_text = data.get("goal", "")
        geo_p = _geo_penalty(text, goal_text)
        # Hard skip: severe geographic conflict (only rival city in first 200 chars, goal city absent)
        if geo_p >= 1.0:
            continue
        _goal_city    = next((c2 for c2 in _GEO_RIVALS if c2 in goal_text), None)
        _travel_score = len(_TRAVEL_KW.findall(text))
        _learn_score  = len(_LEARN_KW.findall(text))

        # Hard skip①: travel goal but snippet is technical/educational content (no travel keywords)
        if _goal_city and _travel_score == 0 and _learn_score >= 1:
            continue    # Travel goal + educational/technical content → skip

        # Hard skip②: non-travel goal (no known city) but snippet is full of travel keywords
        # Threshold depends on goal language: CJK (Chinese/Japanese/Korean)=3, pure English=5
        # Source: threshold_analysis_v3.py 5960 samples (Chinese 3 is optimal, English almost no travel chunks so relaxed)
        _goal_is_travel = bool(_goal_city) or len(_TRAVEL_KW.findall(goal_text)) >= 2
        _thr = _travel_threshold(goal_text)
        if not _goal_is_travel and _travel_score >= _thr:
            continue    # Non-travel goal + travel snippet → skip

        # Language mismatch filter: skip chunks in the wrong language for this session
        if not _lang_matches(text):
            continue

        quality = _snippet_quality(text)
        # Node name relevance bonus (e.g. Kiyomizudera node: "清水寺" or "清水" in text → +0.15/+0.06)
        quality += _node_relevance_bonus(text, node_name)
        # Penalty for complete absence of node name (3+ char name not mentioned at all → embedding coincidence)
        if len(node_name) >= 3 and node_name not in text and node_name[:2] not in text:
            quality -= 0.12
        # Geographic soft penalty (many rival cities but goal city still present)
        quality -= geo_p
        quality = round(quality, 3)
        if quality < 0.35:
            continue        # Quality too low (raised threshold to filter more noise)

        seen_sources.add(src)
        title = _extract_title(text)
        domain = _domain_label(src)
        db_cat = c.get("category", "general")
        display_cat = _infer_display_category(text, db_cat)
        source_name = c.get("source_name", "")

        candidates.append({
            "id":          f"res_{str(uuid.uuid4())[:6]}",
            "name":        title if title else domain,   # Prefer knowledge summary title
            "domain":      domain,
            "source_url":  src,
            "source_name": source_name,
            "snippet":     text[:180],   # Short version for graph node label
            "full_snippet": text[:400],  # Full version for right-side panel
            "title":       title,
            "distance":    round(dist, 3),
            "quality":     quality,
            "category":    display_cat,
            "parent_id":   req.node_id,
        })
        if len(candidates) >= 6:
            break

    # ── LLM relevance filter: goal-aware geographic/topical filtering ──────────
    # Only triggered when goal has a country-level keyword (日本/台灣/...) to catch cases where
    # embedding alone can't distinguish same-vocabulary cross-country content (e.g. 入山許可: TW vs JP).
    # Semaphore limits concurrency to 2 to avoid Gemini 503 rate-limit storms.
    _goal_text_for_filter = data.get("goal", "")
    if len(candidates) >= 1 and _GOAL_COUNTRY_RE.search(_goal_text_for_filter):
        if _llm_filter_sem.acquire(blocking=False):
            try:
                previews = "\n".join(
                    f"[{i}] {c['full_snippet'][:130]}"
                    for i, c in enumerate(candidates)
                )
                _filter_country = next((c for c in ["日本", "台灣", "韓國", "中國", "美國"] if c in _goal_text_for_filter), None)
                _geo_note = (
                    f"\n判斷標準：片段的「主要內容」是否來自{_filter_country}（不是台灣、中國、韓國或其他地區）。"
                    f"如果片段主要描述{_filter_country}以外地區的制度、機構或資源，則拒絕。"
                ) if _filter_country else ""
                filter_msg = (
                    f"用戶目標：{_goal_text_for_filter[:80]}\n"
                    f"知識節點：{node_name}\n"
                    f"以下知識片段，哪些的主要知識來自{_filter_country or '目標地區'}？"
                    f"{_geo_note}\n"
                    f"回答JSON格式：{{\"keep\":[0,2]}}\n\n{previews}"
                )
                raw = _chat_quick(
                    [{"role": "user", "content": filter_msg}],
                    system="你是知識相關性篩選器。只輸出JSON，不解釋。",
                )
                raw = raw.strip()
                if "```" in raw:
                    raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`")
                keep_list = _json.loads(raw).get("keep", None)
                # Apply if LLM returned a valid list (even empty = "nothing is relevant" → triggers crawl)
                if isinstance(keep_list, list):
                    filtered = [candidates[i] for i in keep_list if 0 <= i < len(candidates)]
                    candidates = filtered
                    print(f"[node_resources] LLM filter: {len(keep_list)} kept / {len(previews.splitlines())} total for '{node_name}'", flush=True)
            except Exception as _fe:
                print(f"[node_resources] LLM filter skip: {_fe.__class__.__name__}: {str(_fe)[:80]}", flush=True)
            finally:
                _llm_filter_sem.release()
        # If semaphore busy → skip filter gracefully (unfiltered result is better than 503 cascade)

    # Sort by quality descending; max satellites depends on node importance
    # ai_planned (required node) → 3; user (explicitly mentioned) → 2; others → 1
    node_source = node.get("source", "user")
    max_sats = 3 if node_source == "ai_planned" else 2 if node_source == "user" else 1
    candidates.sort(key=lambda x: x["quality"], reverse=True)
    # Final claim step: acquire session lock so concurrent node_resources calls don't race.
    # Final claim step: lock prevents concurrent calls from duplicating the same snippet text.
    # Source URL is no longer claimed — same article can appear on multiple nodes with different chunks.
    resources = []
    with sat_lock:
        for r in candidates[:max_sats]:
            key    = r["snippet"][:60].strip()
            key_ok = (not key) or key not in sat_global or sat_global[key] == req.node_id
            if key_ok:
                if key:
                    sat_global[key] = req.node_id
                resources.append(r)

    # ── Generate context-aware satellite titles ───────────────────────────────────────────
    # Default title is the article title, which doesn't reveal the relationship to the parent node.
    # Use LLM to rewrite each satellite's name to describe what it contributes to this specific node.
    if resources:
        try:
            _title_reply_lang = _LANG_MAP.get(session_lang, "English")
            items = "\n".join(
                f"[{i}] Node: {node_name}\nSnippet: {r['snippet'][:120]}"
                for i, r in enumerate(resources)
            )
            raw = _chat_quick(
                [{"role": "user", "content":
                  f"For each snippet below, generate a short title (5-10 words) in {_title_reply_lang} "
                  f"that explains how this snippet relates to the node. Format: [index] Title\n\n{items}"}],
                system=f"Output only lines in format [0] Title, one per line, in {_title_reply_lang}. No explanation.",
            )
            for line in raw.strip().splitlines():
                m = re.match(r'\[(\d+)\]\s*(.+)', line.strip())
                if m:
                    idx, new_title = int(m.group(1)), m.group(2).strip()[:40]
                    if 0 <= idx < len(resources) and new_title:
                        resources[idx]["name"] = new_title
        except Exception:
            pass  # Fall back to original article titles on any failure

    # ── A: No results → trigger background targeted crawl (frontend retries after 15s) ──
    # Normalize to set (JSON serialization converts sets → lists on session restore)
    crawl_pending = set(data.get("_crawl_pending") or [])
    data["_crawl_pending"] = crawl_pending
    crawl_done    = set(data.get("_crawl_done") or [])
    data["_crawl_done"] = crawl_done
    if len(resources) == 0:
        if req.node_id in crawl_done:
            return {"resources": []}          # Already crawled and still no results; stop retrying
        if req.node_id not in crawl_pending:
            goal_text = data.get("goal", "")
            goal_type = "travel" if any(c in goal_text for c in _KNOWN_GOAL_CITIES) else "general"
            topic     = data.get("topic", detect_topic(goal_text))
            crawl_pending.add(req.node_id)
            threading.Thread(
                target=_do_targeted_crawl,
                args=(node_name, node_desc, goal_text, goal_type, data, req.node_id),
                kwargs={"topic": topic, "lang": data.get("lang", "en")},
                daemon=True,
            ).start()
            print(f"[crawl] triggered for node: {node_name!r}", flush=True)
        return {"resources": [], "crawling": True}   # Crawling in progress; frontend waits then retries

    return {"resources": resources}


@app.get("/api/og_image")
def get_og_image(url: str):
    """Fetch og:image from URL (SQLite persistent cache, survives server restarts)."""
    cached = get_og_image_cache(url)
    if cached is not False:          # False = not cached; None = checked but no image; str = image URL
        return {"image_url": cached}
    try:
        import requests as _req
        from bs4 import BeautifulSoup as _BS
        _headers = {"User-Agent": "Mozilla/5.0 (compatible; Ragraphe/0.1)"}
        resp = _req.get(url, headers=_headers, timeout=6)
        soup = _BS(resp.text, "lxml")
        img = None
        for meta in soup.find_all("meta"):
            prop = meta.get("property", "") or meta.get("name", "")
            if prop in ("og:image", "twitter:image", "og:image:url"):
                img = meta.get("content", "").strip() or None
                if img:
                    break
        set_og_image_cache(url, img)
        return {"image_url": img}
    except Exception:
        set_og_image_cache(url, None)
        return {"image_url": None}


@app.get("/api/profile/{user_id}")
def get_profile_api(user_id: str):
    profile = get_profile(user_id)
    goals   = get_recent_goals(user_id, limit=10)
    return {"profile": profile, "goals": goals}


@app.post("/api/profile")
def save_profile_api(req: ProfileRequest):
    upsert_profile(req.user_id, req.name, req.background, req.skills)
    return {"ok": True}


# ── Priority Sources ───────────────────────────────────────────────────────────

@app.get("/api/sources")
def list_sources():
    return {"sources": list_priority_sources()}


@app.post("/api/sources")
def add_source(req: SourceRequest):
    sid = add_priority_source(
        name=req.name, url=req.url,
        goal_types=req.goal_types, keywords=req.keywords,
        vendor_id=req.vendor_id, priority=req.priority,
        category=req.category, ttl_days=req.ttl_days,
    )
    return {"ok": True, "id": sid}


@app.delete("/api/sources/{source_id}")
def delete_source(source_id: str):
    delete_priority_source(source_id)
    return {"ok": True}


# ── Knowledge Base ─────────────────────────────────────────────────────────────

@app.post("/api/knowledge/crawl")
def knowledge_crawl(req: KnowledgeCrawlRequest):
    """Topic crawl (SSE), returns progress in real time."""
    from ragraphe.core.crawler import crawl_node_smart_stream

    def event_stream():
        node = {"name": req.topic, "description": req.topic}
        for ev_type, ev_data in crawl_node_smart_stream(node, req.goal_type):
            if ev_type == "progress":
                yield _sse({"type": "progress", "text": ev_data})
            elif ev_type == "done":
                yield _sse({"type": "done", "chunks": ev_data})

    return StreamingResponse(
        event_stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/knowledge/search")
def knowledge_search(q: str, n: int = 10):
    """Search raw_chunks and return relevant chunks."""
    from ragraphe.core.crawler import query_raw_chunks
    from ragraphe.core.category import CATEGORY_LABEL, TIME_SENSITIVE
    if not q.strip():
        return {"chunks": []}
    try:
        vec = embed(q[:300])
        chunks = query_raw_chunks(vec, n=n)
        return {
            "chunks": [
                {
                    "text":           c["text"][:300],
                    "source":         c["source"],
                    "source_name":    c.get("source_name", ""),
                    "category":       c.get("category", "general"),
                    "category_label": CATEGORY_LABEL.get(c.get("category","general"), "📄"),
                    "time_sensitive": c.get("category","general") in TIME_SENSITIVE,
                    "distance":       round(c["distance"], 3),
                }
                for c in chunks
            ]
        }
    except Exception as e:
        return {"chunks": [], "error": str(e)}


@app.get("/api/knowledge/status")
def knowledge_status():
    """Return knowledge base statistics: chunk count and crawled URL count."""
    from ragraphe.core.crawler import raw_chunks
    return {
        "chunk_count": raw_chunks.count(),
        "url_count":   len(list_crawled_urls(limit=9999)),
        "recent_urls": list_crawled_urls(limit=10),
    }


@app.post("/api/knowledge/url")
def knowledge_add_url(req: KnowledgeURLRequest):
    """Crawl a URL and add its content to the knowledge base."""
    from ragraphe.core.crawler import fetch_text, chunk_text, store_chunks
    url = req.url.strip()
    if not url.startswith("http"):
        return {"ok": False, "error": "Invalid URL"}
    cached = is_url_cached(url)
    if cached:
        return {"ok": True, "chunks": 0, "cached": True}
    text = fetch_text(url)
    if not text:
        return {"ok": False, "error": "Failed to retrieve page content"}
    source = req.source or url
    chunks = chunk_text(text, source)
    # Override the URL with the specified source name (for easier identification)
    if req.source:
        for c in chunks:
            c["source"] = req.source
    store_chunks(chunks)
    mark_url_crawled(url, len(chunks))
    return {"ok": True, "chunks": len(chunks), "cached": False}


@app.post("/api/knowledge/text")
def knowledge_add_text(req: KnowledgeTextRequest):
    """Add text directly to the knowledge base."""
    from ragraphe.core.crawler import chunk_text, store_chunks
    if not req.text.strip():
        return {"ok": False, "error": "Content cannot be empty"}
    # Use a pseudo-source for text imports (makes later listing and deletion easier)
    source = req.source or f"text://import_{uuid.uuid4().hex[:8]}"
    chunks = chunk_text(req.text, source)
    for c in chunks:
        if req.source:
            c["source_name"] = req.source
    store_chunks(chunks, category="concept", ttl_days=0)
    return {"ok": True, "chunks": len(chunks), "source": source}


@app.get("/api/knowledge/sources")
def knowledge_list_sources():
    """List all imported sources (aggregated from ChromaDB)."""
    return {"sources": list_chunk_sources()}


@app.post("/api/knowledge/delete_source")
def knowledge_delete_source(req: KnowledgeDeleteRequest):
    """Delete all chunks for the specified source."""
    if not req.source:
        return {"ok": False, "error": "source cannot be empty"}
    deleted = delete_chunks_by_source(req.source)
    # Also clear the crawled_urls record (so it can be re-crawled next time)
    from ragraphe.db.store import _DBConn
    with _DBConn() as conn:
        conn.execute("DELETE FROM crawled_urls WHERE url = ?", (req.source,))
    return {"ok": True, "deleted": deleted}


@app.post("/api/knowledge/pdf")
async def knowledge_upload_pdf(
    file:        UploadFile = File(...),
    source_name: str        = Form(""),
    category:    str        = Form("concept"),
    session_id:  str        = Form(""),
):
    """Upload PDF → parse → chunk + embed → raw_chunks; file stored in data/files/."""
    from ragraphe.core.crawler import chunk_text, store_chunks

    if not file.filename.lower().endswith(".pdf"):
        return {"ok": False, "error": "Only PDF files are supported"}

    # Save file (use uuid to avoid filename conflicts; preserve original name for display)
    safe_stem = re.sub(r"[^\w\-.]", "_", Path(file.filename).stem)[:60]
    unique_name = f"{uuid.uuid4().hex[:8]}_{safe_stem}.pdf"
    dest = FILES_DIR / unique_name
    content = await file.read()
    dest.write_bytes(content)

    # Parse and chunk page-by-page (no char limit — index entire manual)
    from ragraphe.core.crawler import chunk_text, store_chunks
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(dest))
        display_name = source_name or file.filename
        source_path  = f"/files/{unique_name}"
        all_chunks: list[dict] = []
        for page in reader.pages:
            page_text = (page.extract_text() or "").strip()
            if len(page_text) > 50:
                page_chunks = chunk_text(page_text, source_path)
                for c in page_chunks:
                    c["source_name"] = display_name
                all_chunks.extend(page_chunks)
    except Exception as e:
        dest.unlink(missing_ok=True)
        return {"ok": False, "error": f"Failed to parse PDF: {e}"}

    if not all_chunks:
        dest.unlink(missing_ok=True)
        return {"ok": False, "error": "Failed to extract text from PDF"}

    chunks = all_chunks
    store_chunks(chunks, category=category, ttl_days=0)   # PDFs never expire
    return {
        "ok":       True,
        "chunks":   len(chunks),
        "file_url": source_path,
        "filename": display_name,
    }


@app.post("/api/knowledge/jsonl")
def knowledge_add_jsonl(req: KnowledgeJSONLRequest):
    """Parse JSONL format and add to the knowledge base (one {"text":"...","source":"..."} per line)."""
    from ragraphe.core.crawler import store_chunks
    import uuid as _uuid
    chunks = []
    errors = 0
    for line in req.content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = _json.loads(line)
            text = obj.get("text", "").strip()
            if not text:
                continue
            chunks.append({
                "id":     str(_uuid.uuid4()),
                "text":   text,
                "source": obj.get("source", req.source),
            })
        except Exception:
            errors += 1
    if not chunks:
        return {"ok": False, "error": f"No valid data ({errors} lines failed to parse)"}
    store_chunks(chunks)
    return {"ok": True, "chunks": len(chunks), "errors": errors}


@app.post("/api/knowledge/ask")
def knowledge_ask(req: KnowledgeAskRequest):
    """RAG Q&A: search KB → build context → Gemini → return grounded answer."""
    from ragraphe.core.crawler import query_raw_chunks
    if not req.query.strip():
        return {"answer": "", "sources": [], "chunks_used": 0}
    try:
        vec = embed(req.query[:300])
        chunks = query_raw_chunks(vec, n=req.n)
        if not chunks:
            return {
                "answer": "No relevant content found in the knowledge base for this query.",
                "sources": [],
                "chunks_used": 0,
            }
        # Build context block
        context_parts = []
        for i, c in enumerate(chunks, 1):
            src = c.get("source_name") or c.get("source", "")
            context_parts.append(f"[{i}] (source: {src})\n{c['text'][:600]}")
        context = "\n\n".join(context_parts)

        lang_instruction = {
            "en":    "Answer in English.",
            "zh-TW": "請用繁體中文回答。",
            "ja":    "日本語で回答してください。",
        }.get(req.lang, "Answer in English.")

        system = (
            "You are a precise technical assistant. Answer only based on the provided context. "
            "If the context does not contain enough information, say so clearly. "
            "Cite which source numbers you used (e.g. [1], [3]). "
            f"{lang_instruction}"
        )
        prompt = f"Context:\n{context}\n\nQuestion: {req.query}"
        answer = chat([{"role": "user", "content": prompt}], system=system)

        seen = set()
        sources = []
        for c in chunks:
            src = c.get("source_name") or c.get("source", "")
            if src and src not in seen:
                seen.add(src)
                sources.append(src)

        return {"answer": answer, "sources": sources, "chunks_used": len(chunks)}
    except Exception as e:
        return {"answer": "", "sources": [], "chunks_used": 0, "error": str(e)}


# ── Frontend HTML ─────────────────────────────────────────────────────────────

