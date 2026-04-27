"""
兩階段全面測試
Phase 1：爬取多元領域內容（Wikipedia + DuckDuckGo）入庫
Phase 2：大量測試各類 goal × node，分析最佳閾值

執行：
    LLM_BACKEND=gemini python3 tests/populate_and_analyze.py 2>/dev/null
"""
import re, sys, os, time, json
from collections import defaultdict, Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("LLM_BACKEND", "gemini")

from ragraphe.core.crawler import (
    raw_chunks, fetch_wikipedia, chunk_text, store_chunks,
    search_urls, crawl_urls, fetch_text,
)
from ragraphe.db.store import is_url_cached
from ragraphe.llm.gemini_client import embed

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 1：補充多元領域的 Wikipedia 內容
# ═══════════════════════════════════════════════════════════════════════════

WIKI_TOPICS = {
    # 物理
    "physics": [
        ("量子力學", "zh"), ("相對論", "zh"), ("熱力學", "zh"),
        ("電磁學", "zh"), ("量子糾纏", "zh"), ("薛丁格方程式", "zh"),
        ("波粒二象性", "zh"), ("狹義相對論", "zh"), ("廣義相對論", "zh"),
        ("量子電動力學", "zh"), ("固態物理學", "zh"), ("超導體", "zh"),
        ("quantum mechanics", "en"), ("thermodynamics", "en"),
        ("electromagnetic wave", "en"), ("particle physics", "en"),
    ],
    # 化學
    "chemistry": [
        ("有機化學", "zh"), ("無機化學", "zh"), ("化學鍵", "zh"),
        ("元素週期表", "zh"), ("酸鹼反應", "zh"), ("氧化還原反應", "zh"),
        ("苯", "zh"), ("高分子化學", "zh"), ("電化學", "zh"),
        ("反應速率", "zh"), ("熱化學", "zh"), ("分析化學", "zh"),
        ("organic chemistry", "en"), ("chemical bond", "en"),
    ],
    # 生物
    "biology": [
        ("細胞生物學", "zh"), ("遺傳學", "zh"), ("分子生物學", "zh"),
        ("生態學", "zh"), ("演化論", "zh"), ("神經科學", "zh"),
        ("DNA", "zh"), ("蛋白質", "zh"), ("光合作用", "zh"),
        ("細胞分裂", "zh"), ("免疫系統", "zh"), ("基因工程", "zh"),
        ("neuroscience", "en"), ("molecular biology", "en"),
        ("CRISPR", "en"), ("protein folding", "en"),
    ],
    # 數學
    "math": [
        ("微積分", "zh"), ("線性代數", "zh"), ("機率論", "zh"),
        ("數論", "zh"), ("拓撲學", "zh"), ("微分方程", "zh"),
        ("傅立葉轉換", "zh"), ("群論", "zh"), ("統計學", "zh"),
        ("linear algebra", "en"), ("calculus", "en"),
        ("probability theory", "en"),
    ],
    # 程式設計
    "programming": [
        ("Python程式語言", "zh"), ("資料結構", "zh"), ("演算法", "zh"),
        ("動態規劃", "zh"), ("圖論", "zh"), ("排序演算法", "zh"),
        ("二元搜尋樹", "zh"), ("雜湊表", "zh"), ("遞迴", "zh"),
        ("作業系統", "zh"), ("計算機網路", "zh"), ("資料庫", "zh"),
        ("machine learning", "en"), ("neural network", "en"),
        ("algorithm", "en"), ("data structure", "en"),
        ("compiler", "en"), ("operating system", "en"),
    ],
    # 工程 / 電子
    "engineering": [
        ("電路學", "zh"), ("訊號處理", "zh"), ("控制系統", "zh"),
        ("半導體", "zh"), ("積體電路", "zh"), ("嵌入式系統", "zh"),
        ("材料科學", "zh"), ("流體力學", "zh"),
        ("semiconductor", "en"), ("signal processing", "en"),
    ],
    # 人文社科（作為對比，非科學）
    "social": [
        ("經濟學", "zh"), ("社會學", "zh"), ("心理學", "zh"),
        ("哲學", "zh"), ("歷史學", "zh"), ("語言學", "zh"),
        ("economics", "en"), ("psychology", "en"),
    ],
}

def phase1_populate():
    print("=" * 70)
    print("PHASE 1：補充多元領域 Wikipedia 內容")
    print("=" * 70)
    before = raw_chunks.count()
    print(f"目前 DB: {before} chunks\n")

    total_added = 0
    for domain, topics in WIKI_TOPICS.items():
        domain_added = 0
        for query, lang in topics:
            chunks = fetch_wikipedia(query, lang=lang)
            if chunks:
                # 為每個 chunk 標記 category
                for c in chunks:
                    c["category"] = domain
                store_chunks(chunks, category=domain, ttl_days=0)
                domain_added += len(chunks)
                total_added += len(chunks)
                print(f"  [{domain:12s}] {query:25s} → {len(chunks):3d} chunks")
            else:
                print(f"  [{domain:12s}] {query:25s} → (無結果)")
            time.sleep(0.3)  # 避免 rate limit
        print(f"  {domain}: 共新增 {domain_added} chunks\n")

    after = raw_chunks.count()
    print(f"Phase 1 完成：{before} → {after} chunks（新增 {total_added}）\n")

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 2：大量測試
# ═══════════════════════════════════════════════════════════════════════════

# 旅遊關鍵字（中英）
_TRAVEL_KW = re.compile(
    r"(旅遊|景點|交通|住宿|餐廳|美食|景色|寺廟|神社|旅行|觀光|"
    r"參觀|門票|入場|行程|旅館|溫泉|海灘|博物館|古蹟|tour|sightseeing)",
    re.IGNORECASE,
)
_RE_CJK = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
_KNOWN_CITIES = [
    "京都","大阪","東京","北海道","沖縄","福岡","嵐山","清水寺","渡月橋",
    "台北","台南","高雄","台中","嘉義","花蓮",
    "首爾","釜山","Seoul","Busan","Tokyo","Kyoto","Osaka",
]

def _travel_threshold(goal_text: str) -> int:
    return 3 if _RE_CJK.search(goal_text) else 5

# ── 大量測試情境 ──────────────────────────────────────────────────────────
ALL_CASES = []
def add(goal, node, gtype, lang):
    ALL_CASES.append((goal, node, gtype, lang))

# ── 旅遊 ─────────────────────────────────────────────────────────────────
for goal, nodes in [
    ("嵐山竹林一日遊",       ["渡月橋","竹林小徑","天龍寺","嵯峨野小火車","野宮神社"]),
    ("京都三天兩夜旅遊",     ["清水寺","金閣寺","錦市場","祇園","哲學之道"]),
    ("東京五日自由行",       ["淺草雷門","秋葉原","新宿","台場","上野"]),
    ("大阪美食之旅",         ["道頓堀","心齋橋","黑門市場","環球影城"]),
    ("沖縄海島度假",         ["美麗海水族館","古宇利島","首里城","沖縄浮潛"]),
    ("北海道冬季旅遊",       ["札幌雪祭","函館夜景","小樽運河","旭山動物園"]),
    ("台南古蹟文化之旅",     ["赤崁樓","安平古堡","孔廟","神農街"]),
    ("花蓮太魯閣健行",       ["太魯閣峽谷","清水斷崖","七星潭","鯉魚潭"]),
    ("首爾購物美食五日",     ["明洞","弘大","東大門","景福宮","南大門"]),
    ("東南亞跨國旅遊計畫",   ["曼谷大皇宮","吳哥窟","峇里島","新加坡濱海灣"]),
]:
    for n in nodes: add(goal, n, "travel", "zh-TW")

for goal, nodes in [
    ("3-day Kyoto travel",   ["Kinkakuji","Arashiyama","Fushimi Inari","Gion"]),
    ("Tokyo 5-day trip",     ["Shibuya","Asakusa","Akihabara","Harajuku"]),
    ("Seoul food tour",      ["Myeongdong","Hongdae","Bukchon","Insadong"]),
]:
    for n in nodes: add(goal, n, "travel", "en")

for goal, nodes in [
    ("京都三日間観光",       ["清水寺","金閣寺","嵐山","祇園"]),
    ("東京自由旅行",         ["浅草","秋葉原","渋谷","上野"]),
]:
    for n in nodes: add(goal, n, "travel", "ja")

# ── 物理研究 ─────────────────────────────────────────────────────────────
for goal, nodes in [
    ("研究量子力學基礎",     ["波函數","量子疊加","海森堡測不準原理","薛丁格方程式","量子糾纏"]),
    ("學習狹義相對論",       ["時間膨脹","長度收縮","質能等價","勞倫茲變換","光速不變"]),
    ("固態物理研究",         ["能帶理論","費米能階","半導體","超導現象","晶格振動"]),
    ("量子場論入門",         ["費曼圖","虛粒子","重整化","規範對稱","希格斯玻色子"]),
    ("熱力學與統計力學",     ["熵","波茲曼常數","吉布斯自由能","相變","配分函數"]),
    ("電磁學研究",           ["馬克士威方程組","電場","磁場","電磁波","法拉第定律"]),
    ("核物理入門",           ["核反應","放射衰變","核裂變","核聚變","半衰期"]),
]:
    for n in nodes: add(goal, n, "physics", "zh-TW")

for goal, nodes in [
    ("Study quantum mechanics", ["wave function","uncertainty principle","entanglement","Schrodinger equation"]),
    ("Learn special relativity", ["time dilation","Lorentz transformation","mass-energy equivalence"]),
    ("Research thermodynamics",  ["entropy","Boltzmann constant","phase transition","heat engine"]),
    ("Particle physics research",["Higgs boson","Standard Model","quark","lepton","gluon"]),
]:
    for n in nodes: add(goal, n, "physics", "en")

# ── 化學研究 ─────────────────────────────────────────────────────────────
for goal, nodes in [
    ("有機化學反應機制",     ["碳正離子","自由基","親核取代","消去反應","加成反應"]),
    ("無機化學研究",         ["配位化合物","過渡金屬","氧化態","晶體場理論","配位鍵"]),
    ("電化學研究",           ["電極電位","能斯特方程式","電解","法拉第定律","電池"]),
    ("高分子化學",           ["聚合反應","共聚物","交聯","玻璃轉化溫度","分子量分布"]),
    ("分析化學技術",         ["色層分析","光譜法","質譜儀","核磁共振","滴定"]),
    ("量子化學",             ["分子軌域","電子組態","鍵能","振動光譜","密度泛函"]),
]:
    for n in nodes: add(goal, n, "chemistry", "zh-TW")

for goal, nodes in [
    ("Organic chemistry reactions", ["nucleophilic substitution","elimination reaction","carbocation"]),
    ("Electrochemistry research",   ["electrode potential","Nernst equation","electrolysis"]),
    ("Polymer chemistry",           ["polymerization","copolymer","glass transition temperature"]),
]:
    for n in nodes: add(goal, n, "chemistry", "en")

# ── 生物研究 ─────────────────────────────────────────────────────────────
for goal, nodes in [
    ("分子生物學研究",       ["DNA複製","轉錄","翻譯","基因調控","表觀遺傳"]),
    ("細胞生物學",           ["細胞膜","粒線體","內質網","核糖體","細胞週期"]),
    ("神經科學研究",         ["突觸","神經傳導物質","動作電位","神經可塑性","大腦皮質"]),
    ("免疫學研究",           ["T細胞","B細胞","抗體","先天免疫","自體免疫"]),
    ("遺傳學與基因組學",     ["孟德爾遺傳","連鎖不平衡","GWAS","SNP","表現型"]),
    ("生物化學",             ["酵素動力學","代謝途徑","ATP合成","糖解作用","克氏循環"]),
    ("生態學研究",           ["食物鏈","生態系","生物多樣性","族群動態","生態棲位"]),
    ("基因編輯技術",         ["CRISPR-Cas9","基因療法","脫靶效應","向導RNA","基因敲除"]),
]:
    for n in nodes: add(goal, n, "biology", "zh-TW")

for goal, nodes in [
    ("Molecular biology research", ["DNA replication","transcription","translation","gene regulation"]),
    ("Neuroscience research",      ["synapse","neurotransmitter","action potential","neuroplasticity"]),
    ("Immunology study",           ["T cells","antibody","innate immunity","autoimmune"]),
    ("CRISPR gene editing",        ["guide RNA","off-target effects","gene therapy","knockout"]),
]:
    for n in nodes: add(goal, n, "biology", "en")

# ── 程式設計 ─────────────────────────────────────────────────────────────
for goal, nodes in [
    ("學習資料結構與演算法", ["排序演算法","二元搜尋樹","圖的遍歷","動態規劃","貪心演算法"]),
    ("Python 進階程式設計", ["裝飾器","生成器","非同步IO","型別提示","metaclass"]),
    ("系統程式設計",         ["行程排程","記憶體管理","虛擬記憶體","鎖機制","I/O模型"]),
    ("資料庫系統設計",       ["正規化","索引","交易","ACID","查詢優化"]),
    ("網路程式設計",         ["TCP/IP","HTTP協議","Socket","REST API","WebSocket"]),
    ("編譯器設計",           ["詞法分析","語法分析","語意分析","中間碼","程式碼生成"]),
    ("機器學習實作",         ["梯度下降","反向傳播","過擬合","交叉驗證","特徵工程"]),
    ("深度學習架構",         ["卷積神經網路","循環神經網路","注意力機制","Transformer","強化學習"]),
    ("分散式系統",           ["一致性協議","Raft","CAP定理","分片","事件驅動"]),
    ("程式語言理論",         ["型別系統","Lambda演算","單子","函數式程式設計","所有權系統"]),
]:
    for n in nodes: add(goal, n, "programming", "zh-TW")

for goal, nodes in [
    ("Learn algorithms and data structures", ["binary search","dynamic programming","graph traversal","sorting"]),
    ("Advanced Python programming",          ["decorators","generators","async IO","type hints"]),
    ("Machine learning fundamentals",        ["gradient descent","backpropagation","overfitting","cross-validation"]),
    ("Deep learning architectures",          ["CNN","RNN","attention mechanism","Transformer"]),
    ("Distributed systems design",           ["consensus","CAP theorem","sharding","event-driven"]),
    ("Database system internals",            ["normalization","indexing","ACID","query optimization"]),
]:
    for n in nodes: add(goal, n, "programming", "en")

# 日文程式設計
for goal, nodes in [
    ("Pythonプログラミング入門",  ["変数","関数","クラス","モジュール","ライブラリ"]),
    ("アルゴリズムを学ぶ",        ["ソート","二分探索","動的計画法","グラフ理論"]),
]:
    for n in nodes: add(goal, n, "programming", "ja")

# ── 數學 ─────────────────────────────────────────────────────────────────
for goal, nodes in [
    ("學習微積分",           ["極限","導數","積分","泰勒展開","偏微分"]),
    ("線性代數研究",         ["向量空間","線性變換","特徵值","SVD分解","正交基底"]),
    ("機率論與統計",         ["期望值","變異數","中央極限定理","假設檢定","貝葉斯定理"]),
    ("數論研究",             ["質數","模運算","歐拉函數","黎曼猜想","費馬定理"]),
    ("微分方程",             ["常微分方程","偏微分方程","拉普拉斯算子","邊界值問題"]),
    ("拓撲學入門",           ["拓撲空間","連續映射","同倫","流形","同調群"]),
]:
    for n in nodes: add(goal, n, "math", "zh-TW")

for goal, nodes in [
    ("Study linear algebra",     ["vector space","eigenvalue","SVD","orthogonal basis"]),
    ("Probability and statistics",["expected value","central limit theorem","Bayesian inference"]),
    ("Number theory research",   ["prime numbers","modular arithmetic","Riemann hypothesis"]),
]:
    for n in nodes: add(goal, n, "math", "en")

# ── 工程 / 電子 ──────────────────────────────────────────────────────────
for goal, nodes in [
    ("電路設計與分析",       ["克希荷夫定律","阻抗匹配","濾波器","運算放大器","共振電路"]),
    ("數位訊號處理",         ["傅立葉轉換","取樣定理","FIR濾波器","Z轉換","頻譜分析"]),
    ("嵌入式系統開發",       ["微控制器","RTOS","GPIO","UART","SPI協議"]),
    ("半導體元件物理",       ["p-n接面","MOSFET","BJT","能帶結構","載子傳輸"]),
    ("控制理論",             ["PID控制器","狀態空間","穩定性分析","波德圖","奈奎斯特"]),
    ("電力系統",             ["發電機","變壓器","輸電線路","電力品質","電網穩定"]),
]:
    for n in nodes: add(goal, n, "engineering", "zh-TW")

for goal, nodes in [
    ("Digital signal processing",  ["Fourier transform","sampling theorem","FIR filter","Z-transform"]),
    ("Embedded systems development",["microcontroller","RTOS","GPIO","interrupt handling"]),
    ("Semiconductor device physics",["p-n junction","MOSFET","band structure","carrier transport"]),
]:
    for n in nodes: add(goal, n, "engineering", "en")

# ── 學術寫作 / 研究方法 ──────────────────────────────────────────────────
for goal, nodes in [
    ("撰寫學術論文",         ["文獻回顧","研究方法","統計分析","結果呈現","參考文獻格式"]),
    ("實驗設計與統計",       ["對照組","隨機分配","效果量","統計顯著性","信賴區間"]),
    ("研究所申請準備",       ["研究計畫書","推薦信","SOP撰寫","面試準備","選校策略"]),
]:
    for n in nodes: add(goal, n, "academic", "zh-TW")

for goal, nodes in [
    ("Write a research paper",     ["literature review","methodology","statistical analysis","citation"]),
    ("PhD application preparation",["statement of purpose","research proposal","recommendation letters"]),
]:
    for n in nodes: add(goal, n, "academic", "en")

# ── 醫學 / 健康科學 ──────────────────────────────────────────────────────
for goal, nodes in [
    ("藥理學基礎",           ["藥效動力學","藥物代謝","受體理論","半衰期","副作用機制"]),
    ("臨床醫學基礎",         ["診斷推理","鑑別診斷","實證醫學","臨床試驗","生物標記"]),
    ("醫學影像技術",         ["X光","電腦斷層","核磁共振","超音波","正子掃描"]),
]:
    for n in nodes: add(goal, n, "medical", "zh-TW")

for goal, nodes in [
    ("Pharmacology fundamentals",  ["pharmacodynamics","drug metabolism","receptor theory","half-life"]),
    ("Medical imaging",            ["X-ray","CT scan","MRI","ultrasound","PET scan"]),
]:
    for n in nodes: add(goal, n, "medical", "en")

# ── 非科學對比（食物、創業、旅遊相鄰）──────────────────────────────────────
for goal, nodes in [
    ("開咖啡廳創業計畫",     ["菜單設計","手沖咖啡","店面選址","成本控制","品牌定位"]),
    ("學日文五十音",         ["平假名","片假名","五十音表","發音規則"]),
    ("健身增肌計畫",         ["重訓課表","蛋白質攝取","深蹲","臥推","有氧搭配"]),
    ("學做日本料理",         ["壽司捲","拉麵湯底","天婦羅","味噌湯"]),
]:
    for n in nodes: add(goal, n, "other", "zh-TW")

print(f"總測試情境：{len(ALL_CASES)}")

# ═══════════════════════════════════════════════════════════════════════════
# PHASE 2：執行測試
# ═══════════════════════════════════════════════════════════════════════════

THRESHOLDS = [2, 3, 4, 5, 6]

def phase2_analyze():
    print("\n" + "=" * 70)
    print("PHASE 2：大量 embedding 查詢 + 閾值分析")
    print(f"DB chunk 數：{raw_chunks.count()}")
    print(f"測試情境數：{len(ALL_CASES)}")
    print("=" * 70 + "\n")

    # { (goal_type, lang): { thr: {cr, fn, fp, total, travel_count} } }
    Results = defaultdict(lambda: {
        t: {"cr":0,"fn":0,"fp":0,"total":0,"travel_count":0}
        for t in THRESHOLDS
    })
    samples = []
    errors  = 0

    for idx, (goal_text, node_name, goal_type, lang) in enumerate(ALL_CASES):
        goal_is_travel = (
            any(c in goal_text for c in _KNOWN_CITIES)
            or len(_TRAVEL_KW.findall(goal_text)) >= 2
        )
        try:
            node_emb = embed(node_name)
            time.sleep(0.12)
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  embed error: {e}")
            continue

        n_chunks = raw_chunks.count()
        if n_chunks == 0:
            print("DB empty!")
            break

        results = raw_chunks.query(
            query_embeddings=[node_emb],
            n_results=min(20, n_chunks),
        )
        for j, _ in enumerate(results["ids"][0]):
            doc  = results["documents"][0][j]
            dist = results["distances"][0][j]
            t_sc = len(_TRAVEL_KW.findall(doc))
            is_travel_snippet = (t_sc >= 3)

            key = (goal_type, lang)
            samples.append({
                "goal_type": goal_type, "lang": lang,
                "goal_is_travel": goal_is_travel,
                "t_score": t_sc, "distance": dist,
            })

            for thr in THRESHOLDS:
                rejected = (not goal_is_travel) and (t_sc >= thr)
                st = Results[key][thr]
                st["total"] += 1
                if is_travel_snippet:
                    st["travel_count"] += 1
                if rejected:
                    if is_travel_snippet:
                        st["cr"] += 1
                    else:
                        st["fn"] += 1
                else:
                    if not goal_is_travel and is_travel_snippet:
                        st["fp"] += 1

        if (idx + 1) % 50 == 0:
            print(f"  [{idx+1:4d}/{len(ALL_CASES)}] errors={errors}")

    print(f"\n完成！{len(samples)} 筆樣本，errors={errors}\n")
    return Results, samples

# ═══════════════════════════════════════════════════════════════════════════
# 報告輸出
# ═══════════════════════════════════════════════════════════════════════════

def report(Results, samples):
    all_types = ["travel","physics","chemistry","biology","programming","math",
                 "engineering","academic","medical","other"]
    all_langs = ["zh-TW","en","ja"]
    REPORT_THRS = [2, 3, 4, 5]

    print("=" * 100)
    print("=== 各 (goal_type, lang) 的旅遊 snippet 混入率 + 各閾值效果 ===")
    print("=" * 100)
    print(f"{'type':12s} {'lang':6s} {'chunks':6s} {'t%>=3':6s} | "
          + "  ".join(f"thr={t}: cr/fn/fp" for t in REPORT_THRS))
    print("-" * 100)

    best_thr = {}
    for gt in all_types:
        for lang in all_langs:
            key = (gt, lang)
            if key not in Results:
                continue
            s3 = Results[key][3]
            total = s3["total"]
            if total == 0:
                continue
            tpct = s3["travel_count"] / total * 100

            parts = []
            err_rates = {}
            for t in REPORT_THRS:
                s = Results[key][t]
                parts.append(f"{s['cr']:3d}/{s['fn']:2d}/{s['fp']:2d}")
                err_rates[t] = (s["fn"] + s["fp"]) / max(total,1) * 100
            best = min(REPORT_THRS, key=lambda x: (err_rates[x], -x)) if gt != "travel" else None
            best_thr[key] = best

            flag = f"★{best}" if best else " n/a"
            print(f"{gt:12s} {lang:6s} {total:6d} {tpct:5.1f}% | "
                  + "  ".join(parts) + f"  [{flag}]")
        if gt != "other":
            print()

    # ── 推薦閾值矩陣 ──────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("=== 推薦閾值矩陣（非旅遊類型）===")
    print("=" * 70)
    print(f"{'type':14s}", end="")
    for lang in all_langs:
        print(f"  {lang:8s}", end="")
    print()
    print("-" * 44)
    for gt in all_types:
        if gt == "travel":
            continue
        print(f"{gt:14s}", end="")
        for lang in all_langs:
            key = (gt, lang)
            v = best_thr.get(key)
            print(f"  {str(v) if v else 'N/A':8s}", end="")
        print()

    # ── travel_score 分布（按類型）────────────────────────────────────────
    print("\n" + "=" * 70)
    print("=== travel_score 分布（per goal_type，embedding 真實查詢）===")
    print("=" * 70)
    for gt in all_types:
        slist = [s for s in samples if s["goal_type"] == gt]
        if not slist:
            continue
        scores = [s["t_score"] for s in slist]
        total = len(scores)
        n_t3  = sum(1 for s in scores if s >= 3)
        cnt   = Counter(scores)
        bar   = lambda pct: "█" * max(0, int(pct / 2))
        print(f"\n{gt} ({total} 樣本) | t>=3: {n_t3/total*100:.1f}%")
        for sc in sorted(cnt.keys()):
            if cnt[sc] == 0:
                continue
            pct = cnt[sc] / total * 100
            print(f"  t={sc:2d}: {cnt[sc]:5d} ({pct:5.1f}%) {bar(pct)}")

    # ── 語言感知閾值驗證 ──────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("=== 語言感知閾值（CJK=3, en=5）的全域效果 ===")
    print("=" * 70)
    lang_thr = {"zh-TW": 3, "ja": 3, "en": 5}
    total_cr = total_fn = total_fp = total_all = 0
    for gt in all_types:
        if gt == "travel":
            continue
        for lang in all_langs:
            key = (gt, lang)
            if key not in Results:
                continue
            thr = lang_thr.get(lang, 3)
            s = Results[key][thr]
            total_cr  += s["cr"]
            total_fn  += s["fn"]
            total_fp  += s["fp"]
            total_all += s["total"]
            if s["fn"] > 0 or s["fp"] > 0:
                print(f"  問題點：{gt:12s} {lang:6s} thr={thr} → fn={s['fn']} fp={s['fp']}")

    err_rate = (total_fn + total_fp) / max(total_all, 1) * 100
    print(f"\n語言感知閾值全域錯誤率：{err_rate:.3f}%"
          f"（cr={total_cr} fn={total_fn} fp={total_fp} total={total_all}）")

    print("\n=== 完成 ===")


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-crawl", action="store_true", help="跳過 Phase 1 爬取")
    args = ap.parse_args()

    if not args.skip_crawl:
        phase1_populate()
    else:
        print(f"跳過 Phase 1（DB 目前 {raw_chunks.count()} chunks）\n")

    Results, samples = phase2_analyze()
    report(Results, samples)
