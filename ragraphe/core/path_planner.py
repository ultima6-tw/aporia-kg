"""
Path planner: the LLM decides the skeleton type and goal category; no hard-coded logic here.
"""
import json
import re
from ragraphe.llm.ollama_client import chat, chat_stream, embed
from ragraphe.db.store import upsert_node, add_edge

SYSTEM = """你是路徑規劃助手。根據使用者目標生成達成路徑。只輸出 JSON，不要說明文字。"""

# ── Per-type gap hints ───────────────────────────────────────────────────────

_TYPE_HINTS = {
    "travel": """【旅行類】通常缺少：出發地、天數、各天目的地、預算。
→ 請使用**逐日骨架**（id: day_N，加 day 整數與 destination 欄位）
→ 天數未知時：先生成 3 個 unknown 佔位節點（day_1 出發、day_2 目的地待定、day_3 返回），等使用者確認天數後再調整
→ 出發地/目的地未知的節點：status=unknown，加 question""",

    "learning": """【學習類】通常缺少：使用者目前程度、可用時間、具體學習目標。
→ 請使用**任務骨架**
→ 必須加入 unknown 節點詢問：
   1. 目前程度（完全初學 / 有程式基礎 / 已學過部分）
   2. 每週可投入時間
→ 已知程度的步驟設為 done""",

    "project": """【專案/產品類】通常缺少：目標用戶、時間表、預算、核心功能定義。
→ 請使用**任務骨架**
→ 必須加入 unknown 節點詢問目標用戶與時間表""",

    "research": """【研究/調查類】通常缺少：研究範圍、目的（學術/商業/個人）、時間。
→ 請使用**任務骨架**
→ 必須加入 unknown 節點詢問研究範圍與目的""",

    "general": """【一般目標】根據目標性質判斷缺少的關鍵資訊。
→ 請使用**任務骨架**
→ 若有不確定的前提條件，加入 unknown 節點詢問""",

    "prompt": """【Prompt 設計類】目標是寫出一個給 AI 使用的 prompt。
節點 = prompt 的組成區塊，每個節點填完後可組裝成完整 prompt。
通常缺少以下資訊，必須逐一詢問：
   1. AI 的角色／身份（你是一個...）
   2. 任務說明（要做什麼、不做什麼）
   3. 目標受眾或使用情境
   4. 輸出格式（純文字／JSON／列點／長短）
   5. 限制條件（禁止事項、品牌規定、語氣要求）
   6. 是否需要 few-shot 範例
→ 請使用**任務骨架**，節點順序對應 prompt 段落順序
→ 每個未確認的區塊設為 unknown 節點，填完後 description 就是該段落的內容
→ 骨架固定包含：角色設定、任務說明、輸出格式、限制條件（至少這四個）""",
}

# ── Unified skeleton prompt ──────────────────────────────────────────────────

SKELETON_PROMPT = """使用者目標：{goal}
使用者上下文：{context}
目標類型提示：{type_hint}

使用者已知道的事項：
{user_states}

輸出 JSON：
{{
  "goal_type": "travel|learning|project|research|general",
  "nodes": [
    {{
      "id": "...",
      "name": "節點名稱",
      "description": "這個節點要做什麼",
      "status": "todo|done|skip|unknown",
      "reason": "為什麼需要或跳過",
      "question": "（status=unknown 時必填）要問使用者的一句話，繁體中文，問號結尾"
    }}
  ],
  "edges": [{{"from_id": "id1", "to_id": "id2"}}],
  "missing": "還缺什麼資訊（沒有就空字串）"
}}

逐日骨架每個節點必須額外加：
  "day": 1,
  "destination": "地名或待定"

unknown 節點規則：
- status=unknown 的節點必須有 question 欄位
- 凡是上面「類型提示」列出的缺口，都必須生成 unknown 節點
- 頂層節點 3-7 個（unknown 節點計入）"""

# ── Unified decomposition prompt ────────────────────────────────────────────

DECOMPOSE_PROMPT = """目標：{goal}
要拆解的步驟：「{node_name}」
說明：{node_description}
上下文：{context}

{type_hint}

輸出 JSON：
{{
  "nodes": [
    {{"id": "{parent_id}__英文名稱", "name": "子步驟名稱", "description": "具體要做什麼"}},
    ...
  ],
  "edges": [
    {{"from_id": "{parent_id}__a", "to_id": "{parent_id}__b"}}
  ]
}}

規則：
- id 必須以「{parent_id}__」開頭，用英文小寫加底線
- 生成 2-5 個子步驟"""


_SAFE_ID_RE = re.compile(r'[^a-zA-Z0-9_\-]')
_VALID_STATUSES = {"todo", "done", "skip", "unknown"}


def _sanitize_id(node_id: str) -> str:
    """Restrict node ID to [a-zA-Z0-9_-] to prevent HTML/JS injection."""
    safe = _SAFE_ID_RE.sub('_', str(node_id).strip())
    return safe or "node_unnamed"


def _sanitize_status(status: str) -> str:
    """Allow only known status values to prevent class attribute injection."""
    return status if status in _VALID_STATUSES else "todo"


def _sanitize_nodes(nodes: list[dict]) -> list[dict]:
    """Sanitize the LLM-generated node list: normalize IDs and whitelist status values."""
    for node in nodes:
        node["id"] = _sanitize_id(node.get("id", ""))
        node["status"] = _sanitize_status(node.get("status", "todo"))
    return nodes


def _sanitize_edges(edges: list[dict]) -> list[dict]:
    """Sanitize the LLM-generated edge list: normalize from/to IDs."""
    for edge in edges:
        edge["from_id"] = _sanitize_id(edge.get("from_id", ""))
        edge["to_id"] = _sanitize_id(edge.get("to_id", ""))
    return edges


def _parse_json(response: str) -> dict:
    text = response.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1])
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if m:
        text = m.group(0)
    return json.loads(text)


_CLASSIFY_PROMPT = """根據以下目標，選出最符合的類型代碼，只輸出代碼，不要其他文字：

prompt   → 寫 prompt、設計提示詞、給 AI 用的指令、system prompt、讓 AI 扮演、AI 助手設定
travel   → 旅行、出遊、出國、去某地玩、度假、背包客
learning → 學習、學某技能、讀書、考試、課程、入門、進階、教自己
project  → 開發、製作、建立、設計、創業、做產品、App、網站、系統
research → 研究、調查、分析、報告、市場研究、文獻
general  → 其他所有目標（健康、生活習慣、個人成長、減肥、理財等）

目標：{goal}
類型代碼："""

_KNOWN_TYPES = set(_TYPE_HINTS.keys())

# Keyword pre-classification: prevents local small models from mis-classifying goals with English keywords
_KEYWORD_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r'prompt|提示詞|system\s*prompt|給.{0,4}AI.{0,4}用|讓.{0,2}AI|AI\s*助手|AI\s*指令|扮演.{0,4}AI|AI.{0,4}扮演', re.IGNORECASE), "prompt"),
]


def classify_goal(goal: str) -> str:
    """Quickly classify the goal type (expects a single-token output from the LLM)."""
    # Apply keyword rules first to avoid local LLM mis-classification on special vocabulary
    for pattern, goal_type in _KEYWORD_RULES:
        if pattern.search(goal):
            return goal_type

    resp = chat(
        system="只輸出一個英文單詞，不要標點或說明。",
        messages=[{"role": "user", "content": _CLASSIFY_PROMPT.format(goal=goal)}],
    )
    t = resp.strip().lower().split()[0].rstrip(".,;:")
    return t if t in _KNOWN_TYPES else "general"


def generate_skeleton(goal: str, context: str, user_states: dict,
                      goal_type: str = "") -> dict:
    """Generate a path skeleton, including unknown nodes to mark information gaps."""
    if not goal_type:
        goal_type = classify_goal(goal)

    STATE_LABEL = {"knows": "已掌握", "doesnt_know": "不會", "uncertain": "不確定"}
    states_lines = "\n".join(
        f"  {nid}: {STATE_LABEL.get(s, s)}"
        for nid, s in user_states.items()
    ) or "  （無）"

    type_hint = _TYPE_HINTS.get(goal_type, _TYPE_HINTS["general"])
    prompt = SKELETON_PROMPT.format(
        goal=goal, context=context,
        type_hint=type_hint, user_states=states_lines,
    )
    response = chat(system=SYSTEM, messages=[{"role": "user", "content": prompt}])
    result = _parse_json(response)
    result["goal_type"] = result.get("goal_type", goal_type)

    _sanitize_nodes(result.get("nodes", []))
    _sanitize_edges(result.get("edges", []))

    for node in result.get("nodes", []):
        nid = node["id"]
        if nid in user_states and user_states[nid] == "knows":
            node["status"] = "done"

    return result


def generate_skeleton_stream(goal: str, context: str, user_states: dict,
                             goal_type: str = ""):
    """
    Streaming skeleton generation.
    yield ("goal_type", str)      — classification complete
    yield ("progress", int)       — emitted every 20 tokens; value is cumulative token count
    yield ("result", dict)        — parsing complete; value is the skeleton dict
    yield ("error", str)          — an error occurred
    """
    if not goal_type:
        goal_type = classify_goal(goal)
    yield ("goal_type", goal_type)

    STATE_LABEL = {"knows": "已掌握", "doesnt_know": "不會", "uncertain": "不確定"}
    states_lines = "\n".join(
        f"  {nid}: {STATE_LABEL.get(s, s)}"
        for nid, s in user_states.items()
    ) or "  （無）"

    type_hint = _TYPE_HINTS.get(goal_type, _TYPE_HINTS["general"])
    prompt = SKELETON_PROMPT.format(
        goal=goal, context=context,
        type_hint=type_hint, user_states=states_lines,
    )

    full_text = ""
    token_count = 0
    for token in chat_stream(system=SYSTEM, messages=[{"role": "user", "content": prompt}]):
        full_text += token
        token_count += 1
        if token_count % 20 == 0:
            yield ("progress", token_count)
    yield ("progress", token_count)   # final count

    try:
        result = _parse_json(full_text)
    except Exception as e:
        yield ("error", f"JSON 解析失敗：{e}")
        return

    result["goal_type"] = result.get("goal_type", goal_type)
    _sanitize_nodes(result.get("nodes", []))
    _sanitize_edges(result.get("edges", []))

    for node in result.get("nodes", []):
        node.setdefault("level", 1)
        node.setdefault("parent_id", None)
        node.setdefault("children", [])
        node.setdefault("name", node.get("id", "unnamed"))   # guard against LLM omitting name
        nid = node["id"]
        if nid in user_states and user_states[nid] == "knows":
            node["status"] = "done"

    yield ("result", result)


def decompose_node(goal: str, node: dict, context: str = "") -> dict:
    """Decompose a node into sub-steps, using a different hint based on node type."""
    is_day = isinstance(node.get("day"), int)
    if is_day:
        type_hint = (
            f"這是旅行的第 {node['day']} 天（{node.get('destination', '')}）。"
            "請生成 3-5 個任務，包含當天的活動安排（景點、交通、用餐）"
            "以及事前需要完成的配套準備（訂票、訂住宿等）。"
        )
    else:
        type_hint = "請將這個步驟拆解成 2-5 個最小可執行的子步驟。"

    prompt = DECOMPOSE_PROMPT.format(
        goal=goal,
        node_name=node.get("name", node.get("id", "")),
        node_description=node.get("description", ""),
        parent_id=node["id"],
        context=context,
        type_hint=type_hint,
    )
    response = chat(system=SYSTEM, messages=[{"role": "user", "content": prompt}])
    try:
        result = _parse_json(response)
        _sanitize_nodes(result.get("nodes", []))
        _sanitize_edges(result.get("edges", []))
        return result
    except Exception:
        return {"nodes": [], "edges": []}


def _store_nodes(nodes: list[dict], edges: list[dict]):
    for n in nodes:
        try:
            node_name = n.get("name", n.get("id", ""))
            emb = embed(n.get("description", node_name)[:500])
            upsert_node(n["id"], node_name, n.get("description", ""), emb)
        except Exception:
            pass
    for e in edges:
        try:
            add_edge(e["from_id"], e["to_id"])
        except Exception:
            pass


def plan_path(
    goal: str,
    context: str,
    user_id: str = None,
    domain: str = "general",
    user_states: dict = None,
    depth: int = 2,
    verbose: bool = True,
) -> dict:
    """
    Generate a goal path.
    The LLM decides the skeleton type (day-by-day or task-based); no hard-coded logic here.
    """
    user_states = user_states or {}

    if verbose:
        print(f"🎯 目標：{goal}")
        print(f"📋 上下文：{context}")
        print(f"🔄 生成骨架中...\n")

    skeleton = generate_skeleton(goal, context, user_states, goal_type=domain)
    all_nodes = skeleton.get("nodes", [])
    all_edges = skeleton.get("edges", [])

    for n in all_nodes:
        n["level"] = 1
        n["parent_id"] = None
        n["children"] = []

    if verbose:
        is_day = any(isinstance(n.get("day"), int) for n in all_nodes)
        mode_label = "逐日行程" if is_day else "任務步驟"
        print(f"📍 {mode_label}（{len(all_nodes)} 個）：")
        for n in all_nodes:
            icon = {"done": "✅", "skip": "⏭️"}.get(n.get("status", "todo"), "🔲")
            print(f"   {icon} {n.get('name', n.get('id', ''))}")

    if depth >= 2:
        if verbose:
            print(f"\n🔍 拆解子步驟中...\n")
        for node in list(all_nodes):
            if node.get("status") == "skip":
                continue
            sub = decompose_node(goal, node, context)
            children = sub.get("nodes", [])
            child_edges = sub.get("edges", [])
            for c in children:
                c["level"] = 2
                c["parent_id"] = node["id"]
                c["status"] = "todo"
                c["children"] = []
            node["children"] = [c["id"] for c in children]
            all_nodes.extend(children)
            all_edges.extend(child_edges)
            if verbose and children:
                print(f"   └─ {node.get('name', '')} → {', '.join(c.get('name', '') for c in children)}")

    _store_nodes(all_nodes, all_edges)

    result = {
        "nodes": all_nodes,
        "edges": all_edges,
        "missing": skeleton.get("missing", ""),
        "goal": goal,
        "context": context,
    }

    if verbose:
        print(f"\n{'='*40}")
        if skeleton.get("missing"):
            print(f"⚠️  缺口：{skeleton['missing']}")
        from ragraphe.core.visualizer import generate as gen_html
        html_path = gen_html(goal=goal, context=context, result=result)
        print(f"🌐 視覺化：{html_path}")

    return result


if __name__ == "__main__":
    from ragraphe.db.store import init_db
    init_db()
    plan_path(
        goal="我想去日本旅行",
        context="從台灣出發，五天四夜; 想去京都、奈良、箱根; 第一次出國，中等預算",
    )
