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
from fastapi.responses import HTMLResponse, StreamingResponse
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

app = FastAPI()
app.mount("/files", StaticFiles(directory=str(FILES_DIR)), name="files")

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
    url:    str
    source: str = ""   # Display name; defaults to the URL


class KnowledgeTextRequest(BaseModel):
    text:   str
    source: str = "手動輸入"


class KnowledgeJSONLRequest(BaseModel):
    content: str        # JSONL text, one {"text":"...","source":"..."} per line
    source:  str = "匯入"  # Used when a line has no source field


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
    embeddings: dict, n_probes: int = 3, n_results: int = 3
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
            chunks = query_raw_chunks(probe, n=n_results)
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
            raw = chat(
                system=_CHAT_EXTRACT_SYSTEM,
                messages=[{"role": "user", "content": _CHAT_EXTRACT_PROMPT.format(
                    reply_lang=reply_lang, node_lang=node_lang,
                    goal=goal, history=history_text,
                    message=user_text, existing_names=existing_names_json,
                    known_concepts_block=known_concepts_block,
                )}],
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
                best_ca, best_cb, snap_embs, n_probes=3, n_results=3
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
    return HTMLResponse(FRONTEND_HTML)


@app.post("/api/start")
def start(req: StartRequest):
    from datetime import datetime as _dt
    session_id = str(uuid.uuid4())[:8]
    sessions[session_id] = {
        "goal":         req.goal,
        "user_id":      req.user_id,
        "lang":         req.lang,
        "created_at":   _dt.now().isoformat(),
        "messages":     [],
        "nodes":        {},      # id → {id, name, description, status, source, exclusive}
        "embeddings":   {},      # id → list[float]
        "edge_set":     set(),   # frozenset({id1, id2}) for dedup
        "edges":        [],      # [{id, from_id, to_id, is_parent?}]
        "decisions":    [],      # [{selected_ids, skipped_ids, deferred_ids, reason}]
        "node_coverage":{},      # id → float (0.0~1.0), degree to which node is covered by conversation
    }

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


def _do_targeted_crawl(node_name: str, node_desc: str, goal_text: str,
                       goal_type: str, session_data: dict, node_id: str) -> None:
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

        # Determine Wikipedia language from goal country (e.g. Japan → "ja")
        wiki_lang = next(
            (lang for kw, lang in _COUNTRY_WIKI_LANG.items() if kw in goal_text),
            "zh"
        )

        pseudo_node = {"name": search_name, "description": node_desc}
        crawl_node_smart(pseudo_node, goal_type=goal_type, verbose=True, wiki_lang=wiki_lang)
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

    try:
        vec = embed(query_text[:500])
        chunks = query_raw_chunks(vec, n=12)
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
        # CJK character ratio: travel knowledge typically > 30%
        zh_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        zh_ratio = zh_chars / max(len(text), 1)
        # Quality score: length + CJK ratio + no ads
        score = min(len(text) / 200, 1.0) * 0.4 + zh_ratio * 0.4 + (0.2 if nav_hits == 0 else 0)
        return round(score, 3)

    # Title quality filter: paragraphs matching these patterns are unsuitable as titles
    _BAD_TITLE_RE = re.compile(
        r"(NT\$|USD|JPY|\$\d|¥\d|每日|每晚|每人|起跳|優惠|折扣|No\.\d|第\d名|\d+天\d+夜)", re.IGNORECASE
    )

    def _extract_title(text: str) -> str:
        """Extract the first meaningful sentence from a snippet as the title, filtering out price/ranking fragments."""
        lines = [l.strip() for l in text.split("\n") if len(l.strip()) >= 10]
        for line in lines:
            # Skip ad/navigation lines
            if _NAV_KEYWORDS.search(line):
                continue
            # Skip lines containing price/ranking info (prone to truncated titles like "Tokyo daily NT$2")
            if _BAD_TITLE_RE.search(line):
                continue
            # Truncate at first period/comma
            cut = re.split(r"[。！？，,!?]", line)[0].strip()
            # Title must be at least 8 chars and CJK ratio > 30% (exclude all-ASCII noise lines)
            if len(cut) >= 8:
                zh_ratio = len(re.findall(r"[\u4e00-\u9fff]", cut)) / max(len(cut), 1)
                if zh_ratio >= 0.25:
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

        candidates.append({
            "id":         f"res_{str(uuid.uuid4())[:6]}",
            "name":       title if title else domain,   # Prefer knowledge summary title
            "domain":     domain,
            "source_url": src,
            "snippet":    text[:180],   # Short version for graph node label
            "full_snippet": text[:400], # Full version for right-side panel
            "title":      title,
            "distance":   round(dist, 3),
            "quality":    quality,
            "category":   display_cat,
            "parent_id":  req.node_id,
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
            items = "\n".join(
                f"[{i}] 節點：{node_name}\n片段：{r['snippet'][:120]}"
                for i, r in enumerate(resources)
            )
            raw = _chat_quick(
                [{"role": "user", "content":
                  f"為以下知識片段各生成一個標題（5-10字），說明這個片段與節點的關係，讓讀者一眼看出關聯。\n"
                  f"格式：[序號] 標題\n\n{items}"}],
                system="只輸出格式為[0] 標題的短標題，每行一個，不加解釋。",
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
            crawl_pending.add(req.node_id)
            threading.Thread(
                target=_do_targeted_crawl,
                args=(node_name, node_desc, goal_text, goal_type, data, req.node_id),
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
):
    """Upload PDF → parse → chunk + embed → raw_chunks; file stored in data/files/."""
    from ragraphe.core.crawler import parse_pdf, chunk_text, store_chunks

    if not file.filename.lower().endswith(".pdf"):
        return {"ok": False, "error": "Only PDF files are supported"}

    # Save file (use uuid to avoid filename conflicts; preserve original name for display)
    safe_stem = re.sub(r"[^\w\-.]", "_", Path(file.filename).stem)[:60]
    unique_name = f"{uuid.uuid4().hex[:8]}_{safe_stem}.pdf"
    dest = FILES_DIR / unique_name
    content = await file.read()
    dest.write_bytes(content)

    # Parse and chunk
    text = parse_pdf(str(dest))
    if not text.strip():
        dest.unlink(missing_ok=True)
        return {"ok": False, "error": "Failed to extract text from PDF"}

    display_name = source_name or file.filename
    source_path  = f"/files/{unique_name}"   # Browser-accessible path

    chunks = chunk_text(text, source_path)
    # Include display name in each chunk's metadata for frontend use
    for c in chunks:
        c["source_name"] = display_name

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


# ── Frontend HTML ─────────────────────────────────────────────────────────────

FRONTEND_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>Ragraphe</title>
<script src="https://unpkg.com/force-graph@1"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: #060a12; color: #e2e8f0;
         font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         height: 100vh; overflow: hidden; }

  /* ── Main App ── */
  #app { display: flex; flex-direction: row; height: 100vh; }
  #graph-pane { flex: 1; position: relative; }
  #graph-canvas { width: 100%; height: 100%; }
  #welcome-overlay {
    position: absolute; inset: 0; display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    pointer-events: none;
    transition: opacity 0.4s;
    z-index: 10;
  }
  #welcome-overlay.hidden { opacity: 0; pointer-events: none; }
  #welcome-overlay.interactive { pointer-events: auto; }
  #welcome-overlay h1 {
    font-size: 48px; font-weight: 800; color: #f8fafc;
    letter-spacing: 4px; margin-bottom: 8px;
  }
  #welcome-overlay p { color: #94a3b8; font-size: 14px; margin-bottom: 0; }
  #onboarding-card {
    margin-top: 28px;
    background: rgba(13,20,36,0.92); border: 1px solid #1e3a5f;
    border-radius: 14px; padding: 22px 28px 18px; max-width: 400px; width: 90%;
    backdrop-filter: blur(8px);
  }
  .ob-steps { list-style: none; padding: 0; margin: 0 0 16px; }
  .ob-steps li {
    display: flex; align-items: flex-start; gap: 10px;
    color: #cbd5e1; font-size: 13px; padding: 5px 0; line-height: 1.5;
  }
  .ob-step-num {
    width: 22px; height: 22px; border-radius: 50%; background: #1e3a5f;
    color: #60a5fa; font-size: 11px; font-weight: 700;
    display: flex; align-items: center; justify-content: center; flex-shrink: 0;
    margin-top: 1px;
  }
  .ob-legend { display: flex; flex-wrap: wrap; gap: 8px 16px; margin-bottom: 16px; }
  .ob-dot {
    display: flex; align-items: center; gap: 6px;
    font-size: 11px; color: #94a3b8;
  }
  .ob-dot span {
    width: 10px; height: 10px; border-radius: 50%; display: inline-block;
  }
  #ob-dismiss-btn {
    width: 100%; padding: 9px; background: #1e3a5f; border: 1px solid #2563eb;
    border-radius: 8px; color: #93c5fd; font-size: 13px; font-weight: 600;
    cursor: pointer; transition: background 0.2s;
  }
  #ob-dismiss-btn:hover { background: #2563eb; color: #fff; }
  /* ── 完成摘要卡 ── */
  .msg-complete {
    margin: 12px 0 6px; padding: 14px 16px;
    background: linear-gradient(135deg, #0a1f0a 0%, #0a1427 100%);
    border: 1px solid #22c55e; border-radius: 10px;
  }
  .msg-complete-title {
    font-size: 14px; font-weight: 700; color: #4ade80; margin-bottom: 10px;
  }
  .msg-complete-stats {
    display: flex; gap: 14px; margin-bottom: 12px; flex-wrap: wrap;
  }
  .mcs-item { display: flex; flex-direction: column; align-items: center; }
  .mcs-num { font-size: 22px; font-weight: 700; line-height: 1; }
  .mcs-label { font-size: 10px; color: #64748b; margin-top: 2px; }
  .mcs-done { color: #4ade80; }
  .mcs-todo { color: #60a5fa; }
  .mcs-skip { color: #94a3b8; }
  .msg-complete-export {
    width: 100%; padding: 8px; background: #0d2f0d; border: 1px solid #16a34a;
    border-radius: 7px; color: #4ade80; font-size: 12px; font-weight: 600;
    cursor: pointer; transition: background 0.2s;
  }
  .msg-complete-export:hover { background: #14532d; }

  /* ── Image Bubbles（節點 RAG 圖片浮動小卡）── */
  .img-bubble {
    position: absolute; width: 90px; height: 68px;
    border-radius: 8px; overflow: hidden;
    border: 2px solid #3b82f6; background: #0f172a;
    cursor: pointer; z-index: 20;
    box-shadow: 0 0 14px rgba(59,130,246,0.45);
    transition: transform 0.15s, box-shadow 0.15s;
    pointer-events: auto;
  }
  .img-bubble:hover { transform: scale(1.12); box-shadow: 0 0 22px rgba(59,130,246,0.75); }
  .img-bubble img { width: 100%; height: 100%; object-fit: cover; display: block; }

  /* ── Hover Tooltip ── */
  #hover-tooltip {
    position: absolute; pointer-events: none; z-index: 45;
    background: rgba(5,10,20,0.92); border: 1px solid #1e3a5f;
    border-radius: 8px; padding: 8px 12px; max-width: 200px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.6);
    display: none; animation: tooltipIn 0.1s ease;
  }
  #hover-tooltip.visible { display: block; }
  @keyframes tooltipIn {
    from { opacity: 0; transform: translateY(4px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  #hover-tooltip .ht-name {
    font-size: 12px; font-weight: 700; color: #f1f5f9; margin-bottom: 4px; line-height: 1.4;
  }
  #hover-tooltip .ht-desc {
    font-size: 11px; color: #64748b; line-height: 1.5; margin-bottom: 4px;
  }
  #hover-tooltip .ht-hint {
    font-size: 10px; color: #38bdf8; letter-spacing: 0.3px;
  }
  #hover-tooltip .ht-hint.has-rag { color: #4ade80; }

  /* ── Node Popup ── */
  #node-popup {
    position: absolute; display: none; z-index: 50;
    background: #0a0e18; border: 1px solid #1e3a5f; border-radius: 10px;
    padding: 14px 16px; width: 220px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.6);
    animation: popupIn 0.15s ease;
  }
  #node-popup.visible { display: block; }
  @keyframes popupIn {
    from { opacity: 0; transform: scale(0.95) translateY(4px); }
    to   { opacity: 1; transform: scale(1) translateY(0); }
  }
  #node-popup .np-title {
    font-size: 13px; font-weight: 700; color: #f1f5f9;
    margin-bottom: 6px; line-height: 1.4; padding-right: 20px;
  }
  #node-popup .np-close {
    position: absolute; top: 10px; right: 12px;
    background: none; border: none; color: #475569;
    font-size: 14px; cursor: pointer; line-height: 1;
  }
  #node-popup .np-close:hover { color: #f1f5f9; }
  #node-popup .np-desc {
    font-size: 12px; color: #64748b; line-height: 1.55; margin-bottom: 8px;
  }
  #node-popup .np-skip-btn {
    display: block; width: 100%; padding: 5px 0; margin-bottom: 8px;
    background: none; border: 1px solid #374151; border-radius: 5px;
    color: #4b5563; font-size: 11px; cursor: pointer; transition: all 0.15s;
  }
  #node-popup .np-skip-btn:hover { border-color: #f59e0b; color: #f59e0b; }
  #node-popup .np-skip-btn.skipped { border-color: #374151; color: #374151; cursor: default; }
  /* ── Node Detail Pane（右側 RAG 資訊區）── */
  #node-detail-pane {
    display: none; flex-direction: column;
    flex-shrink: 0; height: 260px;
    border-top: 1px solid #1e3a5f;
    background: #060a14;
  }
  #node-detail-pane.visible { display: flex; }
  #ndp-header {
    display: flex; align-items: center; gap: 8px;
    padding: 8px 14px; border-bottom: 1px solid #0f1f38; flex-shrink: 0;
    background: #080c16;
  }
  #ndp-title { font-size: 13px; font-weight: 700; color: #f1f5f9; flex: 1; min-width: 0;
               white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  #ndp-close {
    background: none; border: none; color: #475569;
    font-size: 14px; cursor: pointer; line-height: 1; padding: 0 2px; flex-shrink: 0;
  }
  #ndp-close:hover { color: #f1f5f9; }
  #ndp-body { flex: 1; overflow-y: auto; padding: 10px 14px; display: flex; flex-direction: column; gap: 6px; }
  .np-rag-label {
    font-size: 10px; color: #38bdf8; text-transform: uppercase;
    letter-spacing: 1px; margin-bottom: 2px; font-weight: 600; flex-shrink: 0;
  }
  .np-chunk {
    background: #040710; border: 1px solid #0f1f38;
    border-left: 3px solid #1e3a5f;
    border-radius: 6px; padding: 8px 10px; flex-shrink: 0;
    transition: border-color 0.15s;
  }
  .np-chunk:hover { border-left-color: #38bdf8; }
  .np-chunk.cat-travel { border-left-color: #0ea5e9; }
  .np-chunk.cat-learning { border-left-color: #8b5cf6; }
  .np-chunk.cat-concept { border-left-color: #10b981; }
  .np-chunk.cat-news { border-left-color: #f59e0b; }
  .np-chunk.cat-product { border-left-color: #f97316; }
  .np-chunk-text {
    font-size: 11px; color: #94a3b8; line-height: 1.6;
    display: -webkit-box; -webkit-line-clamp: 4;
    -webkit-box-orient: vertical; overflow: hidden;
  }
  .np-chunk-footer {
    display: flex; align-items: center; gap: 6px; margin-top: 5px;
  }
  .np-chunk-cat {
    font-size: 9px; color: #334155; background: #0a1628;
    border: 1px solid #0f1f38; border-radius: 3px; padding: 1px 4px;
    flex-shrink: 0; text-transform: uppercase; letter-spacing: 0.5px;
  }
  .np-chunk-src {
    font-size: 10px; color: #334155; flex: 1;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  a.np-chunk-src:hover { color: #93c5fd; }

  /* ── Chat Panel ── */
  #chat-pane {
    width: 340px; min-width: 340px; height: 100vh;
    background: #0a0e18; border-left: 1px solid #1e293b;
    display: flex; flex-direction: column;
  }
  #chat-header {
    padding: 10px 14px 8px; border-bottom: 1px solid #1e293b;
    background: #080c16; flex-shrink: 0;
    display: flex; flex-direction: column; gap: 6px;
  }
  #chat-header-toolbar {
    display: flex; align-items: center; justify-content: flex-end; gap: 4px;
  }
  #chat-header-goal {
    display: flex; align-items: baseline; gap: 8px;
    min-width: 0;
  }
  .header-label { font-size: 10px; color: #38bdf8; text-transform: uppercase;
                   letter-spacing: 1.5px; flex-shrink: 0; }
  #goal-display { font-size: 13px; font-weight: 600; color: #f1f5f9; line-height: 1.4;
                   white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; }

  #messages {
    flex: 1; overflow-y: auto; padding: 14px;
    display: flex; flex-direction: column; gap: 8px;
  }

  .msg { max-width: 88%; padding: 10px 14px; border-radius: 12px;
          font-size: 13px; line-height: 1.65; word-break: break-word; }
  .msg-ai   { background: #0f2744; border: 1px solid #1e3a5f; color: #93c5fd;
               align-self: flex-start; border-radius: 4px 12px 12px 12px; }
  .msg-ai.ai-off-topic { background: #111; border-color: #333; color: #6b7280;
               font-style: italic; }
  .msg-user { background: #1a3a1a; border: 1px solid #1c4a1c; color: #86efac;
               align-self: flex-end; border-radius: 12px 4px 12px 12px; }
  .msg-system { background: #1a1200; border: 1px solid #3d2800; color: #fbbf24;
                 align-self: center; font-size: 12px; text-align: center;
                 border-radius: 8px; max-width: 96%; }
  .msg-retry  { background: #1a0a0a; border: 1px solid #7f1d1d; color: #fca5a5;
                 align-self: center; font-size: 12px; text-align: center;
                 border-radius: 8px; max-width: 96%;
                 display: flex; align-items: center; gap: 10px; justify-content: center; }
  .node-ref   { color: #7dd3fc; border-bottom: 1px dashed #7dd3fc55;
                 cursor: pointer; transition: color .15s; }
  .node-ref:hover { color: #fff; border-bottom-color: #fff; }
  .msg-retry button { background: #7f1d1d; color: #fecaca; border: 1px solid #991b1b;
                       border-radius: 6px; padding: 3px 10px; font-size: 12px;
                       cursor: pointer; white-space: nowrap; }
  .msg-retry button:hover { background: #991b1b; }
  .msg-loading  { color: #334155; font-style: italic; font-size: 13px; align-self: flex-start; }
  .msg-stream   { color: #475569; font-style: italic; font-size: 13px; align-self: flex-start;
                   background: #080c16; border: 1px solid #1e293b; border-radius: 4px 12px 12px 12px;
                   padding: 8px 12px; max-width: 88%; transition: color 0.2s; }
  .msg-stream.active { color: #60a5fa; border-color: #1e3a5f; }

  /* Node detail card (in chat) */
  .msg-node {
    background: #080c16; border: 1px solid #1e293b; color: #94a3b8;
    align-self: stretch; border-radius: 8px; max-width: 100%; padding: 12px 14px;
  }
  .nd-title { font-size: 14px; font-weight: 700; color: #f8fafc; margin-bottom: 6px; }
  .nd-badge { font-size: 11px; padding: 2px 9px; border-radius: 99px;
               display: inline-block; margin-bottom: 8px; }
  .nd-desc  { font-size: 12px; color: #64748b; margin-bottom: 6px; line-height: 1.5; }
  .nd-reason { font-size: 12px; color: #94a3b8; border-left: 3px solid #1e3a5f;
                padding-left: 10px; margin-bottom: 8px; line-height: 1.5; }
  .nd-expand { display: block; width: 100%; padding: 7px;
                background: #0f2744; border: 1px solid #2563eb; border-radius: 6px;
                color: #60a5fa; font-size: 12px; cursor: pointer; text-align: center; }
  .nd-expand:hover { background: #1e3a5f; }

  /* Status badge colours */
  .s-done    { background: #14532d; color: #4ade80; }
  .s-todo    { background: #0f2744; color: #60a5fa; }
  .s-skip    { background: #1c1c1c; color: #4b5563; }
  .s-unknown { background: #2d1a00; color: #fcd34d; }
  .s-source, .s-sink { background: #0a1f38; color: #93c5fd; }

  #input-area {
    padding: 12px 14px; border-top: 1px solid #1e293b;
    display: flex; gap: 8px; flex-shrink: 0;
  }
  #msg-input {
    flex: 1; padding: 10px 14px; background: #0f1724;
    border: 1px solid #1e293b; border-radius: 8px; color: #f1f5f9;
    font-size: 13px; outline: none; transition: border-color 0.2s;
  }
  #msg-input:focus { border-color: #2563eb; }
  #msg-input:disabled { opacity: 0.4; }
  #send-btn {
    padding: 10px 16px; background: #1d4ed8; border: none;
    border-radius: 8px; color: white; font-size: 13px;
    cursor: pointer; white-space: nowrap; transition: background 0.2s;
  }
  #send-btn:hover:not(:disabled) { background: #2563eb; }
  #send-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  ::-webkit-scrollbar { width: 5px; }
  ::-webkit-scrollbar-thumb { background: #1e293b; border-radius: 3px; }

  /* ── Profile Panel ── */
  #profile-btn {
    background: none; border: none; cursor: pointer; padding: 4px;
    color: #475569; transition: color 0.2s; line-height: 1;
  }
  #profile-btn:hover { color: #93c5fd; }
  #profile-panel {
    position: fixed; inset: 0; background: rgba(6,10,18,0.85);
    z-index: 200; display: none; align-items: flex-start; justify-content: flex-end;
  }
  #profile-panel.open { display: flex; }
  #profile-inner {
    width: 360px; height: 100vh; background: #0a0e18;
    border-left: 1px solid #1e293b; display: flex; flex-direction: column;
    overflow: hidden;
  }
  #profile-header {
    padding: 16px 20px; border-bottom: 1px solid #1e293b;
    display: flex; align-items: center; justify-content: space-between;
  }
  #profile-header h2 { font-size: 15px; font-weight: 700; color: #f1f5f9; }
  #profile-close {
    background: none; border: none; color: #475569; cursor: pointer;
    font-size: 18px; line-height: 1; padding: 2px 6px;
  }
  #profile-close:hover { color: #f1f5f9; }
  #profile-body { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
  .pf-label { font-size: 10px; color: #38bdf8; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; }
  .pf-input, .pf-textarea {
    width: 100%; background: #060a12; border: 1px solid #1e293b;
    border-radius: 8px; color: #f1f5f9; font-size: 13px; padding: 9px 12px;
    outline: none; resize: none; font-family: inherit;
    transition: border-color 0.2s;
  }
  .pf-input:focus, .pf-textarea:focus { border-color: #2563eb; }
  .pf-textarea { min-height: 80px; }
  .pf-skills { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
  .pf-tag {
    background: #0f2744; border: 1px solid #1e3a5f; color: #60a5fa;
    border-radius: 99px; font-size: 11px; padding: 3px 10px;
    display: flex; align-items: center; gap: 4px;
  }
  .pf-tag-del { cursor: pointer; color: #334155; font-size: 13px; }
  .pf-tag-del:hover { color: #f87171; }
  .pf-skill-input {
    flex: 1; min-width: 80px; background: none; border: none;
    color: #f1f5f9; font-size: 12px; outline: none;
  }
  .pf-skill-row {
    display: flex; align-items: center; gap: 6px;
    background: #060a12; border: 1px solid #1e293b; border-radius: 8px; padding: 6px 10px;
  }
  #profile-save-btn {
    width: 100%; padding: 10px; background: #1d4ed8; border: none;
    border-radius: 8px; color: white; font-size: 13px; font-weight: 600;
    cursor: pointer; transition: background 0.2s;
  }
  #profile-save-btn:hover { background: #2563eb; }
  .pf-history-item {
    padding: 9px 12px; background: #060a12; border: 1px solid #1e293b;
    border-radius: 8px; cursor: pointer; transition: border-color 0.2s;
  }
  .pf-history-item:hover { border-color: #2563eb; }
  .pf-history-goal { font-size: 13px; color: #e2e8f0; margin-bottom: 3px; }
  .pf-history-meta { font-size: 11px; color: #334155; }
  .pf-type-badge {
    display: inline-block; font-size: 10px; padding: 1px 7px;
    border-radius: 99px; background: #0f2744; color: #60a5fa; margin-right: 6px;
  }

  /* ── Knowledge Panel ── */
  #kb-btn {
    background: none; border: none; cursor: pointer; padding: 4px;
    color: #475569; transition: color 0.2s; line-height: 1;
  }
  #kb-btn:hover { color: #34d399; }
  #kb-panel {
    position: fixed; inset: 0; background: rgba(6,10,18,0.85);
    z-index: 200; display: none; align-items: flex-start; justify-content: flex-end;
  }
  #kb-panel.open { display: flex; }
  #kb-inner {
    width: 480px; height: 100vh; background: #0a0e18;
    border-left: 1px solid #1e293b; display: flex; flex-direction: column;
    overflow: hidden;
  }
  #kb-header {
    padding: 16px 20px; border-bottom: 1px solid #1e293b;
    display: flex; align-items: center; justify-content: space-between;
  }
  #kb-header h2 { font-size: 15px; font-weight: 700; color: #f1f5f9; }
  #kb-header-right { display: flex; align-items: center; gap: 10px; }
  #kb-close {
    background: none; border: none; color: #475569; cursor: pointer;
    font-size: 18px; line-height: 1; padding: 2px 6px;
  }
  #kb-close:hover { color: #f1f5f9; }
  #kb-stats { font-size: 11px; color: #334155; }
  #kb-body { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 20px; }
  .kb-section-title { font-size: 10px; color: #38bdf8; text-transform: uppercase;
                       letter-spacing: 1px; margin-bottom: 10px; font-weight: 600; }
  .kb-card { background: #060a12; border: 1px solid #1e293b; border-radius: 8px; padding: 14px; }
  .kb-tabs { display: flex; gap: 2px; background: #060a12; border: 1px solid #1e293b;
              border-radius: 8px; padding: 3px; }
  .kb-tab {
    flex: 1; padding: 7px; background: none; border: none; border-radius: 6px;
    color: #475569; font-size: 12px; cursor: pointer; transition: all 0.15s;
  }
  .kb-tab.active { background: #0f2744; color: #60a5fa; }
  .kb-tab-content { display: none; padding-top: 12px; }
  .kb-tab-content.active { display: flex; flex-direction: column; gap: 8px; }
  .kb-input, .kb-textarea {
    width: 100%; background: #0a0e18; border: 1px solid #1e293b; border-radius: 6px;
    color: #f1f5f9; font-size: 12px; padding: 8px 10px; outline: none; resize: none;
    font-family: inherit; transition: border-color 0.2s;
  }
  .kb-input:focus, .kb-textarea:focus { border-color: #2563eb; }
  .kb-textarea { min-height: 120px; font-size: 11px; }
  .kb-btn {
    width: 100%; padding: 9px; background: #065f46; border: none;
    border-radius: 6px; color: #34d399; font-size: 12px; font-weight: 600;
    cursor: pointer; transition: background 0.2s;
  }
  .kb-btn:hover { background: #047857; }
  .kb-result { font-size: 11px; padding: 6px 8px; border-radius: 5px; }
  .kb-result.ok  { background: #022c22; color: #34d399; }
  .kb-result.err { background: #3f1111; color: #f87171; }
  .kb-url-row { font-size: 11px; color: #334155; padding: 5px 0;
                 border-bottom: 1px solid #0f1724; white-space: nowrap;
                 overflow: hidden; text-overflow: ellipsis; }

  /* ── Admin Panel ── */
  #admin-btn {
    background: none; border: none; cursor: pointer; padding: 4px;
    color: #475569; transition: color 0.2s; line-height: 1;
  }
  #admin-btn:hover { color: #fbbf24; }
  #admin-panel {
    position: fixed; inset: 0; background: rgba(6,10,18,0.85);
    z-index: 200; display: none; align-items: flex-start; justify-content: flex-end;
  }
  #admin-panel.open { display: flex; }
  #admin-inner {
    width: 480px; height: 100vh; background: #0a0e18;
    border-left: 1px solid #1e293b; display: flex; flex-direction: column;
    overflow: hidden;
  }
  #admin-header {
    padding: 16px 20px; border-bottom: 1px solid #1e293b;
    display: flex; align-items: center; justify-content: space-between;
  }
  #admin-header h2 { font-size: 15px; font-weight: 700; color: #f1f5f9; }
  #admin-close {
    background: none; border: none; color: #475569; cursor: pointer;
    font-size: 18px; line-height: 1; padding: 2px 6px;
  }
  #admin-close:hover { color: #f1f5f9; }
  #admin-body { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
  .src-card {
    background: #060a12; border: 1px solid #1e293b; border-radius: 8px; padding: 12px 14px;
    display: flex; align-items: flex-start; gap: 10px;
  }
  .src-card-info { flex: 1; min-width: 0; }
  .src-name { font-size: 13px; font-weight: 600; color: #e2e8f0; margin-bottom: 2px; }
  .src-url  { font-size: 11px; color: #334155; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .src-meta { font-size: 11px; color: #475569; margin-top: 4px; }
  .src-del-btn {
    background: none; border: 1px solid #3f1111; border-radius: 6px;
    color: #f87171; font-size: 11px; cursor: pointer; padding: 4px 8px; white-space: nowrap;
    flex-shrink: 0; transition: background 0.2s;
  }
  .src-del-btn:hover { background: #3f1111; }
  .src-add-form {
    background: #060a12; border: 1px solid #1e3a5f; border-radius: 8px; padding: 14px;
    display: flex; flex-direction: column; gap: 10px;
  }
  .src-form-row { display: flex; gap: 8px; }
  .src-form-input, .src-form-select {
    flex: 1; background: #0a0e18; border: 1px solid #1e293b; border-radius: 6px;
    color: #f1f5f9; font-size: 12px; padding: 7px 10px; outline: none;
    transition: border-color 0.2s;
  }
  .src-form-input:focus { border-color: #2563eb; }
  .src-form-input.narrow { flex: 0 0 80px; }
  .src-add-btn {
    width: 100%; padding: 9px; background: #1d4ed8; border: none;
    border-radius: 6px; color: white; font-size: 13px; font-weight: 600;
    cursor: pointer; transition: background 0.2s;
  }
  .src-add-btn:hover { background: #2563eb; }

  /* ── 重新規劃按鈕 ── */
  #restart-btn {
    display: none; width: calc(100% - 28px); margin: 0 14px 6px;
    padding: 10px; background: #0f2744; border: 1px solid #2563eb;
    border-radius: 8px; color: #60a5fa; font-size: 13px; font-weight: 600;
    cursor: pointer; transition: background 0.2s; flex-shrink: 0;
  }
  #restart-btn:hover { background: #1e3a5f; }

  /* ── 匯出 Prompt 按鈕 ── */
  #export-prompt-btn {
    display: none; width: calc(100% - 28px); margin: 0 14px 12px;
    padding: 9px; background: #0d1f0d; border: 1px solid #22c55e;
    border-radius: 8px; color: #4ade80; font-size: 12px; font-weight: 600;
    cursor: pointer; transition: background 0.2s; flex-shrink: 0;
  }
  #export-prompt-btn:hover { background: #14301a; }
  #export-prompt-btn:disabled { opacity: 0.5; cursor: default; }

  /* ── 撤銷按鈕 ── */
  #undo-btn {
    display: none; width: calc(100% - 28px); margin: 0 14px 6px;
    padding: 9px; background: #1a1200; border: 1px solid #b45309;
    border-radius: 8px; color: #fbbf24; font-size: 12px; font-weight: 600;
    cursor: pointer; transition: background 0.2s; flex-shrink: 0;
  }
  #undo-btn:hover { background: #2a1f00; }
  #undo-btn:disabled { opacity: 0.4; cursor: default; }

  /* ── Debug Panel ── */
  #debug-toggle {
    position: absolute; bottom: 60px; right: 8px;
    background: rgba(80,80,80,0.3); color: #888; border: 1px solid #444;
    border-radius: 4px; font-size: 11px; padding: 2px 6px; cursor: pointer;
    z-index: 10;
  }
  #debug-toggle:hover { background: rgba(100,100,100,0.5); color: #ccc; }
  #debug-panel {
    display: none; position: absolute; bottom: 88px; left: 0; right: 0;
    max-height: 220px; background: #0d1117;
    border-top: 1px solid #333; font-size: 11px; font-family: monospace;
    color: #8b9; z-index: 9; flex-direction: column;
  }
  #debug-panel.open { display: flex; }
  #debug-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 3px 8px; background: #161b22; border-bottom: 1px solid #333; flex-shrink: 0;
  }
  #debug-header span { color: #5af; font-weight: bold; font-size: 11px; }
  #debug-hide-btn {
    background: none; border: none; color: #666; font-size: 13px;
    cursor: pointer; padding: 0 2px; line-height: 1;
  }
  #debug-hide-btn:hover { color: #ccc; }
  #debug-body { overflow-y: auto; padding: 6px 8px; max-height: 190px; }
  .dbg-entry { margin-bottom: 6px; border-bottom: 1px solid #1e2a1e; padding-bottom: 4px; }
  .dbg-stage { color: #5af; font-weight: bold; }
  .dbg-error { color: #f66; }
  .dbg-key { color: #aaa; }
  .dbg-val { color: #8b9; }

  /* ── Sessions Panel ── */
  #sessions-panel {
    display: none; position: fixed; inset: 0; z-index: 9000;
    background: rgba(0,0,0,0.55); align-items: flex-start; justify-content: flex-end;
  }
  #sessions-panel.open { display: flex; }
  #sessions-inner {
    background: #0d1424; border-left: 1px solid #1e293b;
    width: min(360px, 90vw); height: 100%; display: flex; flex-direction: column;
    box-shadow: -8px 0 32px rgba(0,0,0,0.4);
  }
  #sessions-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 16px 18px; border-bottom: 1px solid #1e293b; flex-shrink: 0;
  }
  #sessions-header h2 { margin: 0; font-size: 15px; font-weight: 700; color: #e2e8f0; }
  #sessions-header button {
    background: none; border: none; color: #475569; font-size: 18px; cursor: pointer;
  }
  #sessions-header button:hover { color: #f1f5f9; }
  #sessions-list { flex: 1; overflow-y: auto; padding: 10px; display: flex; flex-direction: column; gap: 6px; }
  .session-item {
    background: #111827; border: 1px solid #1e293b; border-radius: 8px;
    padding: 10px 12px; cursor: pointer; transition: border-color 0.15s, background 0.15s;
    display: flex; align-items: flex-start; gap: 8px;
  }
  .session-item:hover { border-color: #334155; background: #161f30; }
  .session-item.active { border-color: #3b82f6; background: #0f1f3d; }
  .session-item-body { flex: 1; min-width: 0; }
  .session-item-goal {
    font-size: 13px; color: #cbd5e1; font-weight: 500;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .session-item-meta { font-size: 10px; color: #475569; margin-top: 3px; }
  .session-del-btn {
    background: none; border: none; color: #334155; font-size: 14px;
    cursor: pointer; padding: 0 2px; flex-shrink: 0; line-height: 1;
    transition: color 0.15s;
  }
  .session-del-btn:hover { color: #ef4444; }
  #sessions-footer { padding: 12px; border-top: 1px solid #1e293b; flex-shrink: 0; }
  #sessions-new-btn {
    width: 100%; padding: 9px; background: #1e293b; border: 1px solid #334155;
    border-radius: 7px; color: #94a3b8; font-size: 13px; cursor: pointer;
    transition: background 0.15s, color 0.15s;
  }
  #sessions-new-btn:hover { background: #273549; color: #e2e8f0; }

  /* ── Export Prompt Modal ── */
  #export-modal {
    display: none; position: fixed; inset: 0; z-index: 9999;
    background: rgba(0,0,0,0.7); align-items: center; justify-content: center;
  }
  #export-modal.open { display: flex; }
  #export-modal-box {
    background: #0f172a; border: 1px solid #334155; border-radius: 12px;
    width: min(640px, 92vw); max-height: 80vh;
    display: flex; flex-direction: column; overflow: hidden;
    box-shadow: 0 24px 64px rgba(0,0,0,0.6);
  }
  #export-modal-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 18px; border-bottom: 1px solid #1e293b; flex-shrink: 0;
  }
  #export-modal-header span { font-size: 14px; font-weight: 700; color: #f1f5f9; }
  #export-modal-close {
    background: none; border: none; color: #475569; font-size: 18px;
    cursor: pointer; line-height: 1; padding: 0;
  }
  #export-modal-close:hover { color: #f1f5f9; }
  #export-modal-body {
    flex: 1; overflow-y: auto; padding: 16px 18px;
  }
  #export-modal-text {
    width: 100%; min-height: 200px; background: #020617;
    border: 1px solid #1e293b; border-radius: 8px;
    color: #cbd5e1; font-size: 13px; line-height: 1.65;
    padding: 14px; resize: vertical; font-family: system-ui, sans-serif;
    box-sizing: border-box;
  }
  #export-modal-footer {
    padding: 12px 18px; border-top: 1px solid #1e293b;
    display: flex; gap: 8px; justify-content: flex-end; flex-shrink: 0;
  }
  #export-copy-btn {
    padding: 8px 20px; background: #22c55e; border: none; border-radius: 7px;
    color: #fff; font-size: 13px; font-weight: 600; cursor: pointer;
    transition: background 0.2s;
  }
  #export-copy-btn:hover { background: #16a34a; }
  #export-copy-btn.copied { background: #0f766e; }

  /* ── Layout Menu ── */
  .layout-opt {
    padding: 7px 12px; font-size: 12px; color: #94a3b8; border-radius: 5px;
    cursor: pointer; transition: background 0.12s, color 0.12s; white-space: nowrap;
  }
  .layout-opt:hover { background: #1e293b; color: #e2e8f0; }
  .layout-opt.active { color: #60a5fa; }

  /* ── Zoom controls ── */
  #zoom-controls {
    position: absolute; bottom: 20px; right: 20px;
    display: flex; flex-direction: column; gap: 5px; z-index: 40;
  }
  #zoom-controls button {
    width: 34px; height: 34px;
    background: rgba(10, 14, 24, 0.88); border: 1px solid #1e3a5f;
    border-radius: 7px; color: #60a5fa; font-size: 18px; line-height: 1;
    cursor: pointer; transition: all 0.15s; display: flex;
    align-items: center; justify-content: center;
  }
  #zoom-controls button:hover { background: #0f2744; border-color: #2563eb; color: #93c5fd; }

  /* ── RAG content in node card ── */
  .nd-rag { margin-top: 10px; }
  .nd-rag-label { font-size: 10px; color: #38bdf8; text-transform: uppercase;
                   letter-spacing: 1px; margin-bottom: 6px; font-weight: 600; }
  .nd-rag-chunk { background: #040710; border: 1px solid #0f1f38;
                   border-radius: 6px; padding: 9px 11px; margin-bottom: 5px; }
  .nd-rag-text { font-size: 11.5px; color: #64748b; line-height: 1.65;
                  display: -webkit-box; -webkit-line-clamp: 4;
                  -webkit-box-orient: vertical; overflow: hidden; }
  .nd-rag-source { font-size: 10px; color: #334155; margin-top: 4px;
                    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .nd-rag-loading { font-size: 11px; color: #334155; font-style: italic; padding: 4px 0; }
</style>
</head>
<body>

<!-- Main App -->
<div id="app">
  <div id="graph-pane">
    <div id="welcome-overlay">
      <h1>Ragraphe</h1>
      <p data-i18n="start.tagline">輸入目標，AI 幫你規劃達成路徑</p>
      <div id="onboarding-card" style="display:none">
        <ul class="ob-steps">
          <li><span class="ob-step-num">1</span><span>在左下角輸入你的目標，例如「我想去日本旅行」或「學習機器學習」</span></li>
          <li><span class="ob-step-num">2</span><span>AI 會建立知識圖，點擊節點可標記完成 ✅ 或跳過 ⏭</span></li>
          <li><span class="ob-step-num">3</span><span>繼續對話，AI 會根據你的進度調整路徑，並補充衛星資源</span></li>
        </ul>
        <div class="ob-legend">
          <div class="ob-dot"><span style="background:#3b82f6"></span>待完成</div>
          <div class="ob-dot"><span style="background:#22c55e"></span>已完成</div>
          <div class="ob-dot"><span style="background:#f59e0b"></span>AI 建議</div>
          <div class="ob-dot"><span style="background:#6366f1"></span>資源</div>
        </div>
        <button id="ob-dismiss-btn" onclick="dismissOnboarding()">了解了，開始探索 →</button>
      </div>
    </div>
    <div id="graph-canvas"></div>
    <div id="zoom-controls">
      <button onclick="zoomIn()" title="放大">＋</button>
      <button onclick="zoomFit()" title="適應視窗">⊙</button>
      <button onclick="zoomOut()" title="縮小">－</button>
      <button id="layout-toggle-btn" onclick="openLayoutMenu(event)" title="切換佈局" style="font-size:11px;padding:2px 5px">⊞</button>
    </div>
    <div id="layout-menu" style="
      display:none; position:fixed; z-index:8000;
      background:#0d1424; border:1px solid #334155; border-radius:8px;
      padding:4px; min-width:140px; box-shadow:0 8px 24px rgba(0,0,0,0.5);">
      <div class="layout-opt" data-mode="force" onclick="setLayout('force')">⋯ 力導向</div>
      <div class="layout-opt" data-mode="td"    onclick="setLayout('td')">⊤ 樹狀（由上而下）</div>
      <div class="layout-opt" data-mode="lr"    onclick="setLayout('lr')">⊢ 樹狀（由左而右）</div>
      <div class="layout-opt" data-mode="radialout" onclick="setLayout('radialout')">◎ 放射狀</div>
    </div>
    <div id="hover-tooltip"></div>
    <div id="node-popup">
      <button class="np-close" onclick="closeNodePopup()">✕</button>
      <div class="np-title" id="np-title"></div>
      <span class="nd-badge" id="np-badge"></span>
      <div class="np-desc" id="np-desc"></div>
      <div id="np-preview" style="display:none;margin:6px 0;padding:6px 8px;
        background:#060a14;border-left:2px solid #1e3a5f;border-radius:4px;
        font-size:10px;color:#64748b;line-height:1.55;max-height:60px;overflow:hidden"></div>
      <div style="display:flex;gap:6px;margin-top:6px">
        <button class="np-done-btn" id="np-done-btn" onclick="toggleNodeDone()" style="
          flex:1;padding:5px 0;border:none;border-radius:5px;font-size:11px;cursor:pointer;
          background:#16a34a;color:#fff;transition:background 0.15s">✓ 標記完成</button>
        <button class="np-skip-btn" id="np-skip-btn" onclick="skipCurrentNode()" style="flex:1">不需要</button>
      </div>
      <div id="np-feedback-row" style="display:none;margin-top:5px;display:flex;align-items:center;gap:4px">
        <span style="font-size:9px;color:#475569;flex:1">AI 建議品質：</span>
        <button id="np-fb-good" title="這個節點很好" onclick="submitNodeFeedback('good')" style="
          border:1px solid #1e3a5f;background:none;border-radius:4px;padding:2px 6px;
          font-size:11px;color:#64748b;cursor:pointer;transition:all 0.15s">👍</button>
        <button id="np-fb-bad"  title="這個節點不相關或品質差" onclick="submitNodeFeedback('bad')" style="
          border:1px solid #1e3a5f;background:none;border-radius:4px;padding:2px 6px;
          font-size:11px;color:#64748b;cursor:pointer;transition:all 0.15s">👎</button>
      </div>
      <button id="np-explore-btn" onclick="askAboutNode()" style="
        display:block;width:100%;margin-top:8px;padding:7px 0;
        border:none;border-radius:5px;font-size:12px;cursor:pointer;
        background:linear-gradient(135deg,#1d4ed8,#7c3aed);color:#fff;
        font-weight:600;letter-spacing:0.3px;transition:opacity 0.15s"
        onmouseover="if(!this.disabled)this.style.opacity='0.85'" onmouseout="if(!this.disabled)this.style.opacity='1'">
        🔍 深入探索此主題
      </button>
    </div>
  </div>
  <div id="chat-pane">
    <div id="chat-header">
      <div id="chat-header-toolbar">
        <button class="lang-btn active" data-lang="zh-TW" onclick="setLang('zh-TW')"
          style="background:none;border:1px solid #1e293b;border-radius:4px;color:#475569;
                 font-size:10px;padding:2px 6px;cursor:pointer;transition:all 0.15s">繁中</button>
        <button class="lang-btn" data-lang="en" onclick="setLang('en')"
          style="background:none;border:1px solid #1e293b;border-radius:4px;color:#475569;
                 font-size:10px;padding:2px 6px;cursor:pointer;transition:all 0.15s">EN</button>
        <button class="lang-btn" data-lang="ja" onclick="setLang('ja')"
          style="background:none;border:1px solid #1e293b;border-radius:4px;color:#475569;
                 font-size:10px;padding:2px 6px;cursor:pointer;transition:all 0.15s">日本語</button>
        <button id="kb-btn" onclick="openKB()" title="知識庫">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
          </svg>
        </button>
        <button id="admin-btn" onclick="openAdmin()" title="優先來源管理">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/>
          </svg>
        </button>
        <button id="profile-btn" onclick="openProfile()" title="個人檔案">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>
          </svg>
        </button>
        <button id="sessions-btn" onclick="openSessions()" title="歷史 Sessions"
          style="background:none;border:1px solid #1e293b;border-radius:4px;color:#475569;
                 padding:3px 6px;cursor:pointer;transition:all 0.15s;font-size:13px;line-height:1">
          ⊞
        </button>
      </div>
      <div id="chat-header-goal">
        <span class="header-label" data-i18n="header.goal">探索</span>
        <span id="goal-display"></span>
        <span id="llm-badge" style="font-size:10px;color:#475569;flex-shrink:0"></span>
      </div>
    </div>
    <div id="messages"></div>
    <div id="node-detail-pane">
      <div id="ndp-header">
        <span class="nd-badge" id="ndp-badge"></span>
        <span id="ndp-title"></span>
        <button id="ndp-close" onclick="closeNodeDetailPane()">✕</button>
      </div>
      <div id="ndp-body"></div>
      <button id="ndp-explore-btn" onclick="askAboutSatellite()" style="
        display:none;margin:8px 12px 12px;padding:7px 0;
        border:none;border-radius:5px;font-size:12px;cursor:pointer;
        background:linear-gradient(135deg,#1d4ed8,#7c3aed);color:#fff;
        font-weight:600;transition:opacity 0.15s"
        onmouseover="if(!this.disabled)this.style.opacity='0.85'" onmouseout="if(!this.disabled)this.style.opacity='1'">
        🔍 深入探索此主題
      </button>
    </div>
    <button id="restart-btn" onclick="restartSession()" data-i18n="chat.restart">↩ 重新開始</button>
    <button id="undo-btn" onclick="undoLastStep()">⎌ 撤回上一步</button>
    <button id="export-prompt-btn" onclick="exportPrompt()">📋 匯出為 Prompt</button>
    <div id="debug-panel">
      <div id="debug-header">
        <span>🐛 Debug</span>
        <button id="debug-hide-btn" onclick="_toggleDebug()" title="隱藏">✕</button>
      </div>
      <div id="debug-body"></div>
    </div>
    <button id="debug-toggle" onclick="_toggleDebug()">🐛 debug</button>
    <div id="input-area">
      <input id="msg-input" data-i18n-ph="start.placeholder" placeholder="例如：我想去日本旅行"
             onkeydown="if(event.key==='Enter' && !event.isComposing) sendMessage()" />
      <button id="send-btn" onclick="sendMessage()" data-i18n="start.btn">開始探索 →</button>
    </div>
  </div>
</div>

<!-- Knowledge Base Panel -->
<div id="kb-panel" onclick="if(event.target===this) closeKB()">
  <div id="kb-inner">
    <div id="kb-header">
      <h2>知識庫</h2>
      <div id="kb-header-right">
        <span id="kb-stats">載入中...</span>
        <button id="kb-close" onclick="closeKB()">✕</button>
      </div>
    </div>
    <div id="kb-body">
      <!-- 新增內容 -->
      <div>
        <div class="kb-section-title">新增內容</div>
        <div class="kb-tabs" style="flex-wrap:wrap">
          <button class="kb-tab active" onclick="switchKBTab('crawl', this)" data-i18n="kb.tab.crawl">主題爬取</button>
          <button class="kb-tab" onclick="switchKBTab('url', this)" data-i18n="kb.tab.url">URL 爬取</button>
          <button class="kb-tab" onclick="switchKBTab('text', this)" data-i18n="kb.tab.text">貼入文字</button>
          <button class="kb-tab" onclick="switchKBTab('jsonl', this)" data-i18n="kb.tab.jsonl">JSONL 匯入</button>
          <button class="kb-tab" onclick="switchKBTab('pdf', this)" data-i18n="kb.tab.pdf">PDF 上傳</button>
          <button class="kb-tab" onclick="switchKBTab('browse', this)" data-i18n="kb.tab.browse">瀏覽資料</button>
        </div>

        <!-- Topic Crawl tab -->
        <div id="kb-tab-crawl" class="kb-tab-content active">
          <input id="kb-crawl-topic" class="kb-input" data-i18n-ph="kb.crawl.topic_ph"
                 placeholder="主題名稱（例：金閣寺、Python 機器學習）"
                 onkeydown="if(event.key==='Enter') kbStartCrawl()" />
          <select id="kb-crawl-type" class="kb-input">
            <option value="general" data-i18n="gtype.general">一般</option>
            <option value="travel"  data-i18n="gtype.travel">旅行</option>
            <option value="learning" data-i18n="gtype.learning">學習</option>
            <option value="project" data-i18n="gtype.project">專案</option>
            <option value="research" data-i18n="gtype.research">研究</option>
          </select>
          <button class="kb-btn" onclick="kbStartCrawl()" data-i18n="kb.crawl.btn">開始爬取</button>
          <div id="kb-crawl-log"
               style="margin-top:8px;font-size:11px;color:#475569;
                      max-height:180px;overflow-y:auto;display:flex;flex-direction:column;gap:3px"></div>
        </div>

        <!-- URL tab -->
        <div id="kb-tab-url" class="kb-tab-content">
          <input id="kb-url" class="kb-input" placeholder="https://..." />
          <input id="kb-url-name" class="kb-input" placeholder="來源名稱（選填）" />
          <button class="kb-btn" onclick="kbAddURL()">抓取並加入知識庫</button>
          <div id="kb-url-result"></div>
        </div>

        <!-- Text tab -->
        <div id="kb-tab-text" class="kb-tab-content">
          <textarea id="kb-text" class="kb-textarea" placeholder="貼入文字內容..."></textarea>
          <input id="kb-text-source" class="kb-input" placeholder="來源名稱（例：論文名稱）" />
          <button class="kb-btn" onclick="kbAddText()">加入知識庫</button>
          <div id="kb-text-result"></div>
        </div>

        <!-- JSONL tab -->
        <div id="kb-tab-jsonl" class="kb-tab-content">
          <textarea id="kb-jsonl" class="kb-textarea"
            placeholder='每行一個 JSON，格式：{"text":"內容","source":"來源"}&#10;{"text":"第二段","source":"paper.pdf"}'></textarea>
          <input id="kb-jsonl-source" class="kb-input" placeholder="預設來源（若行內無 source 欄位）" />
          <button class="kb-btn" onclick="kbAddJSONL()">匯入</button>
          <div id="kb-jsonl-result"></div>
        </div>

        <!-- PDF tab -->
        <div id="kb-tab-pdf" class="kb-tab-content">
          <div style="font-size:11px;color:#475569;margin-bottom:4px">上傳 PDF，自動解析文字並加入知識庫</div>
          <input id="kb-pdf-file" type="file" accept=".pdf" class="kb-input"
                 style="padding:6px;cursor:pointer" />
          <input id="kb-pdf-name" class="kb-input" placeholder="顯示名稱（選填，預設用檔名）" />
          <select id="kb-pdf-category" class="kb-input">
            <option value="concept">📖 概念（論文、教科書）</option>
            <option value="resource">🔗 資源（參考手冊）</option>
            <option value="how_to">🛠 操作（技術文件）</option>
            <option value="event">📅 活動（會議資料）</option>
          </select>
          <button class="kb-btn" onclick="kbUploadPDF()">解析並加入知識庫</button>
          <div id="kb-pdf-result"></div>
        </div>
      </div>

      <!-- 已爬 URL -->
      <div id="kb-recent-section">
        <div class="kb-section-title" data-i18n="kb.recent">最近加入的來源</div>
        <div id="kb-url-list"><div style="color:#334155;font-size:12px">載入中...</div></div>
      </div>

      <!-- 瀏覽資料（搜尋模式） -->
      <div id="kb-browse-section" style="display:none;flex-direction:column;gap:8px">
        <div class="src-form-row">
          <input id="kb-browse-q" class="kb-input" data-i18n-ph="kb.browse.ph"
                 placeholder="輸入關鍵詞搜尋知識庫..."
                 onkeydown="if(event.key==='Enter') kbBrowse()" />
          <button class="kb-btn" onclick="kbBrowse()"
                  style="flex:0 0 60px;padding:8px 6px" data-i18n="kb.browse.btn">搜尋</button>
        </div>
        <div id="kb-browse-results"
             style="display:flex;flex-direction:column;gap:6px;max-height:380px;overflow-y:auto"></div>
      </div>
    </div>
  </div>
</div>

<!-- Admin Panel (Priority Sources) -->
<div id="admin-panel" onclick="if(event.target===this) closeAdmin()">
  <div id="admin-inner">
    <div id="admin-header">
      <h2>優先來源管理</h2>
      <button id="admin-close" onclick="closeAdmin()">✕</button>
    </div>
    <div id="admin-body">
      <!-- 新增表單 -->
      <div>
        <div class="pf-label" style="margin-bottom:10px">新增來源</div>
        <div class="src-add-form">
          <input id="src-name" class="src-form-input" placeholder="來源名稱（例：雄獅旅遊）" />
          <input id="src-url" class="src-form-input" placeholder="URL（例：https://...）" />
          <div class="src-form-row">
            <input id="src-keywords" class="src-form-input" placeholder="關鍵詞（逗號分隔）" />
            <input id="src-priority" class="src-form-input narrow" type="number" value="100" placeholder="優先度" />
          </div>
          <div class="src-form-row">
            <select id="src-category" class="src-form-input">
              <option value="general">📄 一般 (30天)</option>
              <option value="concept">📖 概念 (永久)</option>
              <option value="how_to">🛠 操作 (90天)</option>
              <option value="resource">🔗 資源 (30天)</option>
              <option value="event">📅 活動 (14天)</option>
              <option value="schedule">🕐 時程 (7天)</option>
              <option value="pricing">💰 費用 (7天)</option>
            </select>
            <input id="src-ttl" class="src-form-input narrow" type="number" placeholder="TTL(天)" title="覆蓋預設 TTL，0=永久" />
          </div>
          <input id="src-goal-types" class="src-form-input" placeholder="適用類型（留空=全部）：travel,learning,..." />
          <input id="src-vendor-id" class="src-form-input" placeholder="廠商 ID（選填）" />
          <button class="src-add-btn" onclick="addSource()">+ 新增來源</button>
        </div>
      </div>
      <!-- 來源列表 -->
      <div>
        <div class="pf-label" style="margin-bottom:10px">現有來源</div>
        <div id="src-list"><div style="color:#334155;font-size:12px">載入中...</div></div>
      </div>
    </div>
  </div>
</div>

<!-- Profile Panel -->
<div id="profile-panel" onclick="if(event.target===this) closeProfile()">
  <div id="profile-inner">
    <div id="profile-header">
      <h2>個人檔案</h2>
      <button id="profile-close" onclick="closeProfile()">✕</button>
    </div>
    <div id="profile-body">
      <div>
        <div class="pf-label">名稱</div>
        <input id="pf-name" class="pf-input" placeholder="（選填）" />
      </div>
      <div>
        <div class="pf-label">背景描述</div>
        <textarea id="pf-bg" class="pf-textarea"
          placeholder="例如：有 Python 基礎的資料科學學生，目標進入 ML 領域"></textarea>
      </div>
      <div>
        <div class="pf-label">技能 / 已知領域（Enter 新增）</div>
        <div class="pf-skill-row" onclick="document.getElementById('pf-skill-input').focus()">
          <div class="pf-skills" id="pf-skills"></div>
          <input id="pf-skill-input" class="pf-skill-input" placeholder="新增技能..."
                 onkeydown="handleSkillInput(event)" />
        </div>
      </div>
      <button id="profile-save-btn" onclick="saveProfile()">儲存</button>
      <div>
        <div class="pf-label">目標歷史</div>
        <div id="pf-history"></div>
      </div>
    </div>
  </div>
</div>

<script>
// ── i18n ───────────────────────────────────────────────────────────────────
const TRANSLATIONS = {
  'zh-TW': {
    // Start
    'start.tagline':        '說說你想探索的主題，或隨便聊聊',
    'start.placeholder':    '例如：我想學機器學習，或說說你在想什麼…',
    'start.btn':            '開始探索 →',
    // Header
    'header.goal':          '探索',
    'header.kb.title':      '知識庫',
    'header.admin.title':   '優先來源管理',
    'header.profile.title': '個人檔案',
    // Status
    'status.done':          '✅ 已完成',
    'status.todo':          '🔲 待完成',
    'status.skip':          '⏭️ 跳過',
    'status.source':        '📍 出發地',
    'status.sink':          '🎯 目的地',
    'status.unknown':       '❓ 未確認',
    // Node
    'node.expand':          '▼ 展開子步驟 ({count})',
    'node.collapse':        '▲ 收合子步驟',
    // RAG
    'rag.loading':          '相關資料載入中...',
    'rag.crawling':         '首次載入，正在抓取資料...',
    'rag.empty':            '目前尚無相關資料',
    'rag.label':            '相關資料',
    'rag.autocrawled':      '相關資料 (已自動補充)',
    'rag.time_sensitive':   '⚠️ 資訊可能已更新',
    'rag.open_pdf':         '開啟 PDF',
    // Category
    'cat.concept':          '📖 概念',
    'cat.how_to':           '🛠 操作',
    'cat.resource':         '🔗 資源',
    'cat.general':          '📄 一般',
    'cat.event':            '📅 活動',
    'cat.schedule':         '🕐 時程',
    'cat.pricing':          '💰 費用',
    // Chat
    'chat.thinking':        '思考中...',
    'chat.done_placeholder':'規劃完成',
    'chat.placeholder':     '輸入回答...',
    'chat.send':            '送出',
    'chat.restart':         '↩ 重新開始',
    'chat.missing':         '⚠️ 缺口：{text}',
    'chat.conn_error':      '連線錯誤，請重試',
    'chat.conn_interrupted':'連線中斷，訊息未送出',
    'chat.retry_btn':       '重新送出',
    // Stream
    'stream.analyzing':     '分析目標類型...',
    'stream.generating':    '目標類型：{type}，生成路徑骨架中...',
    'stream.progress':      '生成骨架中... ({tokens} tokens)',
    'stream.building':      '建立問題清單...',
    'stream.error':         '連線錯誤，請重試',
    // Goal types
    'gtype.travel':         '旅行',
    'gtype.learning':       '學習',
    'gtype.project':        '專案',
    'gtype.research':       '研究',
    'gtype.prompt':         'Prompt 設計',
    'gtype.general':        '一般目標',
    // Profile
    'pf.name':              '名稱',
    'pf.name_ph':           '（選填）',
    'pf.bg':                '背景描述',
    'pf.bg_ph':             '例如：有 Python 基礎的資料科學學生，目標進入 ML 領域',
    'pf.skills':            '技能 / 已知領域（Enter 新增）',
    'pf.skill_ph':          '新增技能...',
    'pf.save':              '儲存',
    'pf.saving':            '儲存中...',
    'pf.saved':             '✓ 已儲存',
    'pf.save_err':          '儲存失敗',
    'pf.history':           '目標歷史',
    'pf.no_history':        '尚無歷史目標',
    // KB
    'kb.title':             '知識庫',
    'kb.add_section':       '新增內容',
    'kb.tab.url':           'URL 爬取',
    'kb.tab.text':          '貼入文字',
    'kb.tab.jsonl':         'JSONL 匯入',
    'kb.tab.pdf':           'PDF 上傳',
    'kb.url_ph':            'https://...',
    'kb.url_name_ph':       '來源名稱（選填）',
    'kb.url_btn':           '抓取並加入知識庫',
    'kb.url_cached':        '✓ 已快取（近期爬過）',
    'kb.url_ok':            '✓ 已加入 {count} 個 chunks',
    'kb.text_ph':           '貼入文字內容...',
    'kb.text_src_ph':       '來源名稱（例：論文名稱）',
    'kb.text_btn':          '加入知識庫',
    'kb.jsonl_src_ph':      '預設來源（若行內無 source 欄位）',
    'kb.jsonl_btn':         '匯入',
    'kb.pdf_hint':          '上傳 PDF，自動解析文字並加入知識庫',
    'kb.pdf_name_ph':       '顯示名稱（選填，預設用檔名）',
    'kb.pdf_btn':           '解析並加入知識庫',
    'kb.pdf_ok':            '✓ 已加入 {count} 個 chunks（{filename}）',
    'kb.pdf_parsing':       '解析中...',
    'kb.pdf_cat.concept':   '📖 概念（論文、教科書）',
    'kb.pdf_cat.resource':  '🔗 資源（參考手冊）',
    'kb.pdf_cat.how_to':    '🛠 操作（技術文件）',
    'kb.pdf_cat.event':     '📅 活動（會議資料）',
    'kb.recent':            '最近加入的來源',
    'kb.no_data':           '尚無資料',
    'kb.fetching':          '爬取中...',
    'kb.load_fail':         '載入失敗',
    'kb.conn_err':          '✗ 連線錯誤',
    'kb.tab.crawl':         '主題爬取',
    'kb.tab.browse':        '瀏覽資料',
    'kb.crawl.topic_ph':    '主題名稱（例：金閣寺、Python 機器學習）',
    'kb.crawl.btn':         '開始爬取',
    'kb.crawl.running':     '爬取中...',
    'kb.crawl.done':        '✓ 完成，共 {count} 個 chunks',
    'kb.crawl.empty':       '未找到相關資料',
    'kb.browse.ph':         '輸入關鍵詞搜尋知識庫...',
    'kb.browse.btn':        '搜尋',
    'kb.browse.no_result':  '無相關結果',
    'kb.browse.searching':  '搜尋中...',
    // Admin
    'adm.title':            '優先來源管理',
    'adm.add_section':      '新增來源',
    'adm.name_ph':          '來源名稱（例：雄獅旅遊）',
    'adm.url_ph':           'URL（例：https://...）',
    'adm.kw_ph':            '關鍵詞（逗號分隔）',
    'adm.priority_ph':      '優先度',
    'adm.types_ph':         '適用類型（留空=全部）：travel,learning,...',
    'adm.vendor_ph':        '廠商 ID（選填）',
    'adm.ttl_ph':           'TTL(天)',
    'adm.add_btn':          '+ 新增來源',
    'adm.sources':          '現有來源',
    'adm.no_sources':       '尚無來源',
    'adm.delete':           '刪除',
    'adm.confirm_del':      '確定刪除這個來源？',
    'adm.loading':          '載入中...',
    'adm.load_fail':        '載入失敗',
    'adm.add_fail':         '新增失敗',
    'adm.del_fail':         '刪除失敗',
    // Lang
    'lang.label':           '語言',
  },

  'en': {
    'start.tagline':        'Explore any topic freely — AI maps the knowledge',
    'start.placeholder':    'e.g. I want to learn machine learning, or just chat…',
    'start.btn':            'Start Exploring →',
    'header.goal':          'Exploring',
    'header.kb.title':      'Knowledge Base',
    'header.admin.title':   'Priority Sources',
    'header.profile.title': 'Profile',
    'status.done':          '✅ Done',
    'status.todo':          '🔲 To Do',
    'status.skip':          '⏭️ Skip',
    'status.source':        '📍 Start',
    'status.sink':          '🎯 Goal',
    'status.unknown':       '❓ Unknown',
    'node.expand':          '▼ Show substeps ({count})',
    'node.collapse':        '▲ Hide substeps',
    'rag.loading':          'Loading related content...',
    'rag.crawling':         'First load, fetching data...',
    'rag.empty':            'No related content yet',
    'rag.label':            'Related Content',
    'rag.autocrawled':      'Related Content (auto-fetched)',
    'rag.time_sensitive':   '⚠️ May be outdated — verify before use',
    'rag.open_pdf':         'Open PDF',
    'cat.concept':          '📖 Concept',
    'cat.how_to':           '🛠 How-to',
    'cat.resource':         '🔗 Resource',
    'cat.general':          '📄 General',
    'cat.event':            '📅 Event',
    'cat.schedule':         '🕐 Schedule',
    'cat.pricing':          '💰 Pricing',
    'chat.thinking':        'Thinking...',
    'chat.done_placeholder':'Planning complete',
    'chat.placeholder':     'Type your answer...',
    'chat.send':            'Send',
    'chat.restart':         '↩ Start Over',
    'chat.missing':         '⚠️ Gaps: {text}',
    'chat.conn_error':      'Connection error, please retry',
    'chat.conn_interrupted':'Connection lost — message not sent',
    'chat.retry_btn':       'Resend',
    'stream.analyzing':     'Analyzing goal type...',
    'stream.generating':    'Goal type: {type} — generating skeleton...',
    'stream.progress':      'Generating... ({tokens} tokens)',
    'stream.building':      'Building question queue...',
    'stream.error':         'Connection error, please retry',
    'gtype.travel':         'Travel',
    'gtype.learning':       'Learning',
    'gtype.project':        'Project',
    'gtype.research':       'Research',
    'gtype.prompt':         'Prompt Design',
    'gtype.general':        'General',
    'pf.name':              'Name',
    'pf.name_ph':           '(optional)',
    'pf.bg':                'Background',
    'pf.bg_ph':             'e.g. Data science student with Python, aiming for ML',
    'pf.skills':            'Skills / Known Areas (press Enter to add)',
    'pf.skill_ph':          'Add skill...',
    'pf.save':              'Save',
    'pf.saving':            'Saving...',
    'pf.saved':             '✓ Saved',
    'pf.save_err':          'Save failed',
    'pf.history':           'Goal History',
    'pf.no_history':        'No history yet',
    'kb.title':             'Knowledge Base',
    'kb.add_section':       'Add Content',
    'kb.tab.url':           'Crawl URL',
    'kb.tab.text':          'Paste Text',
    'kb.tab.jsonl':         'Import JSONL',
    'kb.tab.pdf':           'Upload PDF',
    'kb.url_ph':            'https://...',
    'kb.url_name_ph':       'Source name (optional)',
    'kb.url_btn':           'Fetch & Add to Knowledge Base',
    'kb.url_cached':        '✓ Cached (recently crawled)',
    'kb.url_ok':            '✓ Added {count} chunks',
    'kb.text_ph':           'Paste text content...',
    'kb.text_src_ph':       'Source name (e.g. paper title)',
    'kb.text_btn':          'Add to Knowledge Base',
    'kb.jsonl_src_ph':      'Default source (if no source field in lines)',
    'kb.jsonl_btn':         'Import',
    'kb.pdf_hint':          'Upload PDF — auto-parse text and add to knowledge base',
    'kb.pdf_name_ph':       'Display name (optional, defaults to filename)',
    'kb.pdf_btn':           'Parse & Add',
    'kb.pdf_ok':            '✓ Added {count} chunks ({filename})',
    'kb.pdf_parsing':       'Parsing...',
    'kb.pdf_cat.concept':   '📖 Concept (papers, textbooks)',
    'kb.pdf_cat.resource':  '🔗 Resource (reference manuals)',
    'kb.pdf_cat.how_to':    '🛠 How-to (technical docs)',
    'kb.pdf_cat.event':     '📅 Event (conference materials)',
    'kb.recent':            'Recently Added Sources',
    'kb.no_data':           'No data yet',
    'kb.fetching':          'Fetching...',
    'kb.load_fail':         'Load failed',
    'kb.conn_err':          '✗ Connection error',
    'kb.tab.crawl':         'Topic Crawl',
    'kb.tab.browse':        'Browse',
    'kb.crawl.topic_ph':    'Topic (e.g. Kinkakuji, Python ML)',
    'kb.crawl.btn':         'Start Crawl',
    'kb.crawl.running':     'Crawling...',
    'kb.crawl.done':        '✓ Done — {count} chunks',
    'kb.crawl.empty':       'No data found',
    'kb.browse.ph':         'Search knowledge base...',
    'kb.browse.btn':        'Search',
    'kb.browse.no_result':  'No results',
    'kb.browse.searching':  'Searching...',
    'adm.title':            'Priority Sources',
    'adm.add_section':      'Add Source',
    'adm.name_ph':          'Source name (e.g. Lion Travel)',
    'adm.url_ph':           'URL (e.g. https://...)',
    'adm.kw_ph':            'Keywords (comma-separated)',
    'adm.priority_ph':      'Priority',
    'adm.types_ph':         'Goal types (empty=all): travel,learning,...',
    'adm.vendor_ph':        'Vendor ID (optional)',
    'adm.ttl_ph':           'TTL (days)',
    'adm.add_btn':          '+ Add Source',
    'adm.sources':          'Current Sources',
    'adm.no_sources':       'No sources yet',
    'adm.delete':           'Delete',
    'adm.confirm_del':      'Delete this source?',
    'adm.loading':          'Loading...',
    'adm.load_fail':        'Load failed',
    'adm.add_fail':         'Add failed',
    'adm.del_fail':         'Delete failed',
    'lang.label':           'Language',
  },

  'ja': {
    'start.tagline':        'トピックを自由に探索、AIが知識をマップ化',
    'start.placeholder':    '例：機械学習を学びたい、または何でも話して…',
    'start.btn':            '探索を始める →',
    'header.goal':          '目標',
    'header.kb.title':      'ナレッジベース',
    'header.admin.title':   '優先ソース管理',
    'header.profile.title': 'プロフィール',
    'status.done':          '✅ 完了',
    'status.todo':          '🔲 未完了',
    'status.skip':          '⏭️ スキップ',
    'status.source':        '📍 出発地',
    'status.sink':          '🎯 目的地',
    'status.unknown':       '❓ 未確認',
    'node.expand':          '▼ サブステップを展開 ({count})',
    'node.collapse':        '▲ サブステップを閉じる',
    'rag.loading':          '関連コンテンツを読み込み中...',
    'rag.crawling':         '初回読み込み中...',
    'rag.empty':            '関連コンテンツはまだありません',
    'rag.label':            '関連コンテンツ',
    'rag.autocrawled':      '関連コンテンツ（自動取得）',
    'rag.time_sensitive':   '⚠️ 情報が古い可能性があります',
    'rag.open_pdf':         'PDFを開く',
    'cat.concept':          '📖 概念',
    'cat.how_to':           '🛠 操作',
    'cat.resource':         '🔗 リソース',
    'cat.general':          '📄 一般',
    'cat.event':            '📅 イベント',
    'cat.schedule':         '🕐 スケジュール',
    'cat.pricing':          '💰 料金',
    'chat.thinking':        '考え中...',
    'chat.done_placeholder':'計画完了',
    'chat.placeholder':     '回答を入力...',
    'chat.send':            '送信',
    'chat.restart':         '↩ やり直す',
    'chat.missing':         '⚠️ 不足：{text}',
    'chat.conn_error':      '接続エラー、再試行してください',
    'chat.conn_interrupted':'接続が切断されました。メッセージは送信されませんでした',
    'chat.retry_btn':       '再送信',
    'stream.analyzing':     '目標タイプを分析中...',
    'stream.generating':    '目標タイプ：{type}、スケルトン生成中...',
    'stream.progress':      '生成中... ({tokens} トークン)',
    'stream.building':      '質問リストを構築中...',
    'stream.error':         '接続エラー、再試行してください',
    'gtype.travel':         '旅行',
    'gtype.learning':       '学習',
    'gtype.project':        'プロジェクト',
    'gtype.research':       'リサーチ',
    'gtype.prompt':         'プロンプト設計',
    'gtype.general':        '一般',
    'pf.name':              '名前',
    'pf.name_ph':           '（任意）',
    'pf.bg':                '経歴',
    'pf.bg_ph':             '例：Python基礎があるデータサイエンス学生',
    'pf.skills':            'スキル（Enterで追加）',
    'pf.skill_ph':          'スキルを追加...',
    'pf.save':              '保存',
    'pf.saving':            '保存中...',
    'pf.saved':             '✓ 保存しました',
    'pf.save_err':          '保存に失敗しました',
    'pf.history':           '目標履歴',
    'pf.no_history':        '履歴はありません',
    'kb.title':             'ナレッジベース',
    'kb.add_section':       'コンテンツを追加',
    'kb.tab.url':           'URLクロール',
    'kb.tab.text':          'テキスト貼り付け',
    'kb.tab.jsonl':         'JSONLインポート',
    'kb.tab.pdf':           'PDFアップロード',
    'kb.url_ph':            'https://...',
    'kb.url_name_ph':       'ソース名（任意）',
    'kb.url_btn':           '取得してナレッジベースに追加',
    'kb.url_cached':        '✓ キャッシュ済み',
    'kb.url_ok':            '✓ {count}件追加しました',
    'kb.text_ph':           'テキストを貼り付け...',
    'kb.text_src_ph':       'ソース名（例：論文タイトル）',
    'kb.text_btn':          'ナレッジベースに追加',
    'kb.jsonl_src_ph':      'デフォルトソース',
    'kb.jsonl_btn':         'インポート',
    'kb.pdf_hint':          'PDFをアップロードして自動解析',
    'kb.pdf_name_ph':       '表示名（任意）',
    'kb.pdf_btn':           '解析して追加',
    'kb.pdf_ok':            '✓ {count}件追加（{filename}）',
    'kb.pdf_parsing':       '解析中...',
    'kb.pdf_cat.concept':   '📖 概念（論文、教科書）',
    'kb.pdf_cat.resource':  '🔗 リソース（参考書）',
    'kb.pdf_cat.how_to':    '🛠 操作（技術文書）',
    'kb.pdf_cat.event':     '📅 イベント（会議資料）',
    'kb.recent':            '最近追加したソース',
    'kb.no_data':           'データなし',
    'kb.fetching':          '取得中...',
    'kb.load_fail':         '読み込み失敗',
    'kb.conn_err':          '✗ 接続エラー',
    'kb.tab.crawl':         'トピック収集',
    'kb.tab.browse':        'データ閲覧',
    'kb.crawl.topic_ph':    'トピック（例：金閣寺、Python機械学習）',
    'kb.crawl.btn':         '収集開始',
    'kb.crawl.running':     '収集中...',
    'kb.crawl.done':        '✓ 完了 — {count}件',
    'kb.crawl.empty':       'データが見つかりません',
    'kb.browse.ph':         'ナレッジベースを検索...',
    'kb.browse.btn':        '検索',
    'kb.browse.no_result':  '結果なし',
    'kb.browse.searching':  '検索中...',
    'adm.title':            '優先ソース管理',
    'adm.add_section':      'ソースを追加',
    'adm.name_ph':          'ソース名',
    'adm.url_ph':           'URL',
    'adm.kw_ph':            'キーワード（カンマ区切り）',
    'adm.priority_ph':      '優先度',
    'adm.types_ph':         '目標タイプ（空=全部）',
    'adm.vendor_ph':        'ベンダーID（任意）',
    'adm.ttl_ph':           'TTL（日）',
    'adm.add_btn':          '+ ソースを追加',
    'adm.sources':          '現在のソース',
    'adm.no_sources':       'ソースなし',
    'adm.delete':           '削除',
    'adm.confirm_del':      'このソースを削除しますか？',
    'adm.loading':          '読み込み中...',
    'adm.load_fail':        '読み込み失敗',
    'adm.add_fail':         '追加失敗',
    'adm.del_fail':         '削除失敗',
    'lang.label':           '言語',
  },
};

// ── i18n core ──────────────────────────────────────────────────────────────
const SUPPORTED_LANGS = ['zh-TW', 'en', 'ja'];

function _detectLang() {
  const saved = localStorage.getItem('ragraphe_lang');
  if (saved && SUPPORTED_LANGS.includes(saved)) return saved;
  const nav = navigator.language || '';
  if (nav.startsWith('ja'))   return 'ja';
  if (nav.startsWith('zh'))   return 'zh-TW';
  return 'en';
}

let currentLang = _detectLang();

function t(key, params = {}) {
  const dict = TRANSLATIONS[currentLang] || TRANSLATIONS['zh-TW'];
  const str  = dict[key] ?? (TRANSLATIONS['zh-TW'][key] ?? key);
  return str.replace(/\\{(\\w+)\\}/g, (_, k) => params[k] !== undefined ? params[k] : `{${k}}`);
}

function setLang(lang) {
  if (!SUPPORTED_LANGS.includes(lang)) return;
  currentLang = lang;
  localStorage.setItem('ragraphe_lang', lang);
  applyI18n();
  // 更新語言選擇器按鈕文字
  document.querySelectorAll('.lang-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.lang === lang);
  });
}

function applyI18n() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll('[data-i18n-ph]').forEach(el => {
    el.placeholder = t(el.dataset.i18nPh);
  });
  document.querySelectorAll('[data-i18n-title]').forEach(el => {
    el.title = t(el.dataset.i18nTitle);
  });
}

// ── Constants ──────────────────────────────────────────────────────────────
function STATUS_LABEL(s) {
  const map = { done:'status.done', todo:'status.todo', skip:'status.skip',
                source:'status.source', sink:'status.sink', unknown:'status.unknown' };
  return t(map[s] || 'status.todo');
}

// ── Node / Link color helpers ──────────────────────────────────────────────
// ── Node depth (hierarchy level) computation ─────────────────────────────────
function _computeNodeDepths() {
  if (!graph3D) return;
  const { links } = graph3D.graphData();
  const childrenOf = {};
  const hasParent  = new Set();
  links.forEach(l => {
    if (!l._is_parent) return;
    const sid = typeof l.source === 'object' ? l.source.id : l.source;
    const tid = typeof l.target === 'object' ? l.target.id : l.target;
    (childrenOf[sid] = childrenOf[sid] || []).push(tid);
    hasParent.add(tid);
  });
  // BFS from roots
  const roots = Object.keys(nodeData).filter(id =>
    !hasParent.has(id) && nodeData[id] && nodeData[id]._source !== 'resource'
  );
  const queue = roots.map(id => [id, 0]);
  const visited = new Set();
  while (queue.length) {
    const [id, depth] = queue.shift();
    if (visited.has(id)) continue;
    visited.add(id);
    if (nodeData[id]) nodeData[id]._depth = depth;
    (childrenOf[id] || []).forEach(cid => {
      if (!visited.has(cid)) queue.push([cid, depth + 1]);
    });
  }
  // Unreached (only proximity edges): treat as depth 0
  Object.keys(nodeData).forEach(id => {
    if (nodeData[id] && nodeData[id]._source !== 'resource' && nodeData[id]._depth == null)
      nodeData[id]._depth = 0;
  });
}

function _nodeColor(id) {
  const n = nodeData[id];
  if (!n) return '#888888';
  if (n._source === 'resource') return '#0ea5e9';
  const src = n.source || '';
  const st  = n._status || n.status || 'unknown';
  if (src === 'ai_planned'   && st === 'unknown') return '#a855f7';
  if (src === 'ai_suggested')  return '#e8924a';
  if (st === 'done')           return '#5ec97e';
  if (st === 'skip')           return '#6b7280';
  // Depth-based colour: root nodes (depth 0) are amber/gold
  const depth = n._depth ?? 0;
  if (depth === 0) return '#e8a020';   // amber — top-level / category node
  if (depth === 1) return '#5b8dee';   // blue  — first-level child
  return '#4a7cba';                    // slightly muted blue for deeper levels
}
function _linkColor(link) {
  if (link._is_bridge) return '#f59e0b';
  const fs = nodeData[typeof link.source === 'object' ? link.source?.id : link.source];
  const ts = nodeData[typeof link.target === 'object' ? link.target?.id : link.target];
  return (fs?._status === 'done' && ts?._status === 'done') ? '#5ec97e' : '#475569';
}

// ── User ID（localStorage 持久化） ─────────────────────────────────────────
function getUserId() {
  let uid = localStorage.getItem("ragraphe_user_id");
  if (!uid) {
    uid = "u_" + Math.random().toString(36).slice(2, 10);
    localStorage.setItem("ragraphe_user_id", uid);
  }
  return uid;
}
const USER_ID = getUserId();

// ── State ──────────────────────────────────────────────────────────────────
let sessionId    = null;
let graph3D      = null;       // ForceGraph (2D) instance
const _gNodes    = [];         // node objects for force-graph
const _gLinks    = [];         // link objects
const _gNodeById = {};         // id → node object
const _gLinkSet  = new Set();  // link id dedup
let nodeData     = {};         // id → full node object (incl. _* fields)
let graphMode    = "task";     // "task" | "day"
let planningDone = false;      // 規劃完成後切換為編輯模式
const expanded   = new Set();
let loadingEl    = null;
let _skills      = [];         // profile 技能標籤暫存
let currentMode  = "task";
let _graphQueue  = [];
let _graphQueueTimer = null;
const _expandedNodes = new Set();  // 已載入 RAG 知識的節點 id
const _ragCache      = {};         // node_id → {chunks, crawled}（前端 session 快取）
let   _pulsingNodeId = null;       // chat 點擊 → 節點 pulse 動畫
let   _pulseStart    = 0;
const _popularNames  = new Set();  // 跨 session 熱門節點名稱（golden ring 標示）
let   _userHasZoomed = false;      // 用戶手動 zoom/pan 後停止自動 zoomToFit
let   _isAutoZooming = false;      // programmatic zoomToFit 中，不觸發 _userHasZoomed

// ── Event delegation：.nd-expand 按鈕（避免 inline onclick） ───────────────
document.addEventListener("click", e => {
  const btn = e.target.closest(".nd-expand");
  if (btn) {
    const nodeId = btn.dataset.nodeId;
    if (nodeId) toggleExpand(nodeId);
  }
});

// ── Start（SSE 串流版）────────────────────────────────────────────────────
async function startSession() {
  const goal = document.getElementById("msg-input").value.trim();

  document.getElementById("goal-display").textContent = goal || "自由探索";
  document.getElementById("msg-input").value = "";
  _currentSparkleGen++;    // 第一輪開始，遞增世代

  // 禁用輸入，顯示串流狀態訊息
  document.getElementById("msg-input").disabled  = true;
  document.getElementById("send-btn").disabled   = true;
  const _exploreNodeBtn = document.getElementById("np-explore-btn");
  const _exploreSatBtn  = document.getElementById("ndp-explore-btn");
  if (_exploreNodeBtn) { _exploreNodeBtn.disabled = true; _exploreNodeBtn.style.opacity = '0.4'; }
  if (_exploreSatBtn)  { _exploreSatBtn.disabled  = true; _exploreSatBtn.style.opacity  = '0.4'; }
  const streamEl = _addStreamMsg(t('stream.analyzing'));

  try {
    const res = await fetch("/api/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal, user_id: USER_ID, lang: currentLang }),
    });

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\\n\\n");
      buffer = parts.pop();   // 保留不完整的尾段

      for (const part of parts) {
        if (!part.startsWith("data: ")) continue;
        let evt;
        try { evt = JSON.parse(part.slice(6)); } catch { continue; }

        if (evt.type === "graph_init") {
          currentMode = "network";
          graphMode   = "network";
          initEmptyGraph("network");
          document.getElementById("welcome-overlay").classList.add("hidden");
          if (evt.session_id) sessionId = evt.session_id;  // 提早設定，讓 resource fetch 能立刻用
          document.getElementById("undo-btn").style.display = "block";
          document.getElementById("undo-btn").disabled = true;  // 第一輪還沒有快照
          document.getElementById("undo-btn").textContent = "⎌ 撤回上一步";
          if (evt.llm) {
            const badge = document.getElementById("llm-badge");
            if (badge) badge.textContent = `✦ ${evt.llm}`;
          }
          // 載入跨 session 熱門節點
          _loadPopularNodes();

        } else if (evt.type === "node_add") {
          _enqueueGraphItem({ type: "node", data: evt.node });

        } else if (evt.type === "edge_add") {
          _enqueueGraphItem({ type: "edge", data: evt.edge });

        } else if (evt.type === "node_update") {
          _enqueueGraphItem({ type: "update", id: evt.id, data: evt.node });

        } else if (evt.type === "edge_update") {
          _enqueueGraphItem({ type: "edge_update", data: evt.edge });

        } else if (evt.type === "layout_update") {
          _waitQueueThenDo(() => _applySemanticLayout(evt.positions));

        } else if (evt.type === "coverage_update") {
          // D: 節點覆蓋率更新 → 更新 nodeData.coverage，讓玻璃球填充視覺化
          for (const [nid, cov] of Object.entries(evt.coverages || {})) {
            if (nodeData[nid]) nodeData[nid].coverage = cov;
          }

        } else if (evt.type === "reply") {
          _waitQueueThenDo(() => addMsg(evt.off_topic ? "ai ai-off-topic" : "ai", evt.text));

        } else if (evt.type === "done") {
          if (evt.session_id) {
            // 初始 done：設定 session 並開放輸入
            sessionId = evt.session_id;
            streamEl.remove();
            document.getElementById("welcome-overlay").classList.add("hidden");
            const sendBtn = document.getElementById("send-btn");
            sendBtn.textContent = t('chat.send');
            sendBtn.dataset.i18n = 'chat.send';
            const msgInput = document.getElementById("msg-input");
            msgInput.placeholder = t('chat.placeholder');
            msgInput.dataset.i18nPh = 'chat.placeholder';
            _waitQueueThenDo(() => {
              document.getElementById("msg-input").disabled = false;
              document.getElementById("send-btn").disabled  = false;
              const _eb1 = document.getElementById("np-explore-btn");
              const _eb2 = document.getElementById("ndp-explore-btn");
              if (_eb1) { _eb1.disabled = false; _eb1.style.opacity = '1'; }
              if (_eb2) { _eb2.disabled = false; _eb2.style.opacity = '1'; }
              document.getElementById("msg-input").focus();
            });
          }
          // 補掃：100ms 後確保所有節點都觸發資源查詢
          // （延遲以等待 _drainGraphQueue 的 50ms debounce 完成，nodeData 才完整）
          setTimeout(() => {
            for (const nid of Object.keys(nodeData)) {
              const n = nodeData[nid];
              if (n && n._source !== "resource" && !_resourceFetched.has(nid)) {
                _fetchNodeResources(nid);
              }
            }
          }, 100);
          // 每輪對話完成後，背景預先載入新增節點的 RAG 知識
          setTimeout(() => _prefetchImportantNodes(), 2500);

        } else if (evt.type === "debug") {
          _addDebugEntry(evt);

        } else if (evt.type === "error") {
          _updateStreamMsg(streamEl, "❌ " + (evt.text || t('stream.error')), false);
          document.getElementById("msg-input").disabled = false;
          document.getElementById("send-btn").disabled  = false;
        }
      }
    }
  } catch (e) {
    _updateStreamMsg(streamEl, "❌ " + t('stream.error'), false);
    document.getElementById("msg-input").disabled = false;
    document.getElementById("send-btn").disabled  = false;
  }
}

function _addStreamMsg(text) {
  const msgs = document.getElementById("messages");
  const div  = document.createElement("div");
  div.className   = "msg msg-stream active";
  div.textContent = text;
  msgs.appendChild(div);
  msgs.scrollTop  = msgs.scrollHeight;
  return div;
}

function _updateStreamMsg(el, text, active = true) {
  if (!el || !el.parentNode) return;
  el.textContent = text;
  el.classList.toggle("active", active);
  document.getElementById("messages").scrollTop =
    document.getElementById("messages").scrollHeight;
}

// ── Send message ───────────────────────────────────────────────────────────
async function sendMessage() {
  const input = document.getElementById("msg-input");
  const text  = input.value.trim();
  if (!text) return;
  if (!sessionId) { await startSession(); return; }

  const userMsgEl = addMsg("user", text);
  input.value = "";
  _userHasZoomed = false;  // 每輪新訊息允許一次 auto zoomToFit
  _currentSparkleGen++;    // 新一輪對話開始，遞增世代（讓本輪新節點共用同一 gen）
  setLoading(true);

  try {
    if (planningDone) {
      // Edit mode: JSON (unchanged)
      const res  = await fetch("/api/edit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, text }),
      });
      const data = await res.json();
      if (data.node_updates) {
        data.node_updates.forEach(n => { nodeData[n.id] = n; });
        if (graph3D) graph3D.graphData({ nodes: _gNodes, links: _gLinks });
      }
      // 新增節點（edit 模式用戶要求加的）
      if (data.node_adds && data.node_adds.length > 0) {
        data.node_adds.forEach(n => _enqueueGraphItem({ type: "node", data: n }));
      }
      if (data.edge_adds && data.edge_adds.length > 0) {
        data.edge_adds.forEach(e => _enqueueGraphItem({ type: "edge", data: e }));
      }
      addMsg("ai", data.message || "已更新。");
    } else {
      // Conversation mode: SSE stream
      const res = await fetch("/api/message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, text, lang: currentLang }),
      });
      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\\n\\n");
        buffer = parts.pop();

        for (const part of parts) {
          if (!part.startsWith("data: ")) continue;
          let evt;
          try { evt = JSON.parse(part.slice(6)); } catch { continue; }

          if (evt.type === "node_add") {
            _enqueueGraphItem({ type: "node", data: evt.node });
          } else if (evt.type === "edge_add") {
            _enqueueGraphItem({ type: "edge", data: evt.edge });
          } else if (evt.type === "node_update") {
            _enqueueGraphItem({ type: "update", id: evt.id, data: evt.node });
          } else if (evt.type === "edge_update") {
            _enqueueGraphItem({ type: "edge_update", data: evt.edge });
          } else if (evt.type === "layout_update") {
            _waitQueueThenDo(() => _applySemanticLayout(evt.positions));
          } else if (evt.type === "coverage_update") {
            for (const [nid, cov] of Object.entries(evt.coverages || {})) {
              if (nodeData[nid]) nodeData[nid].coverage = cov;
            }
          } else if (evt.type === "reply") {
            _waitQueueThenDo(() => {
              addMsg(evt.off_topic ? "ai ai-off-topic" : "ai", evt.text);
              // 第一次 reply 後啟用 undo（快照已存在）
              const _undoBtn = document.getElementById("undo-btn");
              if (_undoBtn) { _undoBtn.disabled = false; _undoBtn.style.display = "block"; }
              if (evt.ready) {
                planningDone = true;
                document.getElementById("msg-input").placeholder = "說說你想調整的部分…";
                document.getElementById("restart-btn").style.display = "block";
                document.getElementById("export-prompt-btn").style.display = "block";
                _showCompletionCard();
              }
            });
          } else if (evt.type === "debug") {
            _addDebugEntry(evt);
          }
          // ignore "done" type here
        }
      }
    }
  } catch (e) {
    // 回退：移除使用者訊息泡泡，還原文字到 input
    userMsgEl.remove();
    input.value = text;
    // 顯示含重試按鈕的錯誤訊息
    const msgs = document.getElementById("messages");
    const errEl = document.createElement("div");
    errEl.className = "msg msg-retry";
    const span = document.createElement("span");
    span.textContent = t('chat.conn_interrupted');
    const btn = document.createElement("button");
    btn.textContent = t('chat.retry_btn');
    btn.onclick = () => { errEl.remove(); sendMessage(); };
    errEl.appendChild(span);
    errEl.appendChild(btn);
    msgs.appendChild(errEl);
    msgs.scrollTop = msgs.scrollHeight;
  } finally {
    setLoading(false);
  }
}

// ── Graph: streaming init ──────────────────────────────────────────────────
function _graphWidth() {
  const pane = document.getElementById('chat-pane');
  const paneW = pane ? pane.offsetWidth : 340;
  return window.innerWidth - paneW;
}

function initEmptyGraph(mode) {
  if (graph3D) return;
  graphMode = mode; currentMode = mode;
  const container = document.getElementById('graph-canvas');

  graph3D = ForceGraph()(container)
    .graphData({ nodes: _gNodes, links: _gLinks })
    .nodeId('id')
    .nodeCanvasObject((node, ctx, globalScale) => {
      const n = nodeData[node.id];
      if (!n) return;
      const gs = globalScale;

      // hex → rgba 輔助
      const cr = (hex, a) => {
        const rv=parseInt(hex.slice(1,3),16), gv=parseInt(hex.slice(3,5),16), bv=parseInt(hex.slice(5,7),16);
        return `rgba(${rv},${gv},${bv},${a})`;
      };

      if (n._source === 'resource') {
        // ── 衛星：依類別著色，顯示知識標題片段 ──────────────────────────
        // 淡入動畫（出生後 800ms 內從 0 淡入）
        const FADE_MS = 800;
        const fadeRatio = n._born ? Math.min((Date.now() - n._born) / FADE_MS, 1.0) : 1.0;
        if (fadeRatio < 0.01) return;   // 還未開始顯示

        // 類別 → 顏色
        const catColors = {
          travel:   [14,165,233],   // 水藍
          learning: [139,92,246],   // 紫
          concept:  [16,185,129],   // 綠
          news:     [245,158,11],   // 琥珀
          product:  [249,115,22],   // 橙
          general:  [99,102,241],   // 靛藍
        };
        const cat = n._category || 'general';
        const [cr_,cg_,cb_] = catColors[cat] || catColors.general;
        // 相關性 → 不透明度 × 淡入比例
        const quality = n._quality || 0.5;
        const alpha = (0.38 + quality * 0.35) * fadeRatio;   // 淡入

        const sr = (4 + quality * 2) / gs;    // 4–6px 螢幕大小，品質越高越大

        // 主體
        ctx.beginPath(); ctx.arc(node.x, node.y, sr, 0, 2*Math.PI);
        ctx.fillStyle = `rgba(${cr_},${cg_},${cb_},${alpha})`; ctx.fill();
        // 高光
        const sg = ctx.createRadialGradient(
          node.x - sr*0.3, node.y - sr*0.35, 0, node.x, node.y, sr);
        sg.addColorStop(0, `rgba(255,255,255,${0.80 * fadeRatio})`);
        sg.addColorStop(0.5, `rgba(255,255,255,${0.10 * fadeRatio})`);
        sg.addColorStop(1,   'rgba(255,255,255,0)');
        ctx.beginPath(); ctx.arc(node.x, node.y, sr, 0, 2*Math.PI);
        ctx.fillStyle = sg; ctx.fill();
        // 邊框
        ctx.strokeStyle = `rgba(${cr_},${cg_},${cb_},${0.85 * fadeRatio})`;
        ctx.lineWidth = 0.7/gs; ctx.stroke();

        // 標籤：優先顯示知識標題（label = extracted title 或 domain）
        // 字號：gs<1.5 維持極小（6.5px），放大到 gs>=1.5 才逐漸增大到最大 12px
        const maxChars = gs < 1.5 ? 14 : gs < 2.5 ? 22 : 30;
        const labelText = (n.label || n._domain || '').slice(0, maxChars);
        if (labelText && gs > 0.6) {   // 太小的時候不顯示標籤（避免雜亂）
          const screenFs = gs < 1.5 ? 6.5 : Math.min(12, 6.5 + (gs - 1.5) * 6);
          const fs = screenFs / gs;
          ctx.font = `${fs}px system-ui,sans-serif`;
          ctx.textAlign = 'center'; ctx.textBaseline = 'bottom';
          // 半透明背景條
          const tw = ctx.measureText(labelText).width;
          ctx.fillStyle = 'rgba(5,10,20,0.65)';
          ctx.fillRect(node.x - tw/2 - 2/gs, node.y - sr - fs - 2/gs, tw + 4/gs, fs + 2/gs);
          ctx.fillStyle = `rgba(${cr_},${cg_},${cb_},0.95)`;
          ctx.fillText(labelText, node.x, node.y - sr - 2/gs);
        }
        return;
      }

      // ── 主節點：玻璃球效果 ──────────────────────────────────────
      // Size by source type first, then modulate by depth (deeper = smaller)
      const depth = n._depth ?? 0;
      const depthScale = Math.max(0.6, 1.0 - depth * 0.12);  // depth 0=1.0, 1=0.88, 2=0.76, 3+=0.6
      const baseRpx = n._source === 'ai_planned' ? 22 : n._source === 'ai_suggested' ? 16 : 20;
      const rPx = baseRpx * depthScale;
      const r   = rPx / gs;
      const col = _nodeColor(node.id);
      const isDash = n._source === 'ai_planned' || n._source === 'ai_suggested';

      // 知識豐富度：有衛星 → 光暈更強；衛星數越多越亮
      const satCount = (_resourceChildren[node.id] || []).length;
      const hasSat = satCount > 0;
      const glowAlpha = hasSat ? (0.28 + satCount * 0.08) : 0.20;  // 0.28~0.52

      // 1. 外部光暈（知識豐富節點更亮）
      const glow = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, r*(hasSat ? 2.8 : 2.4));
      glow.addColorStop(0, cr(col, glowAlpha)); glow.addColorStop(1, 'transparent');
      ctx.beginPath(); ctx.arc(node.x, node.y, r*(hasSat ? 2.8 : 2.4), 0, 2*Math.PI);
      ctx.fillStyle = glow; ctx.fill();

      // 1.5. 衛星軌道圈（有衛星且夠大時才顯示）
      if (hasSat && gs > 0.6) {
        const orbitPx = _orbitRadiusPx(node.id);
        const orbitR  = orbitPx / gs;
        ctx.save();
        ctx.setLineDash([3/gs, 5/gs]);
        ctx.beginPath(); ctx.arc(node.x, node.y, orbitR, 0, 2*Math.PI);
        ctx.strokeStyle = cr(col, 0.18);
        ctx.lineWidth   = 0.7 / gs;
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.restore();
      }

      // 1.8. 當次世代節點持續閃光（直到下一次生成）
      if (n._sparkleGen === _currentSparkleGen) {
        const _t = Date.now() / 1000;  // 秒，用於波紋相位
        // 3 道擴散波紋，錯開相位（持續循環，不 fade out）
        for (let _wi = 0; _wi < 3; _wi++) {
          const _phase = ((_t * 0.8) + _wi / 3) % 1;  // 0→1 循環
          const _ringR = r * (1.4 + _phase * 2.6);
          const _rAlpha = (1 - _phase) * 0.65;
          if (_rAlpha < 0.01) continue;
          ctx.beginPath();
          ctx.arc(node.x, node.y, _ringR, 0, 2 * Math.PI);
          ctx.strokeStyle = cr(col, _rAlpha);
          ctx.lineWidth = (2.5 * (1 - _phase)) / gs;
          ctx.stroke();
        }
        // 6 個方向小亮點（持續旋轉）
        const _sparkR = r * (1.8 + 0.4 * Math.sin(_t * 3));
        for (let _si = 0; _si < 6; _si++) {
          const _angle = (_si / 6) * 2 * Math.PI + _t * 1.5;
          const _sx = node.x + Math.cos(_angle) * _sparkR;
          const _sy = node.y + Math.sin(_angle) * _sparkR;
          const _sAlpha = 0.4 + 0.4 * Math.sin(_t * 4 + _si);
          ctx.beginPath();
          ctx.arc(_sx, _sy, 1.2 / gs, 0, 2 * Math.PI);
          ctx.fillStyle = `rgba(255,255,255,${Math.max(0, _sAlpha)})`;
          ctx.fill();
        }
      }

      // 2. 玻璃球主體（偏心漸層，左上亮、右下暗透）
      const body = ctx.createRadialGradient(
        node.x - r*0.28, node.y - r*0.28, r*0.04,
        node.x + r*0.12, node.y + r*0.12, r*1.08
      );
      body.addColorStop(0,    cr(col, 0.78));
      body.addColorStop(0.42, cr(col, 0.50));
      body.addColorStop(1,    cr(col, 0.18));
      ctx.beginPath(); ctx.arc(node.x, node.y, r, 0, 2*Math.PI);
      ctx.fillStyle = body; ctx.fill();

      // 2.5. D: Coverage fill（覆蓋率液體，從球底往上填充）
      const coverage = n.coverage || 0;
      if (coverage > 0.04) {
        ctx.save();
        ctx.beginPath(); ctx.arc(node.x, node.y, r * 0.94, 0, 2*Math.PI);
        ctx.clip();
        const innerR  = r * 0.94;
        const fillH   = 2 * innerR * coverage;
        const fillTop = node.y + innerR - fillH;
        // 液體漸層：底部白色亮光→中間節點色→頂部透明
        const fillGrad = ctx.createLinearGradient(node.x, fillTop + fillH, node.x, fillTop);
        fillGrad.addColorStop(0,   `rgba(255,255,255,0.30)`);  // 底部白色亮光（玻璃感）
        fillGrad.addColorStop(0.3, cr(col, 0.52));
        fillGrad.addColorStop(1,   cr(col, 0.06));
        ctx.fillStyle = fillGrad;
        ctx.fillRect(node.x - r, fillTop, 2*r, fillH);
        ctx.restore();
        // 液面橢圓邊（meniscus line，讓填充量一目瞭然）
        if (coverage < 0.97) {
          ctx.save();
          ctx.beginPath();
          ctx.ellipse(node.x, fillTop, innerR * 0.82, innerR * 0.07, 0, 0, 2*Math.PI);
          ctx.strokeStyle = cr(col, 0.65);
          ctx.lineWidth = 0.9 / gs;
          ctx.stroke();
          ctx.restore();
        }
      }

      // 3. 橢圓高光（左上，玻璃最亮反射點）
      ctx.save();
      ctx.beginPath();
      ctx.ellipse(node.x - r*0.27, node.y - r*0.30,
                  r*0.26, r*0.16, -Math.PI/4, 0, 2*Math.PI);
      ctx.fillStyle = 'rgba(255,255,255,0.58)';
      ctx.fill();
      ctx.restore();

      // 4. 底部淡反射（增加球體深度）
      ctx.save();
      ctx.beginPath();
      ctx.ellipse(node.x + r*0.18, node.y + r*0.30,
                  r*0.20, r*0.11, Math.PI/5, 0, 2*Math.PI);
      ctx.fillStyle = cr(col, 0.20);
      ctx.fill();
      ctx.restore();

      // 5. 虛線外框（只用於 ai_planned/ai_suggested，標示「待確認」狀態）
      if (isDash) {
        ctx.beginPath(); ctx.arc(node.x, node.y, r, 0, 2*Math.PI);
        ctx.strokeStyle = cr(col, 0.55);
        ctx.lineWidth = 1.2 / gs;
        ctx.setLineDash([3/gs, 3/gs]);
        ctx.stroke(); ctx.setLineDash([]);
      }

      // 6. Knowledge halo（已載入 RAG 知識的節點，顯示脈衝光環）
      if (_expandedNodes.has(node.id)) {
        const pulse = 0.22 + 0.12 * Math.sin(Date.now() * 0.0025);
        ctx.beginPath(); ctx.arc(node.x, node.y, r * 1.6, 0, 2 * Math.PI);
        ctx.strokeStyle = cr(col, pulse);
        ctx.lineWidth = 1.0 / gs;
        ctx.setLineDash([2/gs, 3/gs]);
        ctx.stroke(); ctx.setLineDash([]);
      }

      // 6.3. Chat-mention pulse ring（chat 點擊節點名稱 → 白色擴散環）
      if (_pulsingNodeId === node.id) {
        const elapsed = Date.now() - _pulseStart;
        const progress = Math.min(elapsed / 2000, 1.0);
        const ringR = r * (1.5 + progress * 2.5);
        const alpha = (1 - progress) * 0.85;
        ctx.beginPath(); ctx.arc(node.x, node.y, ringR, 0, 2 * Math.PI);
        ctx.strokeStyle = `rgba(255,255,255,${alpha})`;
        ctx.lineWidth = (2.5 * (1 - progress)) / gs;
        ctx.stroke();
        // autoPauseRedraw(false) 讓 force-graph 持續重繪，pulse ring 會自然更新
      }

      // 6.5. B: Crawling ring（背景爬取中 → 搜尋脈衝圈）
      if (_crawlingNodes.has(node.id)) {
        const t = Date.now() * 0.003;
        const searchR = (r * gs * 1.55 + 4 * Math.sin(t)) / gs;
        const searchAlpha = 0.18 + 0.22 * Math.abs(Math.sin(t * 0.8));
        ctx.beginPath(); ctx.arc(node.x, node.y, searchR, 0, 2*Math.PI);
        ctx.strokeStyle = `rgba(99,102,241,${searchAlpha})`;
        ctx.lineWidth = 1.8 / gs;
        ctx.setLineDash([5/gs, 3/gs]);
        ctx.stroke(); ctx.setLineDash([]);
        // 小標示文字
        if (gs > 0.7) {
          const fs2 = 7 / gs;
          ctx.font = `${fs2}px system-ui,sans-serif`;
          ctx.textAlign = 'center'; ctx.textBaseline = 'top';
          ctx.fillStyle = 'rgba(99,102,241,0.75)';
          ctx.fillText('⟳', node.x, node.y + searchR + 1/gs);
        }
      }

      // 6.7. Popular node golden ring
      if (_popularNames.has(n.label)) {
        ctx.beginPath(); ctx.arc(node.x, node.y, r * 1.22, 0, 2*Math.PI);
        ctx.strokeStyle = 'rgba(251,191,36,0.55)';
        ctx.lineWidth = 1.5 / gs;
        ctx.stroke();
        // 小星星 badge 左上角
        const sx = node.x - r * 0.72, sy = node.y - r * 0.72;
        const sbr = 4 / gs;
        ctx.beginPath(); ctx.arc(sx, sy, sbr, 0, 2*Math.PI);
        ctx.fillStyle = 'rgba(251,191,36,0.90)'; ctx.fill();
        if (gs > 0.6) {
          const sfs = 5 / gs;
          ctx.font = `bold ${sfs}px system-ui,sans-serif`;
          ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
          ctx.fillStyle = '#1a0e00';
          ctx.fillText('★', sx, sy);
        }
      }

      // 7. 文字標籤
      if (n.label) {
        const fs = 12 / gs;
        ctx.font = `bold ${fs}px system-ui,sans-serif`;
        ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
        const tw = ctx.measureText(n.label).width;
        ctx.fillStyle = 'rgba(5,10,20,0.70)';
        ctx.fillRect(node.x - tw/2 - 3/gs, node.y - r - fs - 3/gs, tw + 6/gs, fs + 3/gs);
        ctx.fillStyle = '#e2e8f0';
        ctx.fillText(n.label, node.x, node.y - r - 3/gs);
      }

      // 7.1. ai_suggested 節點：節點下方顯示「點擊確認」提示
      if (n._source === 'ai_suggested' && n._status === 'unknown' && gs > 0.7) {
        const hint = '點擊確認 ↑';
        const hfs = 9 / gs;
        ctx.font = `${hfs}px system-ui,sans-serif`;
        ctx.textAlign = 'center'; ctx.textBaseline = 'top';
        const pulse = 0.5 + 0.3 * Math.sin(Date.now() * 0.003);
        ctx.fillStyle = `rgba(249,115,22,${pulse})`;
        ctx.fillText(hint, node.x, node.y + r + 3/gs);
      }

      // 8. 知識計數 badge（右上角小圓，顯示衛星數量）
      if (satCount > 0 && gs > 0.5) {
        const bx = node.x + r * 0.72;
        const by = node.y - r * 0.72;
        const br = 4.5 / gs;
        ctx.beginPath(); ctx.arc(bx, by, br, 0, 2*Math.PI);
        ctx.fillStyle = 'rgba(14,165,233,0.92)';   // 水藍（代表知識）
        ctx.fill();
        // 數字
        const bfs = 5.5 / gs;
        ctx.font = `bold ${bfs}px system-ui,sans-serif`;
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.fillStyle = '#fff';
        ctx.fillText(String(satCount), bx, by);
      }
    })
    .nodeCanvasObjectMode(() => 'replace')
    .nodePointerAreaPaint((node, color, ctx, globalScale) => {
      const n = nodeData[node.id];
      const rPx = n?._source === 'resource' ? 8 : 24;
      ctx.beginPath(); ctx.arc(node.x, node.y, rPx / globalScale, 0, 2*Math.PI);
      ctx.fillStyle = color; ctx.fill();
    })
    .linkCanvasObject((link, ctx, globalScale) => {
      // 用 link 物件內建的 source/target（force-graph 替換成 node 物件）
      const sn = link.source, tn = link.target;
      if (!sn || !tn || typeof sn !== 'object') return;
      const sid = sn.id, tid = tn.id;
      if (nodeData[sid]?._source === 'resource' || nodeData[tid]?._source === 'resource') return;
      const gs = globalScale;
      // 螢幕固定線寬（2px bridge / 1.5px 一般邊）
      const lw = (link._is_bridge ? 2.0 : 1.5) / gs;
      // 螢幕固定 dash（5px on / 4px off）
      const dash = link._is_bridge ? [] : [5/gs, 4/gs];
      ctx.beginPath(); ctx.moveTo(sn.x, sn.y); ctx.lineTo(tn.x, tn.y);
      ctx.strokeStyle = link._color || _linkColor(link);
      ctx.lineWidth = lw;
      ctx.setLineDash(dash);
      ctx.globalAlpha = link._opacity ?? (link._is_bridge ? 0.80 : 0.65);
      ctx.stroke();
      ctx.setLineDash([]); ctx.globalAlpha = 1;
    })
    .linkCanvasObjectMode(() => 'replace')
    .onNodeClick((node) => {
      const n = nodeData[node.id];
      if (!n) return;
      if (n._source === 'resource') { _showResourceDetail(n); return; }
      const sc = graph3D.graph2ScreenCoords(node.x || 0, node.y || 0);
      showNodePopup(n, sc);
    })
    .onBackgroundClick(() => { closeNodePopup(); _hideHoverTooltip(); })
    .onNodeHover((node) => {
      container.style.cursor = node ? 'pointer' : 'default';
      if (node && nodeData[node.id]) {
        _showHoverTooltip(node);   // 主節點 + 衛星節點都顯示 tooltip
      } else {
        _hideHoverTooltip();
      }
    })
    .onEngineStop(() => {
      // 圖力模擬穩定後：更新 depth，再自動縮放
      _computeNodeDepths();
      const mainNodes = _gNodes.filter(n => nodeData[n.id]?._source !== 'resource');
      if (mainNodes.length >= 2 && graph3D && !_userHasZoomed) {
        _autoZoomToFit(500);
      }
    })
    .backgroundColor('#050a14')
    .autoPauseRedraw(false)
    .width(_graphWidth())
    .height(container.clientHeight || window.innerHeight);

  window.addEventListener('resize', () => {
    if (graph3D) graph3D.width(_graphWidth()).height(
      document.getElementById('graph-canvas').clientHeight
    );
  });

  // 偵測真正的用戶 zoom/pan（wheel 或拖拉），才停止自動 zoomToFit
  // 不用 onZoom，因為 force-graph 初始化時也會觸發 onZoom
  const _graphCanvas = container.querySelector('canvas');
  if (_graphCanvas) {
    const _markUserZoomed = () => { _userHasZoomed = true; };
    _graphCanvas.addEventListener('wheel',       _markUserZoomed, { passive: true });
    _graphCanvas.addEventListener('pointerdown', _markUserZoomed, { passive: true });
  }

  // 降低排斥力 + 加自訂重力，讓孤立元件不會飛太遠
  graph3D.d3Force('charge').strength(-80);
  // d3 force 必須是 function
  function _gravityForce(alpha) {
    _gNodes.forEach(n => {
      if (n.fx != null) return;
      n.vx -= n.x * 0.04 * alpha;
      n.vy -= n.y * 0.04 * alpha;
    });
  }
  _gravityForce.initialize = () => {};
  graph3D.d3Force('gravity', _gravityForce);
}

function _enqueueGraphItem(item) {
  _graphQueue.push(item);
  // 50ms 緩衝：把短時間內連續到達的 SSE 事件合併成一批
  if (!_graphQueueTimer) {
    _graphQueueTimer = setTimeout(_drainGraphQueue, 50);
  }
}

function _drainGraphQueue() {
  _graphQueueTimer = null;
  if (_graphQueue.length === 0) return;
  if (!graph3D) initEmptyGraph(currentMode);

  let graphChanged = false;

  while (_graphQueue.length > 0) {
    const item = _graphQueue.shift();
    if (item.type === 'node') {
      const d = item.data;
      nodeData[d.id] = d;
      if (!_galaxyCenterNid && d._source !== 'resource') _galaxyCenterNid = d.id;
      if (!_gNodeById[d.id]) {
        // 新節點初始位置設在現有節點質心附近，避免飛出畫面
        let cx = 0, cy = 0;
        const existing = _gNodes.filter(n => nodeData[n.id]?._source !== 'resource' && n.x != null && isFinite(n.x));
        if (existing.length > 0) {
          cx = existing.reduce((s, n) => s + n.x, 0) / existing.length + (Math.random() - 0.5) * 30;
          cy = existing.reduce((s, n) => s + n.y, 0) / existing.length + (Math.random() - 0.5) * 30;
        }
        const gn = { id: d.id, x: cx, y: cy };
        _gNodeById[d.id] = gn;
        _gNodes.push(gn);
        graphChanged = true;
        // 新主節點：標記當前世代，持續閃光直到下一輪
        if (d._source !== 'resource') {
          d._sparkleGen = _currentSparkleGen;
          _startSparkleLoop();
        }
      } // end if (!_gNodeById[d.id])
    } else if (item.type === 'update') {
      nodeData[item.id] = item.data;
      graphChanged = true;
    } else if (item.type === 'edge') {
      const e = item.data;
      if (!_gLinkSet.has(e.id)) {
        _gLinkSet.add(e.id);
        _gLinks.push({
          id: e.id,
          source: e.from || e.from_id,
          target: e.to   || e.to_id,
          _is_bridge: e.is_bridge || false,
          _color:   (e.color?.color)   || (e.is_bridge ? '#f97316' : '#60a5fa'),
          _opacity: (e.color?.opacity) || (e.is_bridge ? 0.70 : 0.65),
          _width: e.is_bridge ? 1.5 : 0.6,
        });
        graphChanged = true;
      }
    } else if (item.type === 'edge_update') {
      // minor update, refresh on next graphData call
      graphChanged = true;
    }
  }

  if (graphChanged && graph3D) {
    graph3D.graphData({ nodes: _gNodes, links: _gLinks });
  }

  // Trigger resource fetch：只對 user/ai_planned 節點（已確認的概念）
  // ai_suggested 是未確認的互斥選項，不值得產生衛星
  for (const gn of _gNodes) {
    const nd = nodeData[gn.id];
    if (!nd || nd._source === 'resource') continue;
    if (nd._source === 'ai_suggested') continue;  // 互斥選項暫不展衛星
    if (!_resourceFetched.has(gn.id)) {
      _fetchNodeResources(gn.id);
    }
  }
}

function _waitQueueThenDo(fn) {
  if (_graphQueue.length === 0 && !_graphQueueTimer) { fn(); return; }
  setTimeout(() => _waitQueueThenDo(fn), 80);
}

// ── 行星軌道動畫（3D）─────────────────────────────────────────────────────
const ORBIT_RADIUS = 25;
const ORBIT_SPEED  = 0.003;

const _orbitAngles    = {};
let   _galaxyCenterNid = null;

// rAF 動畫：衛星公轉（2D xy 平面，軌道半徑依行星大小縮放）
function _orbitRadiusPx(parentId) {
  const n = nodeData[parentId];
  if (!n) return 42;
  const depth = n._depth ?? 0;
  const src   = n.source || '';
  const baseRpx = src === 'ai_planned' ? 22 : src === 'ai_suggested' ? 16 : 20;
  const depthScale = Math.max(0.6, 1.0 - depth * 0.12);
  const planetPx = baseRpx * depthScale;
  return planetPx * 2.8;   // 軌道半徑 = 行星半徑 × 2.8（螢幕 px）
}

(function _animLoop() {
  if (graph3D) {
    const zoom = graph3D.zoom() || 1;

    for (const [parentId, childIds] of Object.entries(_resourceChildren)) {
      if (!childIds.length) continue;
      const parent = _gNodeById[parentId];
      if (!parent) continue;
      const px = parent.x || 0, py = parent.y || 0;
      const orbitPx = _orbitRadiusPx(parentId);
      const r = orbitPx / zoom;   // graph 單位
      childIds.forEach((cid, idx) => {
        const child = _gNodeById[cid];
        if (!child) return;
        if (_orbitAngles[cid] === undefined)
          _orbitAngles[cid] = (idx / Math.max(childIds.length, 1)) * 2 * Math.PI;
        _orbitAngles[cid] += ORBIT_SPEED;
        const a = _orbitAngles[cid];
        child.fx = px + r * Math.cos(a);
        child.fy = py + r * Math.sin(a);
        child.x = child.fx; child.y = child.fy;
      });
    }
  }
  requestAnimationFrame(_animLoop);
})();

// ── 資源子節點（RAG 知識來源，自動載入）──────────────────────────────────
const _resourceChildren  = {};
const _resourceFetched   = new Set();  // 成功取得衛星的節點 id
const _resourceAttempted = new Set();  // 已嘗試過（含空結果）
const _usedResourceIds   = new Set();
const _crawlingNodes     = new Set();  // B: 正在背景爬取的節點 id（顯示脈衝圈）

// ── Sparkle animation loop ─────────────────────────────────────────────────
// Nodes of the latest generation sparkle continuously until the next generation arrives.
let _currentSparkleGen = 0;  // increments each time a new batch of nodes is created
let _sparkleRafId = null;
function _startSparkleLoop() {
  if (_sparkleRafId) return;
  function _tick() {
    if (!graph3D) { _sparkleRafId = null; return; }
    const anyAlive = Object.values(nodeData).some(
      n => n._sparkleGen === _currentSparkleGen && n._source !== 'resource'
    );
    if (anyAlive) {
      graph3D.refresh();
      _sparkleRafId = requestAnimationFrame(_tick);
    } else {
      _sparkleRafId = null;
    }
  }
  _sparkleRafId = requestAnimationFrame(_tick);
}

async function _fetchNodeResources(nodeId, isRetry = false) {
  if (!sessionId) return;
  if (!isRetry && _resourceAttempted.has(nodeId)) return;
  if (_resourceFetched.has(nodeId)) return;
  _resourceAttempted.add(nodeId);
  try {
    const res = await fetch('/api/node_resources', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, node_id: nodeId }),
    });
    const data = await res.json();
    if (data.resources && data.resources.length > 0) {
      _crawlingNodes.delete(nodeId);
      _resourceFetched.add(nodeId);
      _addResourceNodes(nodeId, data.resources);
    } else if (data.crawling && !isRetry) {
      // A/B: 後端正在背景爬取 → 顯示脈衝圈，15 秒後重試一次
      _crawlingNodes.add(nodeId);
      setTimeout(async () => {
        _crawlingNodes.delete(nodeId);
        if (!_resourceFetched.has(nodeId)) {
          await _fetchNodeResources(nodeId, true);
        }
      }, 15000);
    }
    // 其他空結果不加入 _resourceFetched → 允許 prefetch 後重試
  } catch(e) {}
}

// prefetch 完成後，重試尚未取得衛星的節點
async function _retryResourceFetch() {
  const pending = Object.keys(nodeData).filter(id =>
    nodeData[id]?._source !== 'resource' && !_resourceFetched.has(id)
  );
  for (const nid of pending) {
    await _fetchNodeResources(nid, true);   // isRetry = true，強制重試
    await new Promise(r => setTimeout(r, 200));
  }
}

function _addResourceNodes(parentId, resources) {
  if (!graph3D) return;
  if (!_resourceChildren[parentId]) _resourceChildren[parentId] = [];

  const dedupedResources = resources.filter(r => !_usedResourceIds.has(r.id));
  dedupedResources.forEach(r => _usedResourceIds.add(r.id));

  dedupedResources.forEach((res, i) => {
    setTimeout(() => {
      const parent = _gNodeById[parentId];
      const px = parent?.x || 0, py = parent?.y || 0;
      const angle = (i / Math.max(dedupedResources.length, 1)) * 2 * Math.PI;
      _orbitAngles[res.id] = angle;

      nodeData[res.id] = {
        id: res.id,
        label: res.name,          // 知識標題（extracted title 或 domain）
        _source: 'resource',
        _url: res.source_url,
        _parent: parentId,
        _snippet: res.snippet,         // 短版（180字，hover tooltip 用）
        _full_snippet: res.full_snippet || res.snippet,  // 長版（400字，面板用）
        _domain: res.domain,      // 純 domain（顯示在 tooltip 來源行）
        _category: res.category,
        _quality: res.quality,
        _distance: res.distance,
        _born: Date.now(),        // 出生時間戳（用於淡入動畫）
      };
      if (!_gNodeById[res.id]) {
        const initR = (graph3D ? 42 / (graph3D.zoom() || 1) : ORBIT_RADIUS);
        const gn = {
          id: res.id,
          fx: px + initR * Math.cos(angle),
          fy: py + initR * Math.sin(angle),
        };
        gn.x = gn.fx; gn.y = gn.fy;
        _gNodeById[res.id] = gn;
        _gNodes.push(gn);
      }
      _resourceChildren[parentId].push(res.id);
      if (!_gLinkSet.has(`${parentId}→${res.id}`)) {
        _gLinkSet.add(`${parentId}→${res.id}`);
        _gLinks.push({ id: `${parentId}→${res.id}`, source: parentId, target: res.id, _width: 0.3 });
      }
      if (graph3D) graph3D.graphData({ nodes: _gNodes, links: _gLinks });
    }, i * 400);
  });
}

// ── 語意座標布局（MDS 結果動畫過渡） ────────────────────────────────────────
function _applySemanticLayout(positions) {
  if (!graph3D || !positions) return;
  const ids = Object.keys(positions);
  if (ids.length === 0) return;

  const startPos = {};
  for (const id of ids) {
    const gn = _gNodeById[id];
    startPos[id] = { x: gn?.x || 0, y: gn?.y || 0 };
  }

  const duration = 900, startTime = performance.now();

  function animate(now) {
    const t = Math.min((now - startTime) / duration, 1);
    const ease = t < 0.5 ? 4*t*t*t : 1 - Math.pow(-2*t+2,3)/2;
    for (const id of ids) {
      const gn = _gNodeById[id];
      if (!gn) continue;
      const s = startPos[id];
      const tgt = positions[id];
      gn.x = s.x + (tgt.x * 1.5 - s.x) * ease;
      gn.y = s.y + (tgt.y * 1.5 - s.y) * ease;
      gn.fx = gn.x; gn.fy = gn.y;
    }
    if (t < 1) {
      requestAnimationFrame(animate);
    } else {
      // Unfix after layout so force sim can spread naturally
      for (const id of ids) {
        const gn = _gNodeById[id];
        if (gn) { delete gn.fx; delete gn.fy; }
      }
      if (graph3D) {
        graph3D.graphData({ nodes: _gNodes, links: _gLinks });
        setTimeout(() => _autoZoomToFit(400), 300);
        // 圖穩定後，背景預先載入最重要節點的 RAG 知識
        setTimeout(() => _prefetchImportantNodes(), 1800);
      }
    }
  }
  requestAnimationFrame(animate);
}

// ── Graph: init ────────────────────────────────────────────────────────────
function initGraph(graphData) {
  graphMode = graphData.mode || "task";
  rebuildGraph(graphData);
}

function rebuildGraph(graphData) {
  nodeData = {};
  _gNodes.length = 0;
  _gLinks.length = 0;
  Object.keys(_gNodeById).forEach(k => delete _gNodeById[k]);
  _gLinkSet.clear();
  (graphData.nodes || []).forEach(n => {
    nodeData[n.id] = n;
    const gn = { id: n.id };
    _gNodeById[n.id] = gn;
    _gNodes.push(gn);
  });
  (graphData.edges || []).forEach(e => {
    if (!_gLinkSet.has(e.id)) {
      _gLinkSet.add(e.id);
      _gLinks.push({ id: e.id, source: e.from_id || e.from, target: e.to_id || e.to, _width: 0.6 });
    }
  });
  if (graph3D) graph3D.graphData({ nodes: _gNodes, links: _gLinks });
}

// ── Zoom controls ─────────────────────────────────────────────────────────
function _autoZoomToFit(ms = 500) {
  if (!graph3D) return;
  _isAutoZooming = true;
  graph3D.zoomToFit(ms, 48);
  setTimeout(() => { _isAutoZooming = false; }, ms + 200);
}
function zoomIn()  { if (!graph3D) return; const k = graph3D.zoom(); graph3D.zoom(k * 1.3, 300); }
function zoomOut() { if (!graph3D) return; const k = graph3D.zoom(); graph3D.zoom(k * 0.77, 300); }
function zoomFit() { if (!graph3D) return; graph3D.zoomToFit(400); }

// ── Expand / Collapse ──────────────────────────────────────────────────────
function toggleExpand(nodeId) {
  // 2D mode: expand/collapse not implemented (no hidden nodes concept in force-graph)
  expanded.has(nodeId) ? expanded.delete(nodeId) : expanded.add(nodeId);
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

const ALLOWED_STATUSES = new Set(["done", "todo", "skip", "unknown", "source", "sink"]);

// ── Node Popup ──────────────────────────────────────────────────────────────
let _popupNodeId = null;

function showNodePopup(n, domPos) {
  const popup = document.getElementById("node-popup");
  const pane  = document.getElementById("graph-pane");
  const safeStatus = ALLOWED_STATUSES.has(n._status) ? n._status : "todo";

  // 填入內容
  const titleEl = document.getElementById("np-title");
  titleEl.textContent = n.label || "";
  if (_popularNames.has(n.label)) {
    titleEl.title = "🔥 熱門路徑節點：多位使用者已完成此項目";
  } else {
    titleEl.title = "";
  }
  const badge = document.getElementById("np-badge");
  badge.textContent  = STATUS_LABEL(safeStatus);
  badge.className    = "nd-badge s-" + safeStatus;
  document.getElementById("np-desc").textContent = n._description || "";

  // Done 按鈕
  const doneBtn = document.getElementById("np-done-btn");
  if (["source", "sink"].includes(safeStatus)) {
    doneBtn.style.display = "none";
  } else if (safeStatus === "done") {
    doneBtn.style.display = "block";
    doneBtn.textContent = "↩ 取消完成";
    doneBtn.style.background = "#1e3a2a";
    doneBtn.style.color = "#4ade80";
  } else {
    doneBtn.style.display = "block";
    doneBtn.textContent = "✓ 標記完成";
    doneBtn.style.background = "#16a34a";
    doneBtn.style.color = "#fff";
  }

  // 跳過按鈕：source/sink 隱藏；skip → 重新開啟；其他 → 跳過
  const skipBtn = document.getElementById("np-skip-btn");
  if (["source", "sink"].includes(safeStatus)) {
    skipBtn.style.display = "none";
  } else if (safeStatus === "skip") {
    skipBtn.style.display = "block";
    skipBtn.textContent = "↩ 重新開啟此節點";
    skipBtn.classList.remove("skipped");
    skipBtn.style.borderColor = "#7c3aed";
    skipBtn.style.color = "#c4b5fd";
    skipBtn.onclick = reopenCurrentNode;
  } else {
    skipBtn.style.display = "block";
    skipBtn.textContent = "不需要此項目";
    skipBtn.classList.remove("skipped");
    skipBtn.style.borderColor = "";
    skipBtn.style.color = "";
    skipBtn.onclick = skipCurrentNode;
  }

  // 品質回饋列：只對 ai_planned 節點顯示
  const fbRow = document.getElementById('np-feedback-row');
  const goodBtn = document.getElementById('np-fb-good');
  const badBtn  = document.getElementById('np-fb-bad');
  if (n._source === 'ai_planned') {
    fbRow.style.display = 'flex';
    // 重設按鈕樣式
    goodBtn.style.background = ''; goodBtn.style.color = '#64748b';
    badBtn.style.background  = ''; badBtn.style.color  = '#64748b';
  } else {
    fbRow.style.display = 'none';
  }

  // 定位：節點右下方，確保不超出 pane 邊界
  const paneW = pane.clientWidth;
  const paneH = pane.clientHeight;
  const popW  = 220, popH = 130;
  let x = domPos.x + 16;
  let y = domPos.y + 16;
  if (x + popW > paneW - 8) x = domPos.x - popW - 16;
  if (y + popH > paneH - 8) y = paneH - popH - 8;
  if (x < 8) x = 8;
  if (y < 8) y = 8;

  popup.style.left = x + "px";
  popup.style.top  = y + "px";
  popup.classList.add("visible");
  _popupNodeId = n.id;
  _hideHoverTooltip();

  // 非同步載入 RAG（source/sink 是圖的起終點，不需要知識內容；unknown/todo/done 都查）
  if (!["source", "sink"].includes(safeStatus)) {
    fetchPopupRAG(n.id, n.label, safeStatus);
  }
}

// BFS 從 startNodeId 往外最多 4 hop，找 _depth 最小的主節點作為主題錨點
function _findThemeAnchor(startNodeId) {
  if (!startNodeId || !nodeData[startNodeId]) return '';
  const visited = new Set([startNodeId]);
  const queue = [startNodeId];
  let bestNode = nodeData[startNodeId];
  let bestDepth = bestNode?._depth ?? 999;
  while (queue.length > 0) {
    if (visited.size > 40) break;  // 防止過大圖爆走
    const current = queue.shift();
    for (const link of _gLinks) {
      const srcId = typeof link.source === 'object' ? link.source.id : link.source;
      const tgtId = typeof link.target === 'object' ? link.target.id : link.target;
      const neighborId = srcId === current ? tgtId : tgtId === current ? srcId : null;
      if (!neighborId || visited.has(neighborId)) continue;
      visited.add(neighborId);
      const nd = nodeData[neighborId];
      if (!nd || nd._source === 'resource') continue;
      const d = nd._depth ?? 999;
      if (d < bestDepth) { bestDepth = d; bestNode = nd; }
      queue.push(neighborId);
    }
  }
  return bestNode?.label || bestNode?.name || '';
}

function askAboutNode() {
  const n = _popupNodeId ? nodeData[_popupNodeId] : null;
  if (!n) return;
  const label = n.label || n.name || '';

  // 收集直接相連的主節點（最多 3 個，排除 resource）
  const neighborLabels = [];
  for (const link of _gLinks) {
    const srcId = typeof link.source === 'object' ? link.source.id : link.source;
    const tgtId = typeof link.target === 'object' ? link.target.id : link.target;
    const neighborId = srcId === _popupNodeId ? tgtId : tgtId === _popupNodeId ? srcId : null;
    if (!neighborId) continue;
    const nd = nodeData[neighborId];
    if (!nd || nd._source === 'resource') continue;
    const nl = nd.label || nd.name || '';
    if (nl && nl !== label && !neighborLabels.includes(nl)) neighborLabels.push(nl);
    if (neighborLabels.length >= 3) break;
  }

  closeNodePopup();
  const input = document.getElementById('msg-input');
  if (!input || input.disabled) return;

  // 動態主題錨點：從點擊節點往上找深度最小的節點
  const anchor = _findThemeAnchor(_popupNodeId);
  // 把點擊的節點 + 鄰居合成 context，讓孤立的短詞（如「爬」）有意義
  const ctx = neighborLabels.length > 0
    ? [label, ...neighborLabels].join('、')
    : label;
  input.value = ctx
    ? (anchor && anchor !== ctx
        ? `針對「${anchor}」，請幫我把「${ctx}」拆解成幾個具體需要了解的子主題`
        : `請幫我把「${ctx}」拆解成幾個具體需要了解的子主題`)
    : '請幫我拆解這個主題的重要子主題';
  sendMessage();
}

function closeNodePopup() {
  document.getElementById("node-popup").classList.remove("visible");
  const preview = document.getElementById("np-preview");
  if (preview) preview.style.display = 'none';
  _popupNodeId = null;
  clearImageBubbles();
  closeNodeDetailPane();
}

// ── Node Feedback ──────────────────────────────────────────────────────────
async function submitNodeFeedback(fb) {
  const nid = _popupNodeId;
  if (!nid || !sessionId) return;
  const n = nodeData[nid];
  if (!n) return;
  // Visual feedback: highlight button
  const goodBtn = document.getElementById('np-fb-good');
  const badBtn  = document.getElementById('np-fb-bad');
  if (fb === 'good') { goodBtn.style.background = '#1e3a5f'; goodBtn.style.color = '#60a5fa'; }
  else               { badBtn.style.background  = '#2d1a1a'; badBtn.style.color  = '#f87171'; }
  try {
    await fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, node_id: nid, node_name: n.label || '', feedback: fb }),
    });
  } catch(e) { /* silent */ }
}

// ── Image Bubbles ──────────────────────────────────────────────────────────────
let _bubbleNodeId  = null;
let _bubbleCount   = 0;

function clearImageBubbles() {
  document.querySelectorAll(".img-bubble").forEach(el => el.remove());
  _bubbleNodeId = null;
  _bubbleCount  = 0;
}

function updateBubblePositions() {
  if (!_bubbleNodeId || !graph3D) return;
  const gn = _gNodeById[_bubbleNodeId];
  if (!gn) return;
  const dom = graph3D.graph2ScreenCoords(gn.x || 0, gn.y || 0);
  const bubbles = [...document.querySelectorAll(".img-bubble")];
  const count   = bubbles.length;
  if (count === 0) return;
  const CARD_W = 90, CARD_H = 68, GAP = 8;
  const totalW = count * CARD_W + (count - 1) * GAP;
  bubbles.forEach((b, i) => {
    const x = dom.x - totalW / 2 + i * (CARD_W + GAP);
    const y = dom.y - 115;
    b.style.left = x + "px";
    b.style.top  = y + "px";
  });
}

async function showNodeImageBubbles(nodeId, chunks) {
  clearImageBubbles();
  _bubbleNodeId = nodeId;
  const pane = document.getElementById("graph-pane");

  // 去重，只取 URL 來源，最多 4 個
  const seen = new Set();
  const urlChunks = chunks.filter(c => {
    if (c.source_type !== "url" || seen.has(c.source)) return false;
    seen.add(c.source);
    return true;
  }).slice(0, 4);
  if (urlChunks.length === 0) return;

  for (const chunk of urlChunks) {
    if (_bubbleNodeId !== nodeId) return;  // 已換節點
    try {
      const res  = await fetch(`/api/og_image?url=${encodeURIComponent(chunk.source)}`);
      const data = await res.json();
      if (_bubbleNodeId !== nodeId) return;
      if (!data.image_url) continue;

      const bubble = document.createElement("div");
      bubble.className = "img-bubble";
      bubble.title = chunk.source_name || chunk.source;
      const img = document.createElement("img");
      img.src = data.image_url;
      img.alt = "";
      img.onerror = () => bubble.remove();
      const srcUrl = chunk.source;  // 閉包捕獲
      bubble.onclick = () => window.open(srcUrl, "_blank", "noopener");
      bubble.appendChild(img);
      pane.appendChild(bubble);

      updateBubblePositions();
    } catch (_) {}
  }
}

async function skipCurrentNode() {
  if (!_popupNodeId || !sessionId) return;
  const nodeId = _popupNodeId;
  try {
    const res  = await fetch("/api/skip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, node_id: nodeId }),
    });
    const data = await res.json();
    if (data.error) return;

    // 更新跳過的節點
    if (data.node) {
      nodeData[data.node.id] = data.node;
      // 3D: refresh nodeThreeObject
      if (graph3D) graph3D.graphData({ nodes: _gNodes, links: _gLinks });
    }
    // 更新邊的激活狀態（3D: edge colors are computed dynamically via linkColor）
    if (data.edge_updates && graph3D) {
      graph3D.graphData({ nodes: _gNodes, links: _gLinks });
    }
    closeNodePopup();
  } catch (e) { /* silent */ }
}

async function reopenCurrentNode() {
  if (!_popupNodeId || !sessionId) return;
  const nodeId = _popupNodeId;
  try {
    const res  = await fetch("/api/reopen", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, node_id: nodeId }),
    });
    const data = await res.json();
    if (data.error) return;
    if (data.node) {
      nodeData[data.node.id] = data.node;
      if (graph3D) graph3D.graphData({ nodes: _gNodes, links: _gLinks });
    }
    if (data.edge_updates && graph3D) {
      graph3D.graphData({ nodes: _gNodes, links: _gLinks });
    }
    closeNodePopup();
    // 重新嘗試取得衛星（若之前因 skip 未取得）
    _resourceAttempted.delete(nodeId);
    _fetchNodeResources(nodeId);
  } catch (e) { /* silent */ }
}

async function toggleNodeDone() {
  if (!_popupNodeId || !sessionId) return;
  const nodeId = _popupNodeId;
  const nd = nodeData[nodeId];
  if (!nd) return;
  const newStatus = nd._status === "done" ? "todo" : "done";
  try {
    const res  = await fetch("/api/node_status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, node_id: nodeId, status: newStatus }),
    });
    const data = await res.json();
    if (data.error) return;
    if (data.node) {
      nodeData[data.node.id] = data.node;
      if (graph3D) graph3D.graphData({ nodes: _gNodes, links: _gLinks });
    }
    closeNodePopup();
  } catch (e) { /* silent */ }
}

function closeNodeDetailPane() {
  document.getElementById("node-detail-pane").classList.remove("visible");
  document.getElementById("ndp-body").innerHTML = "";
  _currentSatelliteNode = null;
  const exploreBtn = document.getElementById('ndp-explore-btn');
  if (exploreBtn) exploreBtn.style.display = 'none';
  clearImageBubbles();
}

// ── Sessions Panel ─────────────────────────────────────────────────────────

async function openSessions() {
  document.getElementById("sessions-panel").classList.add("open");
  await _loadSessionsList();
}

function closeSessions() {
  document.getElementById("sessions-panel").classList.remove("open");
}

async function _loadSessionsList() {
  const list = document.getElementById("sessions-list");
  list.innerHTML = '<div style="color:#475569;font-size:12px;padding:8px">載入中…</div>';
  try {
    const res  = await fetch("/api/sessions");
    const data = await res.json();
    const sessions_data = data.sessions || [];
    if (!sessions_data.length) {
      list.innerHTML = '<div style="color:#475569;font-size:12px;padding:8px">尚無歷史 Session</div>';
      return;
    }
    list.innerHTML = "";
    sessions_data.forEach(s => {
      const item = document.createElement("div");
      item.className = "session-item" + (s.id === sessionId ? " active" : "");
      const dateStr = s.updated_at ? s.updated_at.slice(0, 16).replace("T", " ") : "";
      item.innerHTML = `
        <div class="session-item-body" onclick="switchToSession('${escapeHtml(s.id)}')">
          <div class="session-item-goal">${escapeHtml(s.goal || "（無標題）")}</div>
          <div class="session-item-meta">${dateStr} · ${s.node_count} 個節點</div>
        </div>
        <button class="session-del-btn" title="刪除" onclick="deleteSessionItem('${escapeHtml(s.id)}', this)">✕</button>`;
      list.appendChild(item);
    });
  } catch (e) {
    list.innerHTML = '<div style="color:#ef4444;font-size:12px;padding:8px">載入失敗</div>';
  }
}

async function switchToSession(sid) {
  if (sid === sessionId) { closeSessions(); return; }
  // 重建前端狀態：reload 整頁帶 sid（最簡單），或重建圖
  // 使用重載方式：把 sid 存入 URL hash 後 reload
  closeSessions();
  await _restoreSession(sid);
}

async function _restoreSession(sid) {
  // 重設前端
  if (graph3D) { graph3D._destructor && graph3D._destructor(); graph3D = null; }
  _gNodes.length = 0; _gLinks.length = 0;
  Object.keys(_gNodeById).forEach(k => delete _gNodeById[k]);
  _gLinkSet.clear();
  nodeData = {}; graphMode = "task"; planningDone = true;
  currentMode = "task"; _graphQueue = []; _graphQueueTimer = null; expanded.clear();
  _resourceAttempted.clear();

  // 從後端取得 session 快照
  try {
    const res  = await fetch("/api/sessions");
    const data = await res.json();
    const sd   = (data.sessions || []).find(s => s.id === sid);
    if (!sd) { alert("找不到 Session"); return; }

    sessionId = sid;
    document.getElementById("messages").innerHTML = "";
    document.getElementById("goal-display").textContent = sd.goal || "";
    document.getElementById("welcome-overlay").classList.add("hidden");
    document.getElementById("restart-btn").style.display = "block";
    document.getElementById("undo-btn").style.display    = "block";
    document.getElementById("export-prompt-btn").style.display = "block";
    document.getElementById("msg-input").disabled = false;
    const _sb = document.getElementById("send-btn");
    _sb.textContent = t('chat.send'); _sb.disabled = false;
    _sb.dataset.i18n = 'chat.send';

    // 取得完整 session 資料（nodes + edges）
    const r2   = await fetch("/api/session_data", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ session_id: sid }),
    });
    const full = await r2.json();
    if (full.error) { alert("Session 資料載入失敗"); return; }

    initEmptyGraph();

    // 重建節點
    (full.nodes || []).forEach(n => _enqueueGraphItem({ type: "node", data: n }));
    // 重建邊
    (full.edges || []).forEach(e => _enqueueGraphItem({ type: "edge", data: e }));

    // 重播聊天記錄（節點先入 nodeData，稍後 linkify 才有效）
    if (full.messages && full.messages.length > 0) {
      setTimeout(() => {
        const msgs = document.getElementById("messages");
        msgs.innerHTML = "";
        full.messages.forEach(m => addMsg(m.role, m.content, false));
        msgs.scrollTop = msgs.scrollHeight;
      }, 350);  // 等圖佇列處理完
    }
  } catch (e) {
    alert("載入 Session 失敗");
  }
}

async function undoLastStep() {
  if (!sessionId) return;
  const btn = document.getElementById("undo-btn");
  btn.disabled = true;
  btn.textContent = "⎌ 撤回中...";
  try {
    const res  = await fetch("/api/undo", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ session_id: sessionId }),
    });
    const data = await res.json();
    if (data.error) { alert(data.error === "No snapshots" ? "已無可撤回的步驟" : data.error); return; }

    // 清空圖並重建
    _gNodes.length = 0; _gLinks.length = 0;
    Object.keys(_gNodeById).forEach(k => delete _gNodeById[k]);
    _gLinkSet.clear();
    nodeData = {};
    if (graph3D) graph3D.graphData({ nodes: _gNodes, links: _gLinks });

    (data.nodes || []).forEach(n => _enqueueGraphItem({ type: "node", data: n }));
    (data.edges || []).forEach(e => _enqueueGraphItem({ type: "edge", data: e }));

    // 重播對話記錄
    setTimeout(() => {
      const msgs = document.getElementById("messages");
      msgs.innerHTML = "";
      (data.messages || []).forEach(m => addMsg(m.role, m.content, false));
      msgs.scrollTop = msgs.scrollHeight;
    }, 350);

    // 更新按鈕狀態
    const remaining = data.snapshots_remaining || 0;
    btn.textContent = remaining > 0 ? ("⎌ 撤回上一步 (" + remaining + ")") : "⎌ 撤回上一步";
    btn.disabled = remaining === 0;
  } catch (e) {
    alert("撤回失敗");
  } finally {
    if (!btn.disabled) btn.disabled = false;
  }
}

async function deleteSessionItem(sid, btn) {
  if (!confirm("確定刪除此 Session？")) return;
  try {
    await fetch(`/api/sessions/${encodeURIComponent(sid)}`, { method: "DELETE" });
    btn.closest(".session-item").remove();
    if (sid === sessionId) restartSession();
  } catch (e) { alert("刪除失敗"); }
}

// ── Layout Toggle ─────────────────────────────────────────────────────────


let _layoutMode = "force";

function openLayoutMenu(e) {
  const menu = document.getElementById("layout-menu");
  const btn  = document.getElementById("layout-toggle-btn");
  if (menu.style.display !== "none") { closeLayoutMenu(); return; }

  // 更新 active 標記
  menu.querySelectorAll(".layout-opt").forEach(el => {
    el.classList.toggle("active", el.dataset.mode === _layoutMode);
  });

  // 定位：緊貼按鈕上方
  const r = btn.getBoundingClientRect();
  menu.style.display = "block";
  const mh = menu.offsetHeight;
  menu.style.left = (r.right - menu.offsetWidth) + "px";
  menu.style.top  = (r.top - mh - 6) + "px";

  // 點外部關閉
  setTimeout(() => document.addEventListener("click", _closeLayoutMenuOutside, { once: true }), 0);
}

function _closeLayoutMenuOutside(e) {
  const menu = document.getElementById("layout-menu");
  if (!menu.contains(e.target)) closeLayoutMenu();
}

function closeLayoutMenu() {
  document.getElementById("layout-menu").style.display = "none";
}

function setLayout(mode) {
  if (!graph3D) return;
  _layoutMode = mode;
  closeLayoutMenu();
  const btn = document.getElementById("layout-toggle-btn");
  if (mode === "force") {
    graph3D.dagMode(null);
    btn.style.color = "";
  } else {
    graph3D.dagMode(mode).dagLevelDistance(80);
    btn.style.color = "#60a5fa";
  }
}

// ── Hover Tooltip ──────────────────────────────────────────────────────────────
function _showHoverTooltip(node) {
  if (!graph3D) return;
  const n  = nodeData[node.id];
  if (!n) return;
  const tt = document.getElementById('hover-tooltip');
  const sc = graph3D.graph2ScreenCoords(node.x || 0, node.y || 0);

  if (n._source === 'resource') {
    // 衛星 tooltip：顯示知識 snippet + 來源
    const catLabel = { travel:'旅遊', learning:'學習', concept:'知識', news:'時事', product:'產品', general:'資料' };
    const snippet  = (n._snippet || '').slice(0, 120);
    const domain   = n._domain || '';
    const cat      = catLabel[n._category] || '資料';
    tt.innerHTML   = `
      <div class="ht-name">${escapeHtml(n.label || domain)}</div>
      ${snippet ? `<div class="ht-desc">${escapeHtml(snippet)}${n._snippet && n._snippet.length > 120 ? '…' : ''}</div>` : ''}
      <div class="ht-hint">${cat} · ${escapeHtml(domain)} · 點擊開啟來源</div>`;
  } else {
    // 主節點 tooltip
    const hasRag   = _expandedNodes.has(node.id);
    const hintText = hasRag ? '💡 知識已載入，點擊查看' : '點擊展開知識';
    const desc     = (n._description || '').slice(0, 80);
    tt.innerHTML   = `
      <div class="ht-name">${escapeHtml(n.label || '')}</div>
      ${desc ? `<div class="ht-desc">${escapeHtml(desc)}${n._description && n._description.length > 80 ? '…' : ''}</div>` : ''}
      <div class="ht-hint${hasRag ? ' has-rag' : ''}">${hintText}</div>`;
  }

  // 定位在節點右下，確保不超出 graph-pane 邊界
  const pane = document.getElementById('graph-pane');
  const pw = pane.clientWidth, ph = pane.clientHeight;
  let x = sc.x + 14, y = sc.y - 10;
  if (x + 210 > pw) x = sc.x - 210 - 14;
  if (y + 120 > ph) y = ph - 120;
  if (y < 4) y = 4;
  tt.style.left = x + 'px';
  tt.style.top  = y + 'px';
  tt.classList.add('visible');
}

function _hideHoverTooltip() {
  document.getElementById('hover-tooltip').classList.remove('visible');
}

// ── Background RAG Prefetch ─────────────────────────────────────────────────
async function _prefetchImportantNodes() {
  if (!sessionId) return;
  // 找尚未載入 RAG 的 unknown/todo 節點，依優先順序：unknown 先，最多 4 個
  const candidates = Object.values(nodeData)
    .filter(n => n && n._source !== 'resource' && !_expandedNodes.has(n.id)
                 && ['unknown', 'todo'].includes(n._status))
    .sort((a, b) => (a._status === 'unknown' ? 0 : 1) - (b._status === 'unknown' ? 0 : 1))
    .slice(0, 4);
  for (const n of candidates) {
    if (!sessionId) return;
    try {
      const res  = await fetch("/api/expand", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, node_id: n.id }),
      });
      const data = await res.json();
      if (data.chunks && data.chunks.length > 0) {
        _ragCache[n.id] = data;
        _expandedNodes.add(n.id);
      }
    } catch (_) {}
    await new Promise(r => setTimeout(r, 400));  // 每次間隔，避免同時打太多 API
  }
  // prefetch 結束後，補抓尚未有衛星的節點（爬完資料就有資料可查了）
  setTimeout(() => _retryResourceFetch(), 500);
}

function _renderChunks(chunks, crawled) {
  // 同時支援 display categories（travel/learning/...）和 DB categories（pricing/how_to/...）
  const catClass = cat => {
    const m = {
      travel:'cat-travel', learning:'cat-learning', concept:'cat-concept',
      news:'cat-news', product:'cat-product',
      // DB category fallback
      pricing:'cat-news', how_to:'cat-learning', event:'cat-news',
      schedule:'cat-travel', resource:'cat-learning',
    };
    return m[cat] || '';
  };
  // 顯示標籤：DB category 也要有對應中文
  const catLabel = {
    travel:'旅遊', learning:'學習', concept:'知識', news:'時事', product:'產品',
    pricing:'費用', how_to:'教學', event:'活動', schedule:'時程', resource:'資源',
    general:'一般',
  };
  return `
    <div class="np-rag-label">${crawled ? t('rag.autocrawled') : t('rag.label')}</div>
    ${chunks.map(c => {
      const src = c.source_name || c.source;
      const icon = c.source_type === 'pdf' ? '📄' : c.source_type === 'url' ? '🔗' : '📝';
      const srcEl = (c.source_type === 'url' || c.source_type === 'pdf')
        ? `<a href="${escapeHtml(c.source)}" target="_blank" class="np-chunk-src">${icon} ${escapeHtml(src)}</a>`
        : `<span class="np-chunk-src">${icon} ${escapeHtml(src)}</span>`;
      return `<div class="np-chunk ${catClass(c.category)}">
        <div class="np-chunk-text">${escapeHtml(c.text)}</div>
        <div class="np-chunk-footer">
          ${c.category ? `<span class="np-chunk-cat">${escapeHtml(catLabel[c.category] || c.category)}</span>` : ''}
          ${srcEl}
        </div>
      </div>`;
    }).join('')}`;
}

// ── 衛星點擊：在右側面板顯示完整知識摘要 ─────────────────────────────────
let _currentSatelliteNode = null;

function askAboutSatellite() {
  const n = _currentSatelliteNode;
  if (!n) return;
  const satLabel = n.label || n.name || '';
  // 找父節點 label（衛星的 parent_id）
  const parentId = n._parent || null;
  const parentLabel = parentId ? (nodeData[parentId]?.label || '') : '';
  closeNodeDetailPane();
  const input = document.getElementById('msg-input');
  if (!input || input.disabled) return;
  // 動態主題錨點：從父節點往上找深度最小的節點
  const anchor = parentId ? _findThemeAnchor(parentId) : '';
  const ctx = parentLabel ? `${satLabel}（關於${parentLabel}）` : satLabel;
  input.value = anchor && anchor !== parentLabel
    ? `針對「${anchor}」，請幫我把「${ctx}」拆解成幾個具體需要了解的子主題`
    : `請幫我把「${ctx}」拆解成幾個具體需要了解的子主題`;
  sendMessage();
}

function _showResourceDetail(n) {
  const pane  = document.getElementById("node-detail-pane");
  const title = document.getElementById("ndp-title");
  const badge = document.getElementById("ndp-badge");
  const body  = document.getElementById("ndp-body");
  if (!pane) return;
  _currentSatelliteNode = n;
  const exploreBtn = document.getElementById('ndp-explore-btn');
  if (exploreBtn) exploreBtn.style.display = 'block';

  // catLabel（含 DB category fallback）
  const catLabel = {
    travel:'旅遊', learning:'學習', concept:'知識', news:'時事', product:'產品',
    pricing:'費用', how_to:'教學', event:'活動', schedule:'時程', resource:'資源',
    general:'一般',
  };
  const cat = catLabel[n._category] || '資料';

  // header
  title.textContent = n.label || n._domain || '知識來源';
  badge.textContent = cat;
  badge.className   = 'nd-badge';

  // body：完整 snippet + 來源連結（優先用 400字的 _full_snippet）
  const snippet = n._full_snippet || n._snippet || '';
  const icon = '🔗';
  body.innerHTML = `
    <div class="np-rag-label">知識摘要</div>
    <div class="np-chunk ${n._category ? 'cat-'+n._category : ''}">
      <div class="np-chunk-text" style="-webkit-line-clamp: unset; overflow: visible; white-space: pre-wrap;">${escapeHtml(snippet)}</div>
      <div class="np-chunk-footer" style="margin-top:8px; gap:8px;">
        <span class="np-chunk-cat">${escapeHtml(cat)}</span>
        ${n._url
          ? `<a href="${escapeHtml(n._url)}" target="_blank" class="np-chunk-src" style="color:#38bdf8;">${icon} ${escapeHtml(n._domain || n._url)}</a>`
          : ''}
        ${n._url
          ? `<a href="${escapeHtml(n._url)}" target="_blank" class="np-chunk-src" style="color:#64748b; margin-left:auto; font-size:10px; white-space:nowrap;">↗ 開啟來源</a>`
          : ''}
      </div>
    </div>`;

  pane.classList.add("visible");
}

async function fetchPopupRAG(nodeId, nodeLabel, nodeStatus) {
  // 展開右側 node-detail-pane
  const pane  = document.getElementById("node-detail-pane");
  const title = document.getElementById("ndp-title");
  const badge = document.getElementById("ndp-badge");
  const body  = document.getElementById("ndp-body");
  const preview = document.getElementById("np-preview");
  const safeStatus = ALLOWED_STATUSES.has(nodeStatus) ? nodeStatus : "todo";

  title.textContent = nodeLabel || "";
  badge.textContent = STATUS_LABEL(safeStatus);
  badge.className   = "nd-badge s-" + safeStatus;
  pane.classList.add("visible");
  // 主節點的 RAG 面板不顯示衛星 explore 按鈕
  _currentSatelliteNode = null;
  const _ndpExploreBtn = document.getElementById('ndp-explore-btn');
  if (_ndpExploreBtn) _ndpExploreBtn.style.display = 'none';

  // 若快取已有資料，立即顯示 inline preview
  if (_ragCache[nodeId]) {
    const cached = _ragCache[nodeId];
    body.innerHTML = _renderChunks(cached.chunks, cached.crawled);
    if (cached.chunks.length > 0) {
      preview.textContent = cached.chunks[0].text.slice(0, 120) + (cached.chunks[0].text.length > 120 ? '…' : '');
      preview.style.display = 'block';
    }
    showNodeImageBubbles(nodeId, cached.chunks);
    return;
  }

  body.innerHTML = `<div class="nd-rag-loading">${t('rag.loading')}</div>`;
  preview.style.display = 'none';

  if (!sessionId) { body.innerHTML = ""; return; }
  try {
    const res  = await fetch("/api/expand", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, node_id: nodeId }),
    });
    const data = await res.json();
    if (_popupNodeId !== nodeId) return;  // 已換節點，捨棄
    if (!data.chunks || data.chunks.length === 0) {
      body.innerHTML = `<div style="font-size:11px;color:#334155">${t('rag.empty')}</div>`;
      preview.style.display = 'none';
      return;
    }

    // 存入前端快取
    _ragCache[nodeId] = data;
    _expandedNodes.add(nodeId);

    body.innerHTML = _renderChunks(data.chunks, data.crawled);

    // Popup inline preview（第一個 chunk 摘要）
    const firstText = data.chunks[0].text;
    preview.textContent = firstText.slice(0, 120) + (firstText.length > 120 ? '…' : '');
    preview.style.display = 'block';

    // 在節點附近顯示圖片浮動小卡
    showNodeImageBubbles(nodeId, data.chunks);
  } catch (_) {
    body.innerHTML = "";
    preview.style.display = 'none';
  }
}

async function fetchNodeRAG(nodeId, node) {
  if (!sessionId) {
    const el = document.getElementById("nd-rag-" + nodeId);
    if (el) el.innerHTML = "";
    return;
  }
  const el = document.getElementById("nd-rag-" + nodeId);
  if (el) el.innerHTML = `<div class="nd-rag-loading">${t('rag.crawling')}</div>`;

  try {
    const res = await fetch("/api/expand", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, node_id: nodeId }),
    });
    const data = await res.json();
    const el2 = document.getElementById("nd-rag-" + nodeId);
    if (!el2) return;
    if (!data.chunks || data.chunks.length === 0) {
      el2.innerHTML = `<div class="nd-rag-loading" style="color:#1e3a5f">${t('rag.empty')}</div>`;
      return;
    }
    el2.innerHTML = `
      <div class="nd-rag-label">${data.crawled ? t('rag.autocrawled') : t('rag.label')}</div>
      ${data.chunks.map(c => {
        const displayName = c.source_name || c.source;
        let sourceHTML = "";
        if (c.source_type === "pdf") {
          sourceHTML = `<a href="${escapeHtml(c.source)}" target="_blank"
            style="font-size:10px;color:#60a5fa;text-decoration:none;display:flex;align-items:center;gap:4px;margin-top:4px">
            📄 ${escapeHtml(displayName)}
            <span style="font-size:9px;color:#334155;background:#0f1724;padding:1px 5px;border-radius:3px">${t('rag.open_pdf')}</span>
          </a>`;
        } else if (c.source_type === "url") {
          sourceHTML = `<a href="${escapeHtml(c.source)}" target="_blank" rel="noopener"
            style="font-size:10px;color:#334155;text-decoration:none;display:block;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
            🔗 ${escapeHtml(displayName)}
          </a>`;
        } else {
          sourceHTML = `<div class="nd-rag-source">📝 ${escapeHtml(displayName)}</div>`;
        }
        return `<div class="nd-rag-chunk">
          <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
            <span style="font-size:10px;color:#475569">${escapeHtml(c.category_label || "")}</span>
            ${c.time_sensitive ? `<span style="font-size:10px;color:#fbbf24">${t('rag.time_sensitive')}</span>` : ""}
          </div>
          <div class="nd-rag-text">${escapeHtml(c.text)}</div>
          ${sourceHTML}
        </div>`;
      }).join("")}`;
    // 更新後捲到底部
    const msgs = document.getElementById("messages");
    msgs.scrollTop = msgs.scrollHeight;
  } catch (_) {
    const el2 = document.getElementById("nd-rag-" + nodeId);
    if (el2) el2.innerHTML = "";
  }
}

// ── Chat helpers ───────────────────────────────────────────────────────────

/**
 * 掃描文字中包含的節點名稱，包裝成可點擊的 <span class="node-ref">
 * 點擊後圖上對應節點會 pulse + zoom
 * 使用 split/join 避免 regex 特殊字元問題
 */
function _linkifyNodes(escapedHtml) {
  const entries = Object.entries(nodeData)
    .filter(([, n]) => n.label && n.label.length > 1 && n._source !== 'resource')
    .sort((a, b) => b[1].label.length - a[1].label.length);  // 長名稱優先
  let result = escapedHtml;
  for (const [id, n] of entries) {
    const label = escapeHtml(n.label);
    if (!result.includes(label)) continue;
    const span = '<span class="node-ref" data-id="' + id + '" onclick="highlightNodeFromChat(this.dataset.id)">' + label + '</span>';
    result = result.split(label).join(span);
  }
  return result;
}

function addMsg(role, text, scroll = true) {
  const msgs = document.getElementById("messages");
  const div  = document.createElement("div");
  div.className = "msg msg-" + role;
  div.innerHTML = _linkifyNodes(escapeHtml(text));
  msgs.appendChild(div);
  if (scroll) msgs.scrollTop = msgs.scrollHeight;
  return div;
}

// ── Debug Panel ──────────────────────────────────────────────────────────────
function _toggleDebug() {
  const panel   = document.getElementById("debug-panel");
  const toggle  = document.getElementById("debug-toggle");
  const hideBtn = document.getElementById("debug-hide-btn");
  panel.classList.toggle("open");
  const isOpen = panel.classList.contains("open");
  toggle.textContent  = isOpen ? "🐛 hide" : "🐛 debug";
  if (hideBtn) hideBtn.title = isOpen ? "隱藏 debug" : "顯示 debug";
}

function _addDebugEntry(evt) {
  const panel = document.getElementById("debug-body");
  if (!panel) return;
  const div = document.createElement("div");
  div.className = "dbg-entry";
  const stageColor = evt.stage === "chat_extract" ? "#5af" : "#fa5";
  let html = `<span class="dbg-stage" style="color:${stageColor}">[${evt.stage}]</span> `;
  if (evt.error) {
    html += `<span class="dbg-error">ERROR: ${escapeHtml(evt.error)}</span><br>`;
  }
  if (evt.stage === "chat_extract") {
    const concepts = (evt.user_concepts || []).map(c => c.name).join(", ") || "(none)";
    const suggestions = (evt.ai_suggestions || []).map(c => c.name).join(", ") || "(none)";
    html += `<span class="dbg-key">reply:</span> <span class="dbg-val">${escapeHtml((evt.reply||"").slice(0,120))}</span><br>`;
    html += `<span class="dbg-key">user_concepts:</span> <span class="dbg-val">${escapeHtml(concepts)}</span><br>`;
    html += `<span class="dbg-key">ai_suggestions:</span> <span class="dbg-val">${escapeHtml(suggestions)}</span>`;
    if (evt.deferred_names && evt.deferred_names.length)
      html += `<br><span class="dbg-key">deferred:</span> <span class="dbg-val">${escapeHtml(evt.deferred_names.join(", "))}</span>`;
  } else if (evt.stage === "plan") {
    const pairs = (evt.top_pairs || []).map(p => `${p.a}↔${p.b}(${p.dist})`).join(", ") || "(none)";
    const bridges = (evt.bridge_nodes || []).map(n => `${n.name}[${(n.connects||[]).join('↔')}]`).join(", ") || "(none)";
    const disconnStatus = evt.disconnected ? '<span style="color:#f90">⚡ disconnected</span>' : '<span style="color:#5af">✓ connected</span>';
    html += `${disconnStatus}  <span class="dbg-key">components:</span> <span class="dbg-val">${evt.cluster_count ?? "?"}</span>  `;
    html += `<span class="dbg-key">interp_chunks:</span> <span class="dbg-val">${evt.interp_chunks ?? "?"}</span><br>`;
    if (evt.disconnected) {
      html += `<span class="dbg-key">gap_pairs:</span> <span class="dbg-val">${escapeHtml(pairs)}</span><br>`;
      html += `<span class="dbg-key">bridges:</span> <span class="dbg-val">${escapeHtml(bridges)}</span><br>`;
      html += `<span class="dbg-key">rag_len:</span> <span class="dbg-val">${evt.rag_context_len ?? "?"} chars</span>`;
    }
  }
  div.innerHTML = html;
  panel.insertBefore(div, panel.firstChild);  // 新的在最上面
}

/** chat 點擊節點名稱 → 圖上該節點 pulse + zoom */
function highlightNodeFromChat(nodeId) {
  const gn = _gNodeById[nodeId];
  if (!gn || !graph3D) return;
  graph3D.centerAt(gn.x, gn.y, 400);
  graph3D.zoom(Math.max(graph3D.zoom(), 2.5), 400);
  _pulsingNodeId = nodeId;
  _pulseStart    = Date.now();
  // 2 秒後停止 pulse
  setTimeout(() => { if (_pulsingNodeId === nodeId) _pulsingNodeId = null; }, 2000);
}

function setLoading(on) {
  const input = document.getElementById("msg-input");
  const btn   = document.getElementById("send-btn");
  const msgs  = document.getElementById("messages");
  const exploreNode = document.getElementById("np-explore-btn");
  const exploreSat  = document.getElementById("ndp-explore-btn");

  if (on) {
    input.disabled = true;
    btn.disabled   = true;
    if (exploreNode) { exploreNode.disabled = true; exploreNode.style.opacity = '0.4'; }
    if (exploreSat)  { exploreSat.disabled  = true; exploreSat.style.opacity  = '0.4'; }
    closeNodePopup();       // 思考開始時關閉 popup，避免節點重新生成後 popup 殘留原位
    loadingEl = document.createElement("div");
    loadingEl.className = "msg msg-loading";
    loadingEl.textContent = t('chat.thinking');
    msgs.appendChild(loadingEl);
    msgs.scrollTop = msgs.scrollHeight;
  } else {
    input.disabled = false;
    btn.disabled   = false;
    if (exploreNode) { exploreNode.disabled = false; exploreNode.style.opacity = '1'; }
    if (exploreSat)  { exploreSat.disabled  = false; exploreSat.style.opacity  = '1'; }
    if (loadingEl) { loadingEl.remove(); loadingEl = null; }
    input.focus();
  }
}

// ── 重新規劃 ───────────────────────────────────────────────────────────────
function restartSession() {
  sessionId    = null;
  if (graph3D) { graph3D._destructor && graph3D._destructor(); graph3D = null; }
  _gNodes.length = 0;
  _gLinks.length = 0;
  Object.keys(_gNodeById).forEach(k => delete _gNodeById[k]);
  _gLinkSet.clear();
  nodeData     = {};
  graphMode    = "task";
  planningDone = false;
  currentMode  = "task";
  _graphQueue  = [];
  _graphQueueTimer = null;
  expanded.clear();

  document.getElementById("messages").innerHTML       = "";
  document.getElementById("restart-btn").style.display = "none";
  document.getElementById("undo-btn").style.display    = "none";
  document.getElementById("export-prompt-btn").style.display = "none";
  document.getElementById("msg-input").disabled        = false;
  const _mi = document.getElementById("msg-input");
  _mi.placeholder    = t('start.placeholder');
  _mi.value          = "";
  _mi.dataset.i18nPh = 'start.placeholder';
  const _sb = document.getElementById("send-btn");
  _sb.textContent  = t('start.btn');
  _sb.disabled     = false;
  _sb.dataset.i18n = 'start.btn';
  document.getElementById("goal-display").textContent  = "";
  document.getElementById("graph-canvas").innerHTML   = "";
  document.getElementById("welcome-overlay").classList.remove("hidden");
  document.getElementById("msg-input").focus();
}

// ── Profile ────────────────────────────────────────────────────────────────
async function openProfile() {
  document.getElementById("profile-panel").classList.add("open");
  await loadProfile();
}

function closeProfile() {
  document.getElementById("profile-panel").classList.remove("open");
}

async function loadProfile() {
  try {
    const res  = await fetch(`/api/profile/${USER_ID}`);
    const data = await res.json();
    const p    = data.profile;

    document.getElementById("pf-name").value = p.name || "";
    document.getElementById("pf-bg").value   = p.background || "";
    _skills = p.skills || [];
    renderSkills();
    renderHistory(data.goals || []);
  } catch (_) {}
}

async function saveProfile() {
  const name       = document.getElementById("pf-name").value.trim();
  const background = document.getElementById("pf-bg").value.trim();
  const btn        = document.getElementById("profile-save-btn");
  btn.textContent  = "儲存中...";
  try {
    await fetch("/api/profile", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: USER_ID, name, background, skills: _skills }),
    });
    btn.textContent = "✓ 已儲存";
    setTimeout(() => { btn.textContent = "儲存"; }, 1500);
  } catch (_) {
    btn.textContent = "儲存失敗";
  }
}

function handleSkillInput(e) {
  if (e.key !== "Enter" && e.key !== ",") return;
  e.preventDefault();
  const val = e.target.value.trim().replace(/,$/, "");
  if (val && !_skills.includes(val)) {
    _skills.push(val);
    renderSkills();
  }
  e.target.value = "";
}

function removeSkill(i) {
  _skills.splice(i, 1);
  renderSkills();
}

function renderSkills() {
  const container = document.getElementById("pf-skills");
  container.innerHTML = _skills.map((s, i) => `
    <span class="pf-tag">
      ${escapeHtml(s)}
      <span class="pf-tag-del" onclick="removeSkill(${i})">×</span>
    </span>`).join("");
}

const GOAL_TYPE_LABELS = {
  travel: "旅行", learning: "學習", project: "專案",
  research: "研究", prompt: "Prompt", general: "一般",
};

function renderHistory(goals) {
  const el = document.getElementById("pf-history");
  if (!goals.length) {
    el.innerHTML = '<div style="color:#334155;font-size:12px">尚無歷史目標</div>';
    return;
  }
  el.innerHTML = goals.map(g => {
    const typeLabel = GOAL_TYPE_LABELS[g.goal_type] || g.goal_type;
    const date = g.created_at ? g.created_at.slice(0, 10) : "";
    return `<div class="pf-history-item" onclick="useHistoryGoal('${escapeHtml(g.description)}')">
      <div class="pf-history-goal">${escapeHtml(g.description)}</div>
      <div class="pf-history-meta">
        <span class="pf-type-badge">${typeLabel}</span>${date}
      </div>
    </div>`;
  }).join("");
}

// 初始化 i18n（DOM ready 後執行）
document.addEventListener('DOMContentLoaded', () => {
  applyI18n();
  // 同步語言按鈕 active 狀態
  document.querySelectorAll('.lang-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.lang === currentLang);
    if (b.dataset.lang === currentLang) b.style.borderColor = '#2563eb';
  });
});

function useHistoryGoal(goal) {
  closeProfile();
  restartSession();
  setTimeout(() => {
    document.getElementById("msg-input").value = goal;
    startSession();
  }, 100);
}

// ── Admin (Priority Sources) ────────────────────────────────────────────────
async function openAdmin() {
  document.getElementById("admin-panel").classList.add("open");
  await loadSources();
}

function closeAdmin() {
  document.getElementById("admin-panel").classList.remove("open");
}

async function loadSources() {
  try {
    const res  = await fetch("/api/sources");
    const data = await res.json();
    renderSources(data.sources || []);
  } catch (_) {
    document.getElementById("src-list").innerHTML =
      '<div style="color:#f87171;font-size:12px">載入失敗</div>';
  }
}

function renderSources(sources) {
  const el = document.getElementById("src-list");
  if (!sources.length) {
    el.innerHTML = '<div style="color:#334155;font-size:12px">尚無來源</div>';
    return;
  }
  el.innerHTML = sources.map(s => {
    const types = JSON.parse(s.goal_types || "[]").join(", ") || "全部";
    const kws   = JSON.parse(s.keywords   || "[]").join(", ") || "無限制";
    return `<div class="src-card">
      <div class="src-card-info">
        <div class="src-name">${escapeHtml(s.name)}</div>
        <div class="src-url">${escapeHtml(s.url)}</div>
        <div class="src-meta">類型：${types} ｜ 關鍵詞：${kws} ｜ 優先度：${s.priority} ｜ ${s.category || "general"} / ${s.ttl_days || 30}天</div>
      </div>
      <button class="src-del-btn" data-sid="${escapeHtml(s.id)}" onclick="deleteSource(this.dataset.sid)">刪除</button>
    </div>`;
  }).join("");
}

async function addSource() {
  const name      = document.getElementById("src-name").value.trim();
  const url       = document.getElementById("src-url").value.trim();
  const keywords  = document.getElementById("src-keywords").value
    .split(",").map(k => k.trim()).filter(Boolean);
  const priority  = parseInt(document.getElementById("src-priority").value) || 100;
  const goalTypes = document.getElementById("src-goal-types").value
    .split(",").map(t => t.trim()).filter(Boolean);
  const vendorId  = document.getElementById("src-vendor-id").value.trim();
  const category  = document.getElementById("src-category").value;
  const ttlRaw    = document.getElementById("src-ttl").value.trim();
  const ttlDays   = ttlRaw !== "" ? parseInt(ttlRaw) : undefined;

  if (!name || !url) { alert("名稱和 URL 為必填"); return; }
  try {
    const body = { name, url, keywords, priority, goal_types: goalTypes, vendor_id: vendorId, category };
    if (ttlDays !== undefined) body.ttl_days = ttlDays;
    await fetch("/api/sources", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    ["src-name","src-url","src-keywords","src-goal-types","src-vendor-id","src-ttl"].forEach(id => {
      document.getElementById(id).value = "";
    });
    document.getElementById("src-priority").value = "100";
    document.getElementById("src-category").value = "general";
    await loadSources();
  } catch (_) {
    alert("新增失敗");
  }
}

// ── Knowledge Base ──────────────────────────────────────────────────────────
async function openKB() {
  document.getElementById("kb-panel").classList.add("open");
  await loadKBStatus();
}

function closeKB() {
  document.getElementById("kb-panel").classList.remove("open");
}

function switchKBTab(name, btn) {
  document.querySelectorAll(".kb-tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".kb-tab-content").forEach(t => t.classList.remove("active"));
  btn.classList.add("active");

  if (name === "browse") {
    // 瀏覽模式：隱藏新增區塊、最近來源，顯示搜尋區塊
    document.getElementById("kb-browse-section").style.display = "flex";
    document.getElementById("kb-recent-section").style.display = "none";
    setTimeout(() => document.getElementById("kb-browse-q").focus(), 50);
  } else {
    document.getElementById("kb-browse-section").style.display = "none";
    document.getElementById("kb-recent-section").style.display = "";
    const tabEl = document.getElementById("kb-tab-" + name);
    if (tabEl) tabEl.classList.add("active");
  }
}

async function loadKBStatus() {
  try {
    const [statusRes, sourcesRes] = await Promise.all([
      fetch("/api/knowledge/status"),
      fetch("/api/knowledge/sources"),
    ]);
    const status  = await statusRes.json();
    const sources = await sourcesRes.json();
    document.getElementById("kb-stats").textContent =
      `${status.chunk_count} chunks ／ ${(sources.sources || []).length} 來源`;
    renderKBSources(sources.sources || []);
  } catch (_) {
    document.getElementById("kb-stats").textContent = "載入失敗";
  }
}

function renderKBSources(sources) {
  const el = document.getElementById("kb-url-list");
  if (!sources.length) {
    el.innerHTML = '<div style="color:#334155;font-size:12px">尚無資料</div>';
    return;
  }
  const catIcon = { concept:'📖', travel:'✈️', learning:'🎓', how_to:'🛠', resource:'🔗', general:'📄', event:'📅' };
  el.innerHTML = sources.map(s => {
    const icon    = catIcon[s.category] || '📄';
    const display = escapeHtml(s.source_name && s.source_name !== s.source ? s.source_name : s.source);
    const srcFull = escapeHtml(s.source);
    return `<div class="kb-url-row" style="display:flex;align-items:center;gap:6px;white-space:normal;overflow:visible">
      <span style="flex-shrink:0">${icon}</span>
      <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${srcFull}">${display}</span>
      <span style="flex-shrink:0;color:#1e3a5f;font-size:10px">${s.count} chunks</span>
      <button onclick="kbDeleteSource(${JSON.stringify(s.source)}, this)" style="
        flex-shrink:0;border:1px solid #3f1111;background:none;border-radius:4px;
        color:#f87171;font-size:10px;padding:2px 6px;cursor:pointer;transition:background 0.15s"
        title="刪除此來源所有 chunks">✕</button>
    </div>`;
  }).join("");
}

async function kbDeleteSource(source, btn) {
  if (!confirm('確定要刪除「' + source + '」的所有 chunks？')) return;
  btn.disabled = true; btn.textContent = '…';
  try {
    const res  = await fetch('/api/knowledge/delete_source', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source }),
    });
    const data = await res.json();
    if (data.ok) {
      await loadKBStatus();
    } else {
      alert('刪除失敗：' + (data.error || '未知錯誤'));
      btn.disabled = false; btn.textContent = '✕';
    }
  } catch(_) {
    alert('連線錯誤');
    btn.disabled = false; btn.textContent = '✕';
  }
}

function _kbResult(elId, ok, msg) {
  const el = document.getElementById(elId);
  if (!el) return;
  el.className = "kb-result " + (ok ? "ok" : "err");
  el.textContent = msg;
  setTimeout(() => { el.textContent = ""; el.className = "kb-result"; }, 4000);
}

async function kbStartCrawl() {
  const topic    = document.getElementById("kb-crawl-topic").value.trim();
  const goalType = document.getElementById("kb-crawl-type").value;
  if (!topic) return;

  const log  = document.getElementById("kb-crawl-log");
  const btn  = document.querySelector('#kb-tab-crawl .kb-btn');
  log.innerHTML = "";
  btn.textContent = t('kb.crawl.running');
  btn.disabled = true;

  const addLog = (text, isResult = false) => {
    const div = document.createElement("div");
    div.textContent = text;
    div.style.color = isResult ? "#34d399" : "#475569";
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  };

  addLog(`▶ ${topic} [${goalType}]`);

  try {
    const res = await fetch("/api/knowledge/crawl", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, goal_type: goalType }),
    });
    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";
    let totalChunks = 0;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split("\\n\\n");
      buf = parts.pop();
      for (const part of parts) {
        if (!part.startsWith("data: ")) continue;
        let evt;
        try { evt = JSON.parse(part.slice(6)); } catch { continue; }
        if (evt.type === "progress") addLog(evt.text);
        else if (evt.type === "done") {
          totalChunks = evt.chunks;
          const msg = totalChunks > 0
            ? t('kb.crawl.done', {count: totalChunks})
            : t('kb.crawl.empty');
          addLog(msg, true);
          await loadKBStatus();
        }
      }
    }
  } catch (_) {
    addLog(t('kb.conn_err'), false);
  }
  btn.textContent = t('kb.crawl.btn');
  btn.disabled = false;
}

async function kbBrowse() {
  const q   = document.getElementById("kb-browse-q").value.trim();
  const el  = document.getElementById("kb-browse-results");
  if (!q) return;
  el.innerHTML = `<div style="color:#475569;font-size:12px">${t('kb.browse.searching')}</div>`;

  try {
    const res  = await fetch(`/api/knowledge/search?q=${encodeURIComponent(q)}&n=10`);
    const data = await res.json();
    if (!data.chunks || data.chunks.length === 0) {
      el.innerHTML = `<div style="color:#334155;font-size:12px">${t('kb.browse.no_result')}</div>`;
      return;
    }
    el.innerHTML = data.chunks.map(c => {
      const src = c.source_name || c.source;
      const isLocal = c.source.startsWith("/files/");
      const srcLink = isLocal
        ? `<a href="${escapeHtml(c.source)}" target="_blank"
              style="color:#60a5fa;font-size:10px;text-decoration:none">📄 ${escapeHtml(src)}</a>`
        : `<span style="color:#334155;font-size:10px;white-space:nowrap;overflow:hidden;
                         text-overflow:ellipsis;display:block">🔗 ${escapeHtml(src)}</span>`;
      return `<div class="nd-rag-chunk">
        <div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
          <span style="font-size:10px;color:#475569">${escapeHtml(c.category_label)}</span>
          ${c.time_sensitive ? `<span style="font-size:10px;color:#fbbf24">${t('rag.time_sensitive')}</span>` : ""}
          <span style="font-size:10px;color:#1e3a5f;margin-left:auto">d=${c.distance}</span>
        </div>
        <div class="nd-rag-text">${escapeHtml(c.text)}</div>
        ${srcLink}
      </div>`;
    }).join("");
  } catch (_) {
    el.innerHTML = `<div style="color:#f87171;font-size:12px">${t('kb.conn_err')}</div>`;
  }
}

async function kbAddURL() {
  const url  = document.getElementById("kb-url").value.trim();
  const name = document.getElementById("kb-url-name").value.trim();
  if (!url) return;
  _kbResult("kb-url-result", true, "爬取中...");
  try {
    const res  = await fetch("/api/knowledge/url", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, source: name }),
    });
    const data = await res.json();
    if (data.ok) {
      const msg = data.cached ? "已快取（7 天內爬過）" : `已加入 ${data.chunks} 個 chunks`;
      _kbResult("kb-url-result", true, "✓ " + msg);
      document.getElementById("kb-url").value = "";
      await loadKBStatus();
    } else {
      _kbResult("kb-url-result", false, "✗ " + (data.error || "失敗"));
    }
  } catch (_) {
    _kbResult("kb-url-result", false, "✗ 連線錯誤");
  }
}

async function kbAddText() {
  const text   = document.getElementById("kb-text").value.trim();
  const source = document.getElementById("kb-text-source").value.trim() || "手動輸入";
  if (!text) return;
  try {
    const res  = await fetch("/api/knowledge/text", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, source }),
    });
    const data = await res.json();
    if (data.ok) {
      _kbResult("kb-text-result", true, `✓ 已加入 ${data.chunks} 個 chunks`);
      document.getElementById("kb-text").value = "";
      await loadKBStatus();
    } else {
      _kbResult("kb-text-result", false, "✗ " + (data.error || "失敗"));
    }
  } catch (_) {
    _kbResult("kb-text-result", false, "✗ 連線錯誤");
  }
}

async function kbUploadPDF() {
  const fileInput = document.getElementById("kb-pdf-file");
  const file      = fileInput.files[0];
  if (!file) { alert("請選擇 PDF 檔案"); return; }

  const name     = document.getElementById("kb-pdf-name").value.trim();
  const category = document.getElementById("kb-pdf-category").value;

  _kbResult("kb-pdf-result", true, "解析中...");
  const form = new FormData();
  form.append("file", file);
  form.append("source_name", name);
  form.append("category", category);

  try {
    const res  = await fetch("/api/knowledge/pdf", { method: "POST", body: form });
    const data = await res.json();
    if (data.ok) {
      _kbResult("kb-pdf-result", true,
        `✓ 已加入 ${data.chunks} 個 chunks（${escapeHtml(data.filename)}）`);
      fileInput.value = "";
      document.getElementById("kb-pdf-name").value = "";
      await loadKBStatus();
    } else {
      _kbResult("kb-pdf-result", false, "✗ " + (data.error || "失敗"));
    }
  } catch (_) {
    _kbResult("kb-pdf-result", false, "✗ 連線錯誤");
  }
}

async function kbAddJSONL() {
  const content = document.getElementById("kb-jsonl").value.trim();
  const source  = document.getElementById("kb-jsonl-source").value.trim() || "匯入";
  if (!content) return;
  try {
    const res  = await fetch("/api/knowledge/jsonl", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, source }),
    });
    const data = await res.json();
    if (data.ok) {
      const warn = data.errors ? `（${data.errors} 行解析失敗）` : "";
      _kbResult("kb-jsonl-result", true, `✓ 已匯入 ${data.chunks} 個 chunks ${warn}`);
      document.getElementById("kb-jsonl").value = "";
      await loadKBStatus();
    } else {
      _kbResult("kb-jsonl-result", false, "✗ " + (data.error || "失敗"));
    }
  } catch (_) {
    _kbResult("kb-jsonl-result", false, "✗ 連線錯誤");
  }
}

async function deleteSource(sourceId) {
  if (!confirm(t('adm.confirm_del'))) return;
  try {
    await fetch(`/api/sources/${encodeURIComponent(sourceId)}`, { method: "DELETE" });
    await loadSources();
  } catch (_) {
    alert("刪除失敗");
  }
}

// ── Popular Nodes ──────────────────────────────────────────────────────────
async function _loadPopularNodes() {
  try {
    const res  = await fetch('/api/popular_nodes?min_count=2&limit=30');
    const data = await res.json();
    _popularNames.clear();
    (data.nodes || []).forEach(n => _popularNames.add(n.name));
    // autoPauseRedraw(false) 讓 force-graph 持續重繪，不需要手動 refresh
  } catch(e) { /* silent */ }
}

// ── Onboarding ────────────────────────────────────────────────────────────
(function _initOnboarding() {
  const overlay = document.getElementById('welcome-overlay');
  const card    = document.getElementById('onboarding-card');
  if (!overlay || !card) return;
  const seen = localStorage.getItem('ragraphe_onboarded');
  if (!seen) {
    card.style.display = 'block';
    overlay.classList.add('interactive');
  }
})();

function dismissOnboarding() {
  localStorage.setItem('ragraphe_onboarded', '1');
  const overlay = document.getElementById('welcome-overlay');
  const card    = document.getElementById('onboarding-card');
  if (card)    card.style.display = 'none';
  if (overlay) overlay.classList.remove('interactive');
}

// ── Completion Card ────────────────────────────────────────────────────────
async function _showCompletionCard() {
  if (!sessionId) return;
  try {
    const res  = await fetch('/api/export_markdown', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    });
    const data = await res.json();
    if (!data.stats) return;
    const s = data.stats;
    const div = document.createElement('div');
    div.className = 'msg-complete';
    div.innerHTML =
      '<div class="msg-complete-title">🎉 路徑規劃完成！</div>' +
      '<div class="msg-complete-stats">' +
        '<div class="mcs-item"><span class="mcs-num mcs-done">' + s.done + '</span><span class="mcs-label">已完成</span></div>' +
        '<div class="mcs-item"><span class="mcs-num mcs-todo">' + s.todo + '</span><span class="mcs-label">待完成</span></div>' +
        '<div class="mcs-item"><span class="mcs-num mcs-skip">' + s.skip + '</span><span class="mcs-label">已跳過</span></div>' +
      '</div>' +
      '<button class="msg-complete-export" onclick="exportMarkdown()">📥 匯出 Markdown Checklist</button>';
    const msgs = document.getElementById('messages');
    if (msgs) { msgs.appendChild(div); msgs.scrollTop = msgs.scrollHeight; }
  } catch(e) { /* silent */ }
}

// ── Export Markdown ────────────────────────────────────────────────────────
async function exportMarkdown() {
  if (!sessionId) return;
  try {
    const res  = await fetch('/api/export_markdown', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    });
    const data = await res.json();
    if (data.markdown) _showExportModal(data.markdown);
    else alert(data.error || '匯出失敗');
  } catch(e) {
    alert('連線錯誤');
  }
}

// ── Export Prompt ─────────────────────────────────────────────────────────
async function exportPrompt() {
  const btn = document.getElementById('export-prompt-btn');
  if (!sessionId) return;
  btn.disabled = true;
  btn.textContent = '⏳ 生成中…';
  try {
    const res  = await fetch('/api/export_prompt', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId }),
    });
    const data = await res.json();
    if (data.prompt) _showExportModal(data.prompt);
    else alert(data.error || '生成失敗，請稍後再試');
  } catch(e) {
    alert('連線錯誤');
  } finally {
    btn.disabled = false;
    btn.textContent = '📋 匯出為 Prompt';
  }
}

function _showExportModal(text) {
  const modal = document.getElementById('export-modal');
  document.getElementById('export-modal-text').value = text;
  modal.classList.add('open');
}

function _closeExportModal() {
  document.getElementById('export-modal').classList.remove('open');
}

async function _copyExportPrompt() {
  const ta  = document.getElementById('export-modal-text');
  const btn = document.getElementById('export-copy-btn');
  try {
    await navigator.clipboard.writeText(ta.value);
    btn.textContent = '✓ 已複製！';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = '複製'; btn.classList.remove('copied'); }, 2000);
  } catch { ta.select(); document.execCommand('copy'); }
}

// 點 modal 背景關閉
document.getElementById('export-modal').addEventListener('click', e => {
  if (e.target === e.currentTarget) _closeExportModal();
});
</script>

<!-- Sessions Panel -->
<div id="sessions-panel" onclick="if(event.target===this) closeSessions()">
  <div id="sessions-inner">
    <div id="sessions-header">
      <h2>歷史 Sessions</h2>
      <button onclick="closeSessions()">✕</button>
    </div>
    <div id="sessions-list"></div>
    <div id="sessions-footer">
      <button id="sessions-new-btn" onclick="closeSessions(); restartSession()">＋ 開始新 Session</button>
    </div>
  </div>
</div>

<!-- Export Prompt Modal -->
<div id="export-modal">
  <div id="export-modal-box">
    <div id="export-modal-header">
      <span>📋 匯出為 Prompt</span>
      <button id="export-modal-close" onclick="_closeExportModal()">✕</button>
    </div>
    <div id="export-modal-body">
      <textarea id="export-modal-text" readonly></textarea>
    </div>
    <div id="export-modal-footer">
      <button id="export-copy-btn" onclick="_copyExportPrompt()">複製</button>
    </div>
  </div>
</div>

</body>
</html>"""
