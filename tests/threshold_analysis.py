"""
閾值分析腳本：分析不同 goal_type 對 travel_score 閾值的敏感度

方法：
1. 從 ChromaDB 抓所有 chunk
2. 模擬 1000+ 種 (goal, node) 組合
3. 對每個 chunk 計算 travel_score、learn_score、quality
4. 分析各 goal_type 在不同閾值下的 Precision/Recall

執行：
    cd /Users/yclin/Documents/Claude/Projects/Ragraphe
    LLM_BACKEND=gemini python3 tests/threshold_analysis.py
"""

import re
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("LLM_BACKEND", "gemini")

from ragraphe.core.crawler import raw_chunks

# ── 複製 main.py 的過濾邏輯 ──────────────────────────────────────────────────
_TRAVEL_KW  = re.compile(r"(旅遊|景點|交通|住宿|餐廳|美食|景色|寺廟|神社|旅行|觀光|"
                          r"參觀|門票|入場|行程|旅館|溫泉|海灘|博物館|古蹟|tour|sightseeing)", re.IGNORECASE)
_LEARN_KW   = re.compile(r"(學習|教學|課程|概念|原理|定義|算法|演算|入門|教程|tutorial|guide|learn)", re.IGNORECASE)

_KNOWN_CITIES = [
    "京都", "大阪", "東京", "北海道", "沖縄", "福岡", "神戸", "横浜",
    "嵐山", "金閣寺", "清水寺", "祇園", "伏見稻荷",
    "台北", "台南", "高雄", "台中", "嘉義", "花蓮", "台東",
    "首爾", "釜山",
]

# ── 測試情境：(goal_text, node_name, expected_type) ──────────────────────────
# expected_type: "travel" | "non-travel"
TEST_GOALS = [
    # 旅遊類
    ("我想規劃京都三天兩夜旅遊", "清水寺", "travel"),
    ("嵐山竹林一日遊", "渡月橋", "travel"),
    ("東京自由行五天", "淺草", "travel"),
    ("沖縄潛水度假", "沖縄浮潛", "travel"),
    ("台南古蹟一日遊", "赤崁樓", "travel"),
    ("首爾美食旅遊", "弘大街頭", "travel"),
    ("大阪環球影城", "USJ", "travel"),
    ("北海道冬季旅遊", "雪祭", "travel"),
    ("九份老街一日遊", "九份", "travel"),
    ("花蓮太魯閣健行", "太魯閣", "travel"),

    # 學習類
    ("我想學日文五十音", "五十音", "non-travel"),
    ("學習 Python 程式設計", "函式", "non-travel"),
    ("深度學習入門", "神經網路", "non-travel"),
    ("學習吉他和弦", "C 和弦", "non-travel"),
    ("考多益 900 分", "文法", "non-travel"),
    ("學鋼琴入門", "拜爾練習曲", "non-travel"),
    ("學習水彩畫", "色彩混合", "non-travel"),
    ("英文寫作技巧", "段落結構", "non-travel"),
    ("日文 JLPT N3 準備", "漢字", "non-travel"),
    ("機器學習實作", "梯度下降", "non-travel"),

    # 創業/事業類
    ("我想開一間咖啡廳", "菜單設計", "non-travel"),
    ("開設網路商店", "金流整合", "non-travel"),
    ("創業第一步", "市場調查", "non-travel"),
    ("開美甲工作室", "設備採購", "non-travel"),
    ("餐飲創業計畫", "成本控制", "non-travel"),
    ("開設健身教練工作室", "客戶開發", "non-travel"),
    ("網路行銷策略", "SEO 優化", "non-travel"),
    ("開發 SaaS 產品", "定價策略", "non-travel"),

    # 健康/健身類
    ("健身增肌計畫", "蛋白質攝取", "non-travel"),
    ("減脂飲食規劃", "熱量計算", "non-travel"),
    ("跑馬拉松訓練", "配速策略", "non-travel"),
    ("瑜伽入門練習", "呼吸法", "non-travel"),
    ("居家健身計畫", "深蹲", "non-travel"),
    ("備孕飲食調整", "葉酸", "non-travel"),

    # 理財/投資類
    ("學習股票投資", "技術分析", "non-travel"),
    ("ETF 長期投資", "定期定額", "non-travel"),
    ("個人理財規劃", "緊急備用金", "non-travel"),
    ("加密貨幣入門", "區塊鏈", "non-travel"),

    # 技術專案類
    ("建立個人網站", "React 框架", "non-travel"),
    ("開發手機 App", "UI 設計", "non-travel"),
    ("架設家庭伺服器", "NAS 設定", "non-travel"),
    ("學 Rust 程式語言", "所有權系統", "non-travel"),
]

# ── 從 DB 載入所有 chunks ─────────────────────────────────────────────────────
print("載入 ChromaDB chunks...", flush=True)
result = raw_chunks.get(include=["documents", "metadatas"])
all_docs  = result["documents"]
all_metas = result["metadatas"]
print(f"共 {len(all_docs)} 筆 chunk")

# ── 分析每個 (goal, chunk) 組合 ───────────────────────────────────────────────
print("\n=== 逐條分析 ===")

from collections import defaultdict

# 收集各 goal_type 的 travel_score 分布
travel_scores_by_type: dict[str, list[int]] = defaultdict(list)

# 針對不同閾值，記錄各 type 的 accept/reject 數
thresholds = [2, 3, 4, 5]
stats = {
    thr: {
        "travel_accept": 0, "travel_reject": 0,
        "non_travel_accept": 0, "non_travel_reject": 0,
        "false_positive": 0,    # 非旅遊 goal 卻接受旅遊 snippet
        "false_negative": 0,    # 旅遊 goal 卻拒絕旅遊 snippet (不應該)
    }
    for thr in thresholds
}

detail_rows = []  # 詳細記錄高 travel_score 的案例

for goal_text, node_name, goal_type in TEST_GOALS:
    goal_is_travel = (
        any(c in goal_text for c in _KNOWN_CITIES)
        or len(_TRAVEL_KW.findall(goal_text)) >= 2
    )

    for doc, meta in zip(all_docs, all_metas):
        t_score = len(_TRAVEL_KW.findall(doc))
        l_score = len(_LEARN_KW.findall(doc))
        travel_scores_by_type[goal_type].append(t_score)

        # 判斷這個 snippet 是否算「旅遊 snippet」(ground truth)
        snippet_is_travel = (t_score >= 3)

        for thr in thresholds:
            if not goal_is_travel and t_score >= thr:
                # 被拒絕
                stats[thr]["non_travel_reject"] += 1
                if snippet_is_travel:
                    pass  # 正確拒絕旅遊 snippet for non-travel goal
                # False negative（誤殺）：拒絕了可能相關的 snippet
                # 難以判斷，因為我們不知道 snippet 是否真的相關
            else:
                stats[thr]["non_travel_accept"] += 1

            if goal_is_travel:
                stats[thr]["travel_accept"] += 1  # 旅遊 goal 不做此過濾

        # 記錄高 travel_score 的案例細節
        if t_score >= 2:
            detail_rows.append({
                "goal": goal_text[:20],
                "goal_type": goal_type,
                "node": node_name,
                "t_score": t_score,
                "l_score": l_score,
                "snippet_preview": doc[:80].replace("\n", " "),
                "category": meta.get("category", "?"),
            })

# ── 輸出 travel_score 分布 ─────────────────────────────────────────────────────
print("\n=== travel_score 分布（每種 goal_type 各 N 筆 chunk 統計）===")
for gt in ["travel", "non-travel"]:
    scores = travel_scores_by_type[gt]
    if not scores:
        continue
    total = len(scores)
    from collections import Counter
    cnt = Counter(scores)
    print(f"\n{gt} ({total} 樣本):")
    for s in sorted(cnt.keys()):
        pct = cnt[s] / total * 100
        bar = "█" * int(pct / 2)
        print(f"  score={s:2d}: {cnt[s]:5d} ({pct:5.1f}%) {bar}")

# ── 輸出各閾值的過濾效果 ──────────────────────────────────────────────────────
print("\n=== 各閾值效果（非旅遊 goal 只看 non-travel）===")
print(f"{'閾值':>4}  {'非旅遊_接受':>10}  {'非旅遊_拒絕':>10}  {'拒絕率':>7}")
for thr in thresholds:
    s = stats[thr]
    total_nt = s["non_travel_accept"] + s["non_travel_reject"]
    if total_nt == 0:
        continue
    reject_rate = s["non_travel_reject"] / total_nt * 100
    print(f"  {thr:2d}     {s['non_travel_accept']:>10,}    {s['non_travel_reject']:>10,}    {reject_rate:6.1f}%")

# ── 高 travel_score 範例 ──────────────────────────────────────────────────────
print("\n=== 高 travel_score (>=3) 的 snippet 範例（前30筆）===")
high_travel = [r for r in detail_rows if r["t_score"] >= 3]
print(f"共 {len(high_travel)} 筆（去重前）")
seen = set()
shown = 0
for r in high_travel:
    key = r["snippet_preview"][:40]
    if key in seen:
        continue
    seen.add(key)
    print(f"  [{r['goal_type']:10s}] goal={r['goal']:18s} t={r['t_score']} l={r['l_score']} cat={r['category']}")
    print(f"    snippet: {r['snippet_preview']}")
    shown += 1
    if shown >= 30:
        break

# ── 非旅遊 goal 中，travel_score=2 的 snippet（閾值邊緣案例）──────────────────
print("\n=== 邊緣案例：非旅遊 goal + travel_score=2（閾值=3 時被接受，閾值=2 時被拒）===")
edge_cases = [r for r in detail_rows if r["t_score"] == 2 and r["goal_type"] == "non-travel"]
print(f"共 {len(edge_cases)} 筆")
seen2 = set()
shown2 = 0
for r in edge_cases:
    key = r["snippet_preview"][:40]
    if key in seen2:
        continue
    seen2.add(key)
    print(f"  goal={r['goal']:20s} t=2 l={r['l_score']} cat={r['category']}")
    print(f"    snippet: {r['snippet_preview']}")
    shown2 += 1
    if shown2 >= 20:
        break

# ── 按 goal 細分的分析 ────────────────────────────────────────────────────────
print("\n=== 各 goal 的平均 travel_score（非旅遊 goal 前20）===")
goal_stats = defaultdict(lambda: {"scores": [], "high": 0})
for goal_text, node_name, goal_type in TEST_GOALS:
    if goal_type != "non-travel":
        continue
    for doc in all_docs:
        t_score = len(_TRAVEL_KW.findall(doc))
        goal_stats[goal_text]["scores"].append(t_score)
        if t_score >= 3:
            goal_stats[goal_text]["high"] += 1

print(f"{'goal':22s}  {'avg_t':>6}  {'high(>=3)%':>10}  {'total':>5}")
for goal_text, s in list(goal_stats.items())[:20]:
    scores = s["scores"]
    if not scores:
        continue
    avg = sum(scores) / len(scores)
    high_pct = s["high"] / len(scores) * 100
    print(f"  {goal_text[:20]:20s}  {avg:6.2f}  {high_pct:10.1f}%  {len(scores):5d}")

print("\n=== 完成 ===")
