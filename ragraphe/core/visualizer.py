"""
Path visualization: left-to-right layout, supports both task skeleton and day-by-day travel skeleton.
"""
import re
import json
import webbrowser
from pathlib import Path
from ragraphe.db.store import nodes_collection

OUTPUT_PATH = Path(__file__).parent.parent.parent / "data" / "path.html"

SOURCE_X = -420
SINK_X   =  420

# Day-column layout constants (must stay in sync with front-end JS)
DAY_COL_SPAN   = 300   # center-to-center distance between columns (canvas units)
DAY_COL_HALF_W = 120   # half-width of a column (used for background rendering)
DAY_SUB_Y_START = 120  # y of the first child node (relative to Day node y=0)
DAY_SUB_Y_STEP  = 90   # vertical spacing between child nodes


# ── Parse endpoints ─────────────────────────────────────────────────────────

_TRAVEL_RE   = re.compile(r'旅行|旅遊|出遊|出國|去.{1,6}玩|景點|行程|trip|travel', re.IGNORECASE)
_LEARNING_RE = re.compile(r'學習|學某|讀|課程|技能|入門|進階|self.study', re.IGNORECASE)
_PROJECT_RE  = re.compile(r'開發|專案|產品|創業|設計|製作|build|create', re.IGNORECASE)
_PROMPT_RE   = re.compile(r'prompt|提示詞|system prompt|給AI|讓AI|AI助手|AI指令', re.IGNORECASE)


def _parse_endpoints(goal: str, context: str) -> tuple[str, str]:
    # ── Destination (sink label) ─────────────────────────────────
    # Prompt type: always display "Complete Prompt"
    if _PROMPT_RE.search(goal):
        dest = "完整 Prompt"
    else:
        dest = "目標達成"
        m = re.search(r'去([^\s，,。！!？?]{1,8})(?:旅行|旅遊|玩|工作|留學|生活)?', goal)
        if m:
            dest = m.group(1)
        else:
            m = re.search(r'(?:travel to|visit|go to)\s+([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)', goal, re.IGNORECASE)
            if m:
                dest = m.group(1)
            else:
                # Strip leading phrases like "I want to" and take the core goal text
                clean = re.sub(r'^(我想|我要|想要|希望|計畫|打算)\s*', '', goal.strip())
                if clean:
                    dest = clean[:12]

    # ── Departure point (source label) ───────────────────────────
    dep = None
    for pat in [
        r'從([^\s，,。；;]{1,8})出發',
        r'([^\s，,。；;]{1,8})出發',
        r'出發地[：:]\s*([^\s，,。；;]{1,8})',
        r'(?:from|departing from)\s+([A-Za-z]+)',
    ]:
        m = re.search(pat, context, re.IGNORECASE)
        if m:
            dep = m.group(1).strip()
            break

    if not dep:
        # Fall back to a default source label based on goal type
        if _PROMPT_RE.search(goal):
            dep = "需求定義"       # Prompt：從釐清需求開始
        elif _TRAVEL_RE.search(goal):
            dep = "？出發地"       # 旅行：出發地未知（橙色警示）
        elif _LEARNING_RE.search(goal):
            dep = "目前程度"       # 學習：起點是現有程度
        elif _PROJECT_RE.search(goal):
            dep = "起點"           # 專案：起點
        else:
            dep = "現況"           # 通用

    return dep, dest


def _get_node_content(node_id: str, n: int = 4) -> list[str]:
    try:
        result = nodes_collection.get(ids=[node_id], include=["documents"])
        if result["documents"] and result["documents"][0]:
            doc = result["documents"][0]
            chunks = [s.strip() for s in doc.split('\n') if len(s.strip()) > 30]
            return chunks[:n] if chunks else [doc[:400]]
    except Exception:
        pass
    return []


# ── Determine skeleton type ──────────────────────────────────────────────────

def _get_day_num(n: dict) -> int:
    """Get the day number from a node: prefers the 'day' field, falls back to parsing day_N id."""
    if isinstance(n.get("day"), int):
        return n["day"]
    m = re.search(r'\d+', n.get("id", ""))
    return int(m.group()) if m else 999


def _is_day_based(nodes: list) -> bool:
    return (any(isinstance(n.get("day"), int) for n in nodes) or
            any(re.match(r'^day_\d+$', n.get("id", "")) for n in nodes))


# ── Day-by-day travel skeleton visualization (timeline block mode) ──────────

def _build_day_vis_data(nodes: list, edges: list) -> tuple[list, list]:
    """
    Network graph mode: Day nodes are large hubs, child nodes cluster around their parent,
    and the physics engine handles automatic layout.
    """
    day_ids  = {n["id"] for n in nodes
                if re.match(r'^day_\d+$', n.get("id", "")) or isinstance(n.get("day"), int)}
    day_nodes = sorted([n for n in nodes if n["id"] in day_ids], key=_get_day_num)
    sub_nodes = [n for n in nodes if n["id"] not in day_ids]
    num_days  = len(day_nodes)

    if num_days == 0:
        return [], []

    # Group child nodes by parent
    parent_children: dict[str, list] = {}
    for n in sub_nodes:
        pid = n.get("parent_id", "")
        if pid in day_ids:
            parent_children.setdefault(pid, []).append(n)

    vis_nodes = []
    vis_edges = []

    STATUS_NODE = {
        "done":    {"bg": "#14532d", "border": "#22c55e", "font": "#4ade80"},
        "todo":    {"bg": "#0f2744", "border": "#2563eb", "font": "#93c5fd"},
        "skip":    {"bg": "#1c1c1c", "border": "#374151", "font": "#4b5563"},
        "unknown": {"bg": "#2d1a00", "border": "#f59e0b", "font": "#fcd34d"},
    }

    # --- Source ---
    vis_nodes.append({
        "id": "__source__", "label": "出發",
        "shape": "dot", "size": 28,
        "color": {"background": "#0f4c75", "border": "#1b6ca8"},
        "font":  {"color": "#90caf9", "size": 13, "bold": True},
        "shadow": {"enabled": True, "color": "#1b6ca8", "size": 8, "x": 0, "y": 0},
        "hidden": False,
        "_status": "source", "_reason": "出發點", "_description": "",
        "_children": [], "_parent": None, "_level": 0,
    })

    # --- Day nodes (large hubs) ---
    for n in day_nodes:
        nid      = n["id"]
        children = parent_children.get(nid, [])
        child_ids = [c["id"] for c in children]
        status   = n.get("status", "unknown")
        sc       = STATUS_NODE.get(status, STATUS_NODE["todo"])

        vis_nodes.append({
            "id": nid, "label": n["name"],
            "shape": "dot", "size": 32,
            "color": {"background": sc["bg"], "border": sc["border"]},
            "font":  {"color": sc["font"], "size": 14, "bold": True},
            "hidden": False,
            "shadow": {"enabled": True, "color": sc["border"], "size": 10, "x": 0, "y": 0},
            "_status":      status,
            "_reason":      n.get("reason", ""),
            "_description": n.get("description", ""),
            "_children":    child_ids,
            "_parent":      None,
            "_level":       1,
            "_day":         _get_day_num(n),
        })

        # --- Child nodes (floating; physics engine attracts them to the parent) ---
        for c in children:
            cid   = c["id"]
            cstat = c.get("status", "todo")
            sc2   = STATUS_NODE.get(cstat, STATUS_NODE["todo"])
            vis_nodes.append({
                "id": cid, "label": c["name"],
                "shape": "dot", "size": 18,
                "color": {"background": sc2["bg"], "border": sc2["border"]},
                "font":  {"color": sc2["font"], "size": 12},
                "hidden": False,
                "shadow": {"enabled": True, "color": sc2["border"], "size": 5, "x": 0, "y": 0},
                "_status":      cstat,
                "_reason":      c.get("reason", ""),
                "_description": c.get("description", ""),
                "_children":    [],
                "_parent":      nid,
                "_level":       2,
            })

    # --- Sink ---
    vis_nodes.append({
        "id": "__sink__", "label": "目標達成",
        "shape": "dot", "size": 28,
        "color": {"background": "#1a3a1a", "border": "#22c55e"},
        "font":  {"color": "#4ade80", "size": 13, "bold": True},
        "shadow": {"enabled": True, "color": "#22c55e", "size": 8, "x": 0, "y": 0},
        "hidden": False,
        "_status": "sink", "_reason": "目的地", "_description": "",
        "_children": [], "_parent": None, "_level": 0,
    })

    # --- Backbone edges: source → day_1 → ... → sink ---
    prev = "__source__"
    for n in day_nodes:
        vis_edges.append({
            "id": f"{prev}→{n['id']}", "from": prev, "to": n["id"],
            "arrows": "to", "hidden": False,
            "dashes": False, "width": 2.5,
            "color": {"color": "#2563eb", "opacity": 0.7},
        })
        prev = n["id"]
    vis_edges.append({
        "id": f"{prev}→__sink__", "from": prev, "to": "__sink__",
        "arrows": "to", "hidden": False,
        "dashes": False, "width": 2.5,
        "color": {"color": "#22c55e", "opacity": 0.7},
    })

    # --- Child node edges (day → sub, dashed) ---
    for pid, children in parent_children.items():
        for c in children:
            vis_edges.append({
                "id": f"__sub__{pid}__{c['id']}", "from": pid, "to": c["id"],
                "arrows": "to", "hidden": False,
                "dashes": True, "width": 1,
                "color": {"color": "#1e3a5f", "opacity": 0.5},
            })

    return vis_nodes, vis_edges


# ── Task skeleton visualization ─────────────────────────────────────────────

def _build_task_vis_data(goal: str, context: str, nodes: list, edges: list) -> tuple[list, list]:
    departure, destination = _parse_endpoints(goal, context)
    is_unknown_dep = departure.startswith("？")

    SOURCE_ID = "__source__"
    SINK_ID   = "__sink__"

    status_map = {n["id"]: n.get("status", "todo") for n in nodes}
    vis_nodes  = []
    vis_edges  = []

    # Source node
    vis_nodes.append({
        "id": SOURCE_ID,
        "label": departure,
        "x": SOURCE_X, "y": 0,
        "fixed": {"x": True, "y": True},
        "shape": "box",
        "color": {
            "background": "#2d1a00" if is_unknown_dep else "#0f4c75",
            "border":     "#f59e0b" if is_unknown_dep else "#1b6ca8",
        },
        "font": {
            "color": "#fcd34d" if is_unknown_dep else "#90caf9",
            "size": 14, "bold": True,
        },
        "dashes": is_unknown_dep,
        "hidden": False,
        "_status":  "unknown" if is_unknown_dep else "source",
        "_reason":  "尚未確認出發地" if is_unknown_dep else "出發地",
        "_content": [], "_children": [], "_parent": None, "_level": 0,
    })

    STATUS_COLORS = {
        "done": {"bg": "#14532d", "border": "#22c55e", "font": "#4ade80"},
        "todo": {"bg": "#0f2744", "border": "#2563eb", "font": "#93c5fd"},
        "skip": {"bg": "#1c1c1c", "border": "#374151", "font": "#4b5563"},
    }
    for n in nodes:
        nid    = n["id"]
        status = n.get("status", "todo")
        c      = STATUS_COLORS.get(status, STATUS_COLORS["todo"])
        level  = n.get("level", 1)
        vis_nodes.append({
            "id":    nid,
            "label": n["name"],
            "hidden": level > 1,
            "shape": "ellipse" if status != "skip" else "box",
            "color": {"background": c["bg"], "border": c["border"]},
            "font":  {"color": c["font"], "size": 13},
            "dashes": status == "skip",
            "shadow": {"enabled": True, "color": c["border"], "size": 6, "x": 0, "y": 0},
            "_status":      status,
            "_reason":      n.get("reason", ""),
            "_content":     _get_node_content(nid),
            "_children":    n.get("children", []),
            "_parent":      n.get("parent_id"),
            "_level":       level,
            "_description": n.get("description", ""),
        })

    # Sink node
    vis_nodes.append({
        "id": SINK_ID,
        "label": destination,
        "x": SINK_X, "y": 0,
        "fixed": {"x": True, "y": True},
        "shape": "box",
        "color": {"background": "#1a3a1a", "border": "#22c55e"},
        "font":  {"color": "#4ade80", "size": 14, "bold": True},
        "hidden": False,
        "_status": "sink", "_reason": "目的地", "_content": [],
        "_children": [], "_parent": None, "_level": 0,
    })

    edge_counter = [0]
    def make_edge(from_id, to_id, done=False, hidden=False, eid=None):
        edge_counter[0] += 1
        return {
            "id":    eid or f"{from_id}→{to_id}",
            "from":  from_id, "to": to_id,
            "arrows": "to", "hidden": hidden,
            "dashes": not done,
            "width":  2.5 if done else 1,
            "color":  {"color": "#22c55e" if done else "#2563eb", "opacity": 0.8 if done else 0.5},
        }

    l1_ids = {n["id"] for n in nodes if n.get("level", 1) == 1}
    l1_has_pred = {e["to_id"] for e in edges if e["from_id"] in l1_ids and e["to_id"] in l1_ids}
    roots = [nid for nid in l1_ids if nid not in l1_has_pred]
    for nid in roots:
        vis_edges.append(make_edge(SOURCE_ID, nid, done=status_map.get(nid) == "done"))

    for e in edges:
        f, t = e["from_id"], e["to_id"]
        if f in l1_ids and t in l1_ids:
            done = status_map.get(f) == "done" and status_map.get(t) == "done"
            vis_edges.append(make_edge(f, t, done=done))

    l1_has_succ = {e["from_id"] for e in edges if e["from_id"] in l1_ids and e["to_id"] in l1_ids}
    for nid in l1_ids:
        if nid not in l1_has_succ:
            vis_edges.append(make_edge(nid, SINK_ID, done=status_map.get(nid) == "done"))

    l2_ids = {n["id"] for n in nodes if n.get("level", 1) == 2}
    for e in edges:
        f, t = e["from_id"], e["to_id"]
        if f in l2_ids or t in l2_ids:
            vis_edges.append(make_edge(f, t, done=False, hidden=True))

    for n in nodes:
        if n.get("level", 1) == 2:
            pid = n.get("parent_id")
            if pid:
                eid = f"__parent__{pid}__{n['id']}"
                vis_edges.append({
                    "id": eid,
                    "from": pid, "to": n["id"],
                    "arrows": "to", "hidden": True,
                    "dashes": True, "width": 1,
                    "color": {"color": "#374151", "opacity": 0.6},
                })

    return vis_nodes, vis_edges


# ── Streaming helpers (for API use) ─────────────────────────────────────────

# Status colors shared
_STATUS_COLORS = {
    "done":    {"bg": "#14532d", "border": "#22c55e", "font": "#4ade80"},
    "todo":    {"bg": "#0f2744", "border": "#2563eb", "font": "#93c5fd"},
    "skip":    {"bg": "#1c1c1c", "border": "#374151", "font": "#4b5563"},
    "unknown": {"bg": "#2d1a00", "border": "#f59e0b", "font": "#fcd34d"},
}

def node_to_vis(node: dict, mode: str, all_nodes: list) -> dict:
    """Convert a single skeleton node → vis.js node dict (for streaming)"""
    nid    = node["id"]
    status = node.get("status", "todo")
    level  = node.get("level", 1)

    STATUS_COLORS_DAY = {
        "done":    {"bg": "#14532d", "border": "#22c55e", "font": "#4ade80"},
        "todo":    {"bg": "#0f2744", "border": "#2563eb", "font": "#93c5fd"},
        "skip":    {"bg": "#1c1c1c", "border": "#374151", "font": "#4b5563"},
        "unknown": {"bg": "#2d1a00", "border": "#f59e0b", "font": "#fcd34d"},
    }
    if mode == "day":
        if re.match(r'^day_\d+$', nid):
            sc = STATUS_COLORS_DAY.get(status, STATUS_COLORS_DAY["todo"])
            return {
                "id": nid, "label": node.get("name", nid),
                "shape": "dot", "size": 32,
                "color": {"background": sc["bg"], "border": sc["border"]},
                "font":  {"color": sc["font"], "size": 14, "bold": True},
                "hidden": False,
                "shadow": {"enabled": True, "color": sc["border"], "size": 10, "x": 0, "y": 0},
                "_status": status, "_reason": node.get("reason", ""),
                "_description": node.get("description", ""),
                "_children": [], "_parent": None, "_level": 1,
                "_day": _get_day_num(node),
            }
        else:
            pid = node.get("parent_id", "")
            sc  = STATUS_COLORS_DAY.get(status, STATUS_COLORS_DAY["todo"])
            return {
                "id": nid, "label": node.get("name", nid),
                "shape": "dot", "size": 18,
                "color": {"background": sc["bg"], "border": sc["border"]},
                "font":  {"color": sc["font"], "size": 12},
                "hidden": False,
                "shadow": {"enabled": True, "color": sc["border"], "size": 5, "x": 0, "y": 0},
                "_status": status, "_reason": node.get("reason", ""),
                "_description": node.get("description", ""),
                "_children": [], "_parent": pid, "_level": 2,
            }
    else:
        # task skeleton mode
        c = _STATUS_COLORS.get(status, _STATUS_COLORS["todo"])
        return {
            "id":    nid,
            "label": node.get("name", nid),
            "hidden": level > 1 and status != "unknown",
            "shape": "ellipse" if status != "skip" else "box",
            "color": {"background": c["bg"], "border": c["border"]},
            "font":  {"color": c["font"], "size": 13},
            "dashes": status in ("skip", "unknown"),
            "shadow": {"enabled": True, "color": c["border"], "size": 6, "x": 0, "y": 0},
            "_status":      status,
            "_reason":      node.get("reason", ""),
            "_description": node.get("description", ""),
            "_children":    node.get("children", []),
            "_parent":      node.get("parent_id"),
            "_level":       level,
        }


def edge_to_vis(from_id: str, to_id: str, mode: str, is_sub: bool = False) -> dict:
    """Make a vis.js edge dict for streaming"""
    eid = f"{from_id}→{to_id}"
    if mode == "day":
        if is_sub:
            return {
                "id": f"__sub__{from_id}__{to_id}",
                "from": from_id, "to": to_id,
                "arrows": "to", "hidden": False,
                "dashes": True, "width": 1,
                "color": {"color": "#1e3a5f", "opacity": 0.5},
            }
        color = "#22c55e" if to_id == "__sink__" else "#2563eb"
        return {
            "id": eid, "from": from_id, "to": to_id,
            "arrows": "to", "hidden": False,
            "dashes": False, "width": 2.5,
            "color": {"color": color, "opacity": 0.7},
        }
    else:
        return {
            "id": eid, "from": from_id, "to": to_id,
            "arrows": "to", "hidden": False,
            "dashes": True, "width": 1,
            "color": {"color": "#2563eb", "opacity": 0.5},
        }


# ── Unified entry point ─────────────────────────────────────────────────────

def _build_vis_data(goal: str, context: str, result: dict) -> tuple[list, list]:
    nodes = result.get("nodes", [])
    edges = result.get("edges", [])
    if _is_day_based(nodes):
        return _build_day_vis_data(nodes, edges)
    else:
        return _build_task_vis_data(goal, context, nodes, edges)


def build_graph_data(goal: str, context: str, result: dict) -> dict:
    """Return JSON-serializable graph data for API consumption."""
    vis_nodes, vis_edges = _build_vis_data(goal, context, result)
    mode = "day" if _is_day_based(result.get("nodes", [])) else "task"
    return {"nodes": vis_nodes, "edges": vis_edges, "mode": mode}


# ── HTML generation (standalone use) ────────────────────────────────────────

def generate(goal: str, context: str, result: dict, open_browser: bool = True) -> str:
    vis_nodes, vis_edges = _build_vis_data(goal, context, result)
    mode = "day" if _is_day_based(result.get("nodes", [])) else "task"
    nodes_json = json.dumps(vis_nodes, ensure_ascii=False)
    edges_json = json.dumps(vis_edges, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>Ragraphe — {goal}</title>
<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ display: flex; height: 100vh; background: #060a12; color: #e2e8f0;
         font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
  #graph {{ flex: 1; position: relative; }}
  #hint-expand {{
    position: absolute; top: 16px; left: 50%; transform: translateX(-50%);
    background: rgba(6,10,18,0.85); border: 1px solid #1e293b;
    padding: 6px 14px; border-radius: 99px; font-size: 12px; color: #475569;
    pointer-events: none;
  }}
  #panel {{
    width: 320px; min-width: 320px; height: 100vh;
    background: #0a0e18; border-left: 1px solid #1e293b;
    display: flex; flex-direction: column; overflow: hidden;
  }}
  #panel-header {{
    padding: 18px 20px; border-bottom: 1px solid #1e293b; background: #080c16;
  }}
  .goal-label {{ font-size: 10px; color: #38bdf8; text-transform: uppercase; letter-spacing: 1.5px; margin-bottom: 5px; }}
  .goal-text {{ font-size: 15px; font-weight: 600; color: #f1f5f9; line-height: 1.4; }}
  #panel-body {{ flex: 1; overflow-y: auto; padding: 20px; }}
  #node-name {{ font-size: 17px; font-weight: 700; margin-bottom: 8px; color: #f8fafc; }}
  #node-desc {{ font-size: 13px; color: #64748b; margin-bottom: 12px; line-height: 1.5; }}
  #node-status {{ font-size: 11px; padding: 3px 10px; border-radius: 99px; display: inline-block; margin-bottom: 14px; }}
  #node-reason {{ font-size: 13px; color: #94a3b8; line-height: 1.65; margin-bottom: 20px;
                  border-left: 3px solid #1e3a5f; padding-left: 12px; }}
  .expand-btn {{ display: block; width: 100%; padding: 8px; margin-bottom: 16px;
    background: #0f2744; border: 1px solid #2563eb; border-radius: 6px;
    color: #60a5fa; font-size: 13px; cursor: pointer; text-align: center; }}
  .expand-btn:hover {{ background: #1e3a5f; }}
  .chunk {{ background: #080c16; border: 1px solid #1e293b; border-radius: 8px;
            padding: 12px; margin-bottom: 8px; font-size: 12.5px; line-height: 1.75; color: #cbd5e1; }}
  .no-content {{ color: #374151; font-size: 13px; font-style: italic; }}
  #hint {{ color: #374151; font-size: 13px; line-height: 1.8; padding-top: 8px; }}
  .s-done {{ background: #14532d; color: #4ade80; }}
  .s-todo {{ background: #0f2744; color: #60a5fa; }}
  .s-skip {{ background: #1c1c1c; color: #4b5563; }}
  .s-unknown {{ background: #2d1a00; color: #fcd34d; }}
  .s-source, .s-sink {{ background: #0a1f38; color: #93c5fd; }}
  ::-webkit-scrollbar {{ width: 5px; }}
  ::-webkit-scrollbar-thumb {{ background: #1e293b; border-radius: 3px; }}
</style>
</head>
<body>
<div id="graph">
  <div id="hint-expand">點擊節點查看詳情，雙擊展開子步驟</div>
</div>
<div id="panel">
  <div id="panel-header">
    <div class="goal-label">目標</div>
    <div class="goal-text">{goal}</div>
  </div>
  <div id="panel-body">
    <p id="hint">← 點擊節點查看詳情<br>雙擊展開子步驟</p>
  </div>
</div>
<script>
const RAW_NODES = {nodes_json};
const RAW_EDGES = {edges_json};
const MODE = "{mode}";
const SOURCE_X = {SOURCE_X};
const SINK_X   = {SINK_X};
const STATUS_LABEL = {{"done":"✅ 已完成","todo":"🔲 待完成","skip":"⏭️ 跳過",
  "source":"📍 出發地","sink":"🎯 目的地","unknown":"❓ 未確認"}};

const nodesDS = new vis.DataSet(RAW_NODES.map(n => ({{
  id: n.id, label: n.label,
  x: n.x, y: n.y, fixed: n.fixed, hidden: n.hidden,
  shape: n.shape, color: n.color, font: n.font,
  dashes: n.dashes, shadow: n.shadow, size: n.size || 20,
}})));
const edgesDS = new vis.DataSet(RAW_EDGES);
const nodeData = {{}};
RAW_NODES.forEach(n => {{ nodeData[n.id] = n; }});

const network = new vis.Network(
  document.getElementById("graph"),
  {{ nodes: nodesDS, edges: edgesDS }},
  {{
    physics: {{
      enabled: true,
      solver: "forceAtlas2Based",
      forceAtlas2Based: {{
        gravitationalConstant: -40, centralGravity: 0.015,
        springLength: 100, springConstant: 0.1, damping: 0.7, avoidOverlap: 1.0,
      }},
      stabilization: {{ iterations: 300, updateInterval: 30 }},
      minVelocity: 0.5,
    }},
    interaction: {{ hover: true }},
    edges: {{ smooth: {{ type: "dynamic", roundness: 0.3 }} }},
    nodes: {{ borderWidth: 2 }},
  }}
);

if (MODE === "task") {{
  network.on("beforeDrawing", ctx => {{
    const scale = network.getScale();
    const H = 8000;
    ctx.save();
    ctx.lineWidth = 1.5 / scale;
    ctx.setLineDash([12/scale, 6/scale]);
    ctx.strokeStyle = "rgba(37,99,235,0.18)";
    ctx.beginPath(); ctx.moveTo(SOURCE_X, -H); ctx.lineTo(SOURCE_X, H); ctx.stroke();
    ctx.strokeStyle = "rgba(34,197,94,0.18)";
    ctx.beginPath(); ctx.moveTo(SINK_X, -H); ctx.lineTo(SINK_X, H); ctx.stroke();
    ctx.restore();
  }});
}}

network.on("stabilized", () => {{
  network.setOptions({{ physics: {{ enabled: false }} }});
  if (MODE === "task") {{
    const positions = network.getPositions();
    const updates = [];
    Object.entries(positions).forEach(([id, pos]) => {{
      if (id === "__source__" || id === "__sink__") return;
      const nx = Math.max(SOURCE_X + 60, Math.min(SINK_X - 60, pos.x));
      const ny = Math.max(-600, Math.min(600, pos.y));
      if (nx !== pos.x || ny !== pos.y) updates.push({{ id, x: nx, y: ny }});
    }});
    if (updates.length) nodesDS.update(updates);
  }}
}});

const expanded = new Set();

function toggleExpand(nodeId) {{
  const n = nodeData[nodeId];
  if (!n || !n._children || n._children.length === 0) return;
  if (expanded.has(nodeId)) {{
    n._children.forEach(cid => nodesDS.update({{ id: cid, hidden: true }}));
    RAW_EDGES.forEach(e => {{
      if (e.id && e.id.startsWith(`__parent__${{nodeId}}__`))
        edgesDS.update({{ id: e.id, hidden: true }});
    }});
    expanded.delete(nodeId);
  }} else {{
    n._children.forEach(cid => nodesDS.update({{ id: cid, hidden: false }}));
    RAW_EDGES.forEach(e => {{
      if (e.id && e.id.startsWith(`__parent__${{nodeId}}__`))
        edgesDS.update({{ id: e.id, hidden: false }});
    }});
    expanded.add(nodeId);
    network.setOptions({{ physics: {{ enabled: true }} }});
    network.once("stabilized", () => network.setOptions({{ physics: {{ enabled: false }} }}));
  }}
}}

network.on("click", params => {{
  if (!params.nodes.length) return;
  const n = nodeData[params.nodes[0]];
  if (!n) return;
  const body = document.getElementById("panel-body");
  const sc = "s-" + n._status;
  const sl = STATUS_LABEL[n._status] || n._status;
  const descHTML = n._description ? `<div id="node-desc">${{n._description}}</div>` : "";
  const reasonHTML = n._reason && !["source","sink"].includes(n._status)
    ? `<div id="node-reason">${{n._reason}}</div>` : "";
  const hasChildren = n._children && n._children.length > 0;
  const expandBtnHTML = hasChildren
    ? `<button class="expand-btn" onclick="toggleExpand('${{n.id}}')">${{expanded.has(n.id) ? "▲ 收合子步驟" : "▼ 展開子步驟 (" + n._children.length + ")"}}</button>`
    : "";
  let contentHTML = "";
  if (n._content && n._content.length) {{
    contentHTML = n._content.map(c => `<div class="chunk">${{c}}</div>`).join("");
  }}
  body.innerHTML = `
    <div id="node-name">${{n.label}}</div>
    <span id="node-status" class="${{sc}}">${{sl}}</span>
    ${{descHTML}}${{reasonHTML}}${{expandBtnHTML}}${{contentHTML}}
  `;
}});

network.on("doubleClick", params => {{
  if (!params.nodes.length) return;
  toggleExpand(params.nodes[0]);
}});
</script>
</body>
</html>"""

    OUTPUT_PATH.parent.mkdir(exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    if open_browser:
        webbrowser.open(f"file://{OUTPUT_PATH.resolve()}")
    return str(OUTPUT_PATH)
