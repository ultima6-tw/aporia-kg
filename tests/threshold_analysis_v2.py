"""
閾值分析 v2：用 embedding 實際查詢 DB，找各 goal_type 最佳 travel_score 閾值

方法：
1. 對每個 (goal, node) 組合，先 embed(node_name)
2. 用 embedding 從 ChromaDB 檢索最相關的 20 chunk
3. 對這些 chunk 計算 travel_score
4. 分析：在不同閾值下，各 goal_type 各會接受/拒絕哪些 snippet
5. 人工標注 ground truth（旅遊 snippet 對非旅遊 goal 應被拒）

執行：
    LLM_BACKEND=gemini python3 tests/threshold_analysis_v2.py
"""
import re
import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("LLM_BACKEND", "gemini")

from ragraphe.core.crawler import raw_chunks, query_raw_chunks
from ragraphe.llm.gemini_client import embed

# ── 測試情境 ─────────────────────────────────────────────────────────────────
# (goal_text, node_name, goal_type_label)
TEST_CASES = [
    # 旅遊類（ground truth：旅遊 snippet OK）
    ("嵐山竹林一日遊",          "渡月橋",      "travel"),
    ("嵐山竹林一日遊",          "竹林小徑",    "travel"),
    ("嵐山竹林一日遊",          "天龍寺",      "travel"),
    ("東京自由行五天",          "淺草",        "travel"),
    ("東京自由行五天",          "秋葉原",      "travel"),
    ("京都三天兩夜旅遊",        "清水寺",      "travel"),
    ("京都三天兩夜旅遊",        "錦市場",      "travel"),
    ("沖縄潛水度假",            "沖縄浮潛",    "travel"),
    ("台南古蹟一日遊",          "赤崁樓",      "travel"),
    ("首爾美食旅遊",            "弘大街頭",    "travel"),

    # 學習類（ground truth：旅遊 snippet 應被拒）
    ("我想學日文五十音",        "五十音",      "learning"),
    ("我想學日文五十音",        "平假名",      "learning"),
    ("學習 Python 程式設計",    "函式",        "learning"),
    ("學習 Python 程式設計",    "迴圈",        "learning"),
    ("深度學習入門",            "神經網路",    "learning"),
    ("考多益 900 分",           "文法",        "learning"),
    ("機器學習實作",            "梯度下降",    "learning"),
    ("學鋼琴入門",              "拜爾練習曲",  "learning"),
    ("英文寫作技巧",            "段落結構",    "learning"),
    ("日文 JLPT N3 準備",       "漢字",        "learning"),

    # 創業/事業類（ground truth：旅遊 snippet 應被拒）
    ("我想開一間咖啡廳",        "菜單設計",    "business"),
    ("我想開一間咖啡廳",        "手沖咖啡",    "business"),
    ("我想開一間咖啡廳",        "店面租金",    "business"),
    ("開設網路商店",            "金流整合",    "business"),
    ("餐飲創業計畫",            "成本控制",    "business"),
    ("網路行銷策略",            "SEO 優化",    "business"),
    ("開發 SaaS 產品",          "定價策略",    "business"),
    ("餐飲創業計畫",            "菜單定價",    "business"),

    # 健康/健身類（ground truth：旅遊 snippet 應被拒）
    ("健身增肌計畫",            "蛋白質攝取",  "health"),
    ("健身增肌計畫",            "重訓課表",    "health"),
    ("減脂飲食規劃",            "熱量計算",    "health"),
    ("跑馬拉松訓練",            "配速策略",    "health"),
    ("瑜伽入門練習",            "呼吸法",      "health"),

    # 技術類（ground truth：旅遊 snippet 應被拒）
    ("建立個人網站",            "React 框架",  "tech"),
    ("架設家庭伺服器",          "NAS 設定",    "tech"),
    ("學 Rust 程式語言",        "所有權系統",  "tech"),
    ("開發手機 App",            "UI 設計",     "tech"),

    # 理財類（ground truth：旅遊 snippet 應被拒）
    ("學習股票投資",            "技術分析",    "finance"),
    ("ETF 長期投資",            "定期定額",    "finance"),
    ("個人理財規劃",            "緊急備用金",  "finance"),
]

_KNOWN_CITIES = [
    "京都", "大阪", "東京", "北海道", "沖縄", "福岡", "神戸", "横浜",
    "嵐山", "金閣寺", "清水寺", "祇園", "伏見稻荷", "天龍寺", "渡月橋",
    "台北", "台南", "高雄", "台中", "嘉義", "花蓮", "台東",
    "首爾", "釜山",
]

_TRAVEL_KW = re.compile(r"(旅遊|景點|交通|住宿|餐廳|美食|景色|寺廟|神社|旅行|觀光|"
                         r"參觀|門票|入場|行程|旅館|溫泉|海灘|博物館|古蹟|tour|sightseeing)", re.IGNORECASE)
_LEARN_KW  = re.compile(r"(學習|教學|課程|概念|原理|定義|算法|演算|入門|教程|tutorial|guide|learn)", re.IGNORECASE)

# ── 主迴圈 ───────────────────────────────────────────────────────────────────
print(f"DB chunk 數：{raw_chunks.count()}")
print(f"測試組合數：{len(TEST_CASES)}")
print("=" * 70)

from collections import defaultdict
THRESHOLDS = [2, 3, 4, 5]

# 統計資料結構
# { goal_type: { threshold: { "correct_reject": int, "false_positive": int, "false_negative": int } } }
type_stats = defaultdict(lambda: {t: {"correct_reject":0,"false_pos":0,"false_neg":0,"total":0} for t in THRESHOLDS})
# 儲存所有 (goal_type, travel_score, snippet) 的樣本（用於分布分析）
all_samples = []

for i, (goal_text, node_name, goal_type) in enumerate(TEST_CASES):
    goal_is_travel = (
        any(c in goal_text for c in _KNOWN_CITIES)
        or len(_TRAVEL_KW.findall(goal_text)) >= 2
    )

    # Embed node name
    try:
        node_emb = embed(node_name)
        time.sleep(0.15)  # rate limit
    except Exception as e:
        print(f"  [{i+1}/{len(TEST_CASES)}] SKIP embed error: {e}")
        continue

    # Query top 20 chunks
    if raw_chunks.count() == 0:
        print("DB empty, cannot test!")
        break

    results = raw_chunks.query(
        query_embeddings=[node_emb],
        n_results=min(20, raw_chunks.count()),
    )

    chunks = []
    for j, chunk_id in enumerate(results["ids"][0]):
        doc  = results["documents"][0][j]
        meta = results["metadatas"][0][j]
        dist = results["distances"][0][j]
        t_score = len(_TRAVEL_KW.findall(doc))
        l_score = len(_LEARN_KW.findall(doc))
        chunks.append({
            "doc": doc,
            "t_score": t_score,
            "l_score": l_score,
            "distance": dist,
            "category": meta.get("category","?"),
        })
        all_samples.append({
            "goal_type": goal_type,
            "goal_is_travel": goal_is_travel,
            "node": node_name,
            "t_score": t_score,
            "l_score": l_score,
            "distance": dist,
        })

    # 分析各閾值對此組合的效果
    for c in chunks:
        t = c["t_score"]
        snippet_is_travel = (t >= 3)

        for thr in THRESHOLDS:
            rejected = (not goal_is_travel) and (t >= thr)
            st = type_stats[goal_type][thr]
            st["total"] += 1
            if rejected:
                if snippet_is_travel:
                    st["correct_reject"] += 1   # 正確拒絕（非旅遊 goal + 旅遊 snippet）
                else:
                    st["false_neg"] += 1        # 誤殺（非旅遊 goal + 非旅遊 snippet，t_score剛好>=thr）
            else:
                if not goal_is_travel and snippet_is_travel:
                    st["false_pos"] += 1        # 漏網（非旅遊 goal + 旅遊 snippet 沒被拒）

    # 打印 progress
    top_t_scores = sorted([c["t_score"] for c in chunks], reverse=True)[:5]
    print(f"  [{i+1:2d}/{len(TEST_CASES)}] {goal_type:8s} | {node_name:12s} | goal={goal_text[:16]:16s} | "
          f"top t-scores: {top_t_scores}")

print("\n" + "=" * 70)
print("=== 各 goal_type × 閾值 的精確度分析 ===")
print(f"{'type':10s}  {'thr':3s}  {'total':6s}  {'tp_rej':6s}  {'fn':6s}  {'fp':6s}  "
      f"{'tp_rate%':8s}  {'fn_rate%':8s}  {'fp_rate%':8s}")
print("-" * 80)

for gt in ["travel", "learning", "business", "health", "tech", "finance"]:
    if gt not in type_stats:
        continue
    for thr in THRESHOLDS:
        s = type_stats[gt][thr]
        total = s["total"]
        if total == 0:
            continue
        tp  = s["correct_reject"]
        fn  = s["false_neg"]
        fp  = s["false_pos"]
        tp_r = tp / total * 100
        fn_r = fn / total * 100
        fp_r = fp / total * 100
        print(f"{gt:10s}  {thr:3d}  {total:6d}  {tp:6d}  {fn:6d}  {fp:6d}  "
              f"{tp_r:8.1f}%  {fn_r:8.1f}%  {fp_r:8.1f}%")
    print()

# ── 分布：各 goal_type 的 travel_score 分布（實際 embedding 查詢到的 chunk）
print("\n=== travel_score 分布（embedding 查詢到的真實 chunk）===")
from collections import Counter
for gt in ["travel", "learning", "business", "health", "tech", "finance"]:
    samples = [s for s in all_samples if s["goal_type"] == gt]
    if not samples:
        continue
    scores = [s["t_score"] for s in samples]
    cnt = Counter(scores)
    total = len(scores)
    n_travel = sum(1 for s in scores if s >= 3)
    print(f"\n{gt} ({total} chunk 查詢)：t>=3 的比例 = {n_travel/total*100:.1f}%")
    for score in sorted(cnt.keys()):
        pct = cnt[score] / total * 100
        bar = "█" * int(pct / 3)
        print(f"  t={score:2d}: {cnt[score]:4d} ({pct:5.1f}%) {bar}")

# ── 最佳閾值推薦 ──────────────────────────────────────────────────────────────
print("\n=== 最佳閾值推薦（最小化 fp+fn，排除旅遊 goal）===")
non_travel_types = ["learning", "business", "health", "tech", "finance"]
for thr in THRESHOLDS:
    total_fp = sum(type_stats[gt][thr]["false_pos"] for gt in non_travel_types if gt in type_stats)
    total_fn = sum(type_stats[gt][thr]["false_neg"] for gt in non_travel_types if gt in type_stats)
    total_tp = sum(type_stats[gt][thr]["correct_reject"] for gt in non_travel_types if gt in type_stats)
    total    = sum(type_stats[gt][thr]["total"] for gt in non_travel_types if gt in type_stats)
    print(f"  thr={thr}: fp={total_fp} fn={total_fn} correct_reject={total_tp} "
          f"(錯誤率={(total_fp+total_fn)/max(total,1)*100:.2f}%)")

print("\n=== 完成 ===")
