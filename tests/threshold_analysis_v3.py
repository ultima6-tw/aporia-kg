"""
閾值分析 v3：大量測試 × 多語言 × 多類型
分析各 (goal_type, language) 組合的最佳 travel_score 閾值

測試矩陣：
  goal_type  × language → 最佳閾值
  travel / learning / business / health / tech / finance / creative / food
  × zh-TW / ja / en / ko / mixed

執行：
    LLM_BACKEND=gemini python3 tests/threshold_analysis_v3.py 2>/dev/null
"""
import re, sys, os, time, json
from collections import defaultdict, Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("LLM_BACKEND", "gemini")

from ragraphe.core.crawler import raw_chunks, query_raw_chunks
from ragraphe.llm.gemini_client import embed

# ─────────────────────────────────────────────────────────────────────────────
# 旅遊關鍵字（多語言版）
# ─────────────────────────────────────────────────────────────────────────────
_TW_TRAVEL   = r"(旅遊|景點|交通|住宿|餐廳|美食|景色|寺廟|神社|旅行|觀光|參觀|門票|入場|行程|旅館|溫泉|海灘|博物館|古蹟)"
_JA_TRAVEL   = r"(観光|旅行|宿泊|温泉|景色|名所|神社|寺|食事|ホテル|旅館|スポット|グルメ|周遊|ツアー|滞在)"
_EN_TRAVEL   = r"(tour|sightseeing|tourist|travel|hotel|resort|itinerary|attraction|landmark|accommodation|cuisine|visit|trip)"
_KO_TRAVEL   = r"(여행|관광|숙소|맛집|명소|투어|호텔|여행지|관람|입장)"

_TRAVEL_KW_MULTI = re.compile(
    f"{_TW_TRAVEL}|{_JA_TRAVEL}|{_EN_TRAVEL}|{_KO_TRAVEL}",
    re.IGNORECASE
)
# 舊版（只有中文+英文，跟 main.py 一致）
_TRAVEL_KW_ZH = re.compile(
    r"(旅遊|景點|交通|住宿|餐廳|美食|景色|寺廟|神社|旅行|觀光|參觀|門票|入場|行程|旅館|溫泉|海灘|博物館|古蹟|tour|sightseeing)",
    re.IGNORECASE
)

_LEARN_KW = re.compile(
    r"(學習|教學|課程|概念|原理|定義|算法|演算|入門|教程|tutorial|guide|learn|"
    r"勉強|教える|入門|講座|学習|コース|練習)",
    re.IGNORECASE
)

_KNOWN_CITIES = [
    "京都","大阪","東京","北海道","沖縄","福岡","神戸","横浜",
    "嵐山","金閣寺","清水寺","祇園","伏見稻荷","天龍寺","渡月橋",
    "台北","台南","高雄","台中","嘉義","花蓮","台東",
    "首爾","釜山",
    "Seoul","Busan","Tokyo","Kyoto","Osaka",
    "京都","東京","大阪","奈良","鎌倉","横浜",  # 日文城市
]

# ─────────────────────────────────────────────────────────────────────────────
# 大量測試情境：(goal_text, node_name, goal_type, language)
# ─────────────────────────────────────────────────────────────────────────────
TEST_CASES = []

def add(goal, node, gtype, lang):
    TEST_CASES.append((goal, node, gtype, lang))

# ── 旅遊 × 中文 ──────────────────────────────────────────────────────────────
for goal, nodes in [
    ("嵐山竹林一日遊",          ["渡月橋", "竹林小徑", "天龍寺", "嵯峨野小火車"]),
    ("京都三天兩夜行程規劃",      ["清水寺", "金閣寺", "錦市場", "祇園花見小路"]),
    ("東京五日自由行",           ["淺草雷門", "秋葉原", "新宿歌舞伎町", "台場"]),
    ("沖縄海島度假",             ["沖縄美麗海水族館", "古宇利島", "首里城"]),
    ("大阪美食之旅",             ["道頓堀", "心齋橋", "黑門市場", "環球影城"]),
    ("北海道冬季旅遊",           ["札幌雪祭", "函館夜景", "小樽運河"]),
    ("台南古蹟文化之旅",         ["赤崁樓", "安平古堡", "孔廟"]),
    ("花蓮太魯閣健行",           ["太魯閣峽谷", "清水斷崖", "七星潭"]),
    ("首爾購物美食五日",         ["明洞", "弘大", "東大門市場", "景福宮"]),
    ("釜山海岸自由行",           ["海雲台海水浴場", "甘川文化村", "廣安大橋"]),
]:
    for node in nodes:
        add(goal, node, "travel", "zh-TW")

# ── 旅遊 × 日文 ──────────────────────────────────────────────────────────────
for goal, nodes in [
    ("嵐山竹林を楽しむ一日旅",    ["渡月橋", "天龍寺", "竹林の道"]),
    ("京都三日間観光プラン",      ["清水寺", "金閣寺", "錦市場"]),
    ("東京自由旅行五日間",        ["浅草", "秋葉原", "新宿"]),
    ("沖縄シュノーケリング旅行",  ["青の洞窟", "古宇利島", "美ら海水族館"]),
    ("北海道冬の旅",              ["札幌雪まつり", "函館夜景", "小樽運河"]),
]:
    for node in nodes:
        add(goal, node, "travel", "ja")

# ── 旅遊 × 英文 ──────────────────────────────────────────────────────────────
for goal, nodes in [
    ("3-day Kyoto travel itinerary",    ["Kinkakuji", "Fushimi Inari", "Arashiyama"]),
    ("Tokyo 5-day trip planning",       ["Shibuya crossing", "Asakusa", "Akihabara"]),
    ("Bali beach vacation guide",       ["Kuta beach", "Ubud rice terraces", "Tanah Lot"]),
    ("Seoul food and shopping trip",    ["Myeongdong", "Hongdae", "Gyeongbokgung"]),
    ("Okinawa snorkeling holiday",      ["Blue Cave", "Kouri Island", "Churaumi"]),
]:
    for node in nodes:
        add(goal, node, "travel", "en")

# ── 學習 × 中文 ──────────────────────────────────────────────────────────────
for goal, nodes in [
    ("學日文從零開始",            ["五十音", "平假名", "片假名", "基本打招呼"]),
    ("Python 程式設計入門",       ["變數", "函式", "迴圈", "串列"]),
    ("深度學習實作",              ["神經網路", "梯度下降", "反向傳播", "CNN"]),
    ("考多益 900 分策略",         ["文法題型", "閱讀技巧", "聽力訓練"]),
    ("鋼琴入門學習",              ["拜爾練習曲", "手指獨立", "節拍器使用"]),
    ("學水彩畫技法",              ["濕畫法", "乾畫法", "色彩混合"]),
    ("英文寫作進階",              ["段落結構", "連接詞用法", "學術寫作"]),
    ("日文 JLPT N3 準備",         ["文型", "漢字", "模擬試題"]),
    ("機器學習概念",              ["監督學習", "過擬合", "特徵工程"]),
    ("吉他和弦入門",              ["C 和弦", "指法練習", "和弦轉換"]),
    ("統計學基礎",                ["平均數", "標準差", "假設檢定"]),
    ("學習西班牙文",              ["動詞變化", "陰陽性名詞", "日常用語"]),
]:
    for node in nodes:
        add(goal, node, "learning", "zh-TW")

# ── 學習 × 日文（在日本學日文、英文的情境）──────────────────────────────────
for goal, nodes in [
    ("英語をゼロから学ぶ",         ["アルファベット", "基本会話", "文法"]),
    ("プログラミング入門",         ["変数", "関数", "ループ"]),
    ("ピアノを独学で学ぶ",         ["音符の読み方", "指の練習", "バイエル"]),
]:
    for node in nodes:
        add(goal, node, "learning", "ja")

# ── 學習 × 英文 ──────────────────────────────────────────────────────────────
for goal, nodes in [
    ("Learn Python from scratch",     ["variables", "functions", "loops", "lists"]),
    ("Master machine learning",       ["neural networks", "gradient descent", "overfitting"]),
    ("IELTS 7.0 preparation",         ["reading skills", "writing structure", "speaking tips"]),
    ("Learn piano as an adult",       ["finger exercises", "music theory", "sight reading"]),
    ("Study Japanese beginner",       ["hiragana", "katakana", "basic greetings"]),
]:
    for node in nodes:
        add(goal, node, "learning", "en")

# ── 創業 × 中文 ──────────────────────────────────────────────────────────────
for goal, nodes in [
    ("開咖啡廳創業計畫",           ["菜單設計", "手沖咖啡", "店面選址", "成本控制", "品牌定位"]),
    ("餐飲創業第一步",             ["市場調查", "食材成本", "廚房規劃", "衛生許可"]),
    ("開美甲工作室",               ["設備採購", "定價策略", "客戶開發", "社群行銷"]),
    ("開設瑜伽教室",               ["場地租金", "課程設計", "師資認證"]),
    ("網路商店創業",               ["金流整合", "物流合作", "商品攝影"]),
    ("開發 SaaS 產品",             ["MVP 開發", "定價模型", "用戶獲取"]),
    ("自媒體創業",                  ["內容策略", "YouTube 演算法", "廣告收益"]),
    ("開設補習班",                  ["課程規劃", "招生策略", "師資管理"]),
]:
    for node in nodes:
        add(goal, node, "business", "zh-TW")

# ── 創業 × 英文 ──────────────────────────────────────────────────────────────
for goal, nodes in [
    ("Start a coffee shop business",  ["menu design", "equipment costs", "location scouting"]),
    ("Launch a SaaS startup",         ["MVP development", "pricing strategy", "user acquisition"]),
    ("Open an online store",          ["payment gateway", "inventory management", "product photos"]),
]:
    for node in nodes:
        add(goal, node, "business", "en")

# ── 健康 × 中文 ──────────────────────────────────────────────────────────────
for goal, nodes in [
    ("健身增肌計畫",               ["蛋白質攝取", "重訓課表", "臥推", "深蹲", "有氧搭配"]),
    ("減脂飲食規劃",               ["熱量計算", "碳水循環", "間歇性斷食"]),
    ("跑馬拉松訓練",               ["配速策略", "長跑訓練", "補給策略"]),
    ("瑜伽入門課程",               ["呼吸法", "下犬式", "貓牛式"]),
    ("備孕身體調整",               ["葉酸補充", "作息規律", "BMI 控制"]),
    ("改善睡眠品質",               ["睡眠環境", "睡前儀式", "褪黑激素"]),
    ("戒菸計畫",                   ["尼古丁替代", "心理戒斷", "支持系統"]),
]:
    for node in nodes:
        add(goal, node, "health", "zh-TW")

# ── 健康 × 英文 ──────────────────────────────────────────────────────────────
for goal, nodes in [
    ("Build muscle mass effectively",  ["protein intake", "progressive overload", "rest days"]),
    ("Lose weight with diet",          ["calorie deficit", "macros", "meal prep"]),
    ("Run a marathon",                 ["training plan", "pacing strategy", "nutrition"]),
]:
    for node in nodes:
        add(goal, node, "health", "en")

# ── 技術 × 中文 ──────────────────────────────────────────────────────────────
for goal, nodes in [
    ("建立個人技術部落格",         ["靜態網站", "React 框架", "Markdown 寫作"]),
    ("架設家庭 NAS 伺服器",        ["Synology 設定", "RAID 配置", "VPN 存取"]),
    ("學 Rust 程式語言",           ["所有權系統", "借用規則", "生命週期"]),
    ("開發 iOS App",               ["Swift UI", "Core Data", "App Store 上架"]),
    ("自動化家居系統",             ["Home Assistant", "MQTT 協議", "ESP32 設定"]),
    ("建立 CI/CD pipeline",        ["GitHub Actions", "Docker 容器", "自動部署"]),
]:
    for node in nodes:
        add(goal, node, "tech", "zh-TW")

# ── 技術 × 英文 ──────────────────────────────────────────────────────────────
for goal, nodes in [
    ("Build a personal website",       ["React components", "CSS styling", "deployment"]),
    ("Set up home server with NAS",    ["RAID configuration", "remote access", "backup"]),
    ("Learn Rust programming",         ["ownership system", "borrowing rules", "lifetimes"]),
]:
    for node in nodes:
        add(goal, node, "tech", "en")

# ── 理財 × 中文 ──────────────────────────────────────────────────────────────
for goal, nodes in [
    ("學習股票投資",               ["技術分析", "基本面分析", "選股策略"]),
    ("ETF 長期投資規劃",           ["定期定額", "資產配置", "費用比率"]),
    ("個人理財起步",               ["緊急備用金", "預算管理", "儲蓄率"]),
    ("加密貨幣入門",               ["區塊鏈原理", "比特幣", "錢包安全"]),
    ("房地產投資入門",             ["貸款試算", "租金收益", "地段評估"]),
]:
    for node in nodes:
        add(goal, node, "finance", "zh-TW")

# ── 理財 × 英文 ──────────────────────────────────────────────────────────────
for goal, nodes in [
    ("Invest in index funds",          ["dollar cost averaging", "asset allocation", "expense ratio"]),
    ("Personal finance basics",        ["emergency fund", "budget planning", "savings rate"]),
]:
    for node in nodes:
        add(goal, node, "finance", "en")

# ── 食物/料理 × 中文（容易跟旅遊混淆）──────────────────────────────────────
for goal, nodes in [
    ("學做日本料理",               ["壽司捲", "拉麵湯底", "天婦羅炸法", "味噌湯"]),
    ("學做義大利麵",               ["義大利麵條種類", "番茄醬底", "奶油培根"]),
    ("學做台灣小吃",               ["滷肉飯", "牛肉麵湯頭", "珍珠奶茶"]),
    ("烘焙入門",                   ["磅蛋糕", "馬卡龍", "可頌技巧"]),
    ("咖啡知識入門",               ["手沖壺用法", "豆子烘焙度", "義式咖啡"]),
]:
    for node in nodes:
        add(goal, node, "food", "zh-TW")

# ── 食物/料理 × 日文 ──────────────────────────────────────────────────────────
for goal, nodes in [
    ("日本料理を自宅で作る",       ["寿司の巻き方", "だし取り方", "味噌汁"]),
    ("パン作りを始める",           ["発酵の仕組み", "成形技術", "焼き上げ"]),
]:
    for node in nodes:
        add(goal, node, "food", "ja")

# ── 創意/藝術 × 中文 ──────────────────────────────────────────────────────────
for goal, nodes in [
    ("學習油畫創作",               ["畫布打底", "色彩混合", "構圖技法"]),
    ("寫小說技巧",                 ["人物塑造", "情節架構", "對話寫作"]),
    ("學街舞 Breaking",            ["地板動作", "風格訓練", "Battle 技巧"]),
    ("開始玩攝影",                 ["光圈快門", "構圖原則", "後製技巧"]),
    ("學日本插畫風格",             ["厚塗技法", "線稿上色", "背景繪製"]),
]:
    for node in nodes:
        add(goal, node, "creative", "zh-TW")

# ── 混合語言情境 ──────────────────────────────────────────────────────────────
for goal, nodes in [
    # 中日混合
    ("日本語能力試験 N2 に合格したい",     ["文型", "語彙", "聴解"]),
    ("日本の大学院に留学したい",           ["出願書類", "研究計画書", "奨学金"]),
    # 中英混合
    ("準備 GMAT 考試衝 700 分",           ["數學部分", "語文部分", "邏輯推理"]),
    ("用 LangChain 建立 RAG 系統",        ["向量資料庫", "Prompt 設計", "文件切割"]),
    # 英日混合
    ("Study JLPT N3 vocabulary",          ["kanji", "grammar patterns", "listening"]),
]:
    for node in nodes:
        add(goal, node, "learning", "mixed")

print(f"總測試組合：{len(TEST_CASES)}")
print(f"DB chunk 數：{raw_chunks.count()}")

# ── 統計資料結構 ───────────────────────────────────────────────────────────────
THRESHOLDS = [2, 3, 4, 5]
# { (goal_type, lang): { thr: {correct_reject, false_neg, false_pos, total} } }
Results = defaultdict(lambda: {
    t: {"cr":0, "fn":0, "fp":0, "total":0, "travel_snippets":0}
    for t in THRESHOLDS
})
# 原始樣本紀錄
samples = []  # { goal_type, lang, goal_is_travel, t_score_zh, t_score_multi, distance }

# ─────────────────────────────────────────────────────────────────────────────
# 執行測試
# ─────────────────────────────────────────────────────────────────────────────
print("\n開始 embedding 查詢...\n")
errors = 0
for idx, (goal_text, node_name, goal_type, lang) in enumerate(TEST_CASES):
    goal_is_travel = (
        any(c in goal_text for c in _KNOWN_CITIES)
        or len(_TRAVEL_KW_ZH.findall(goal_text)) >= 2
    )

    try:
        node_emb = embed(node_name)
        time.sleep(0.12)
    except Exception as e:
        errors += 1
        if errors <= 5:
            print(f"  [{idx+1}] EMBED ERROR: {e}")
        continue

    if raw_chunks.count() == 0:
        print("DB 空！")
        break

    results = raw_chunks.query(
        query_embeddings=[node_emb],
        n_results=min(20, raw_chunks.count()),
    )
    for j, chunk_id in enumerate(results["ids"][0]):
        doc  = results["documents"][0][j]
        dist = results["distances"][0][j]
        t_zh    = len(_TRAVEL_KW_ZH.findall(doc))
        t_multi = len(_TRAVEL_KW_MULTI.findall(doc))

        snippet_is_travel_zh    = (t_zh >= 3)
        snippet_is_travel_multi = (t_multi >= 3)

        key = (goal_type, lang)
        samples.append({
            "goal_type": goal_type, "lang": lang,
            "goal_is_travel": goal_is_travel,
            "t_zh": t_zh, "t_multi": t_multi,
            "distance": dist,
        })

        for thr in THRESHOLDS:
            # 使用多語言關鍵字版本評估
            rejected = (not goal_is_travel) and (t_multi >= thr)
            st = Results[key][thr]
            st["total"] += 1
            if snippet_is_travel_multi:
                st["travel_snippets"] += 1
            if rejected:
                if snippet_is_travel_multi:
                    st["cr"] += 1       # 正確拒絕
                else:
                    st["fn"] += 1       # 誤殺（非旅遊 snippet 被錯誤拒絕）
            else:
                if not goal_is_travel and snippet_is_travel_multi:
                    st["fp"] += 1       # 漏網（旅遊 snippet 沒被拒）

    if (idx + 1) % 20 == 0:
        print(f"  進度：{idx+1}/{len(TEST_CASES)}  errors={errors}")

print(f"\n完成！共 {len(samples)} 筆樣本（embedding 查詢），errors={errors}\n")

# ─────────────────────────────────────────────────────────────────────────────
# 輸出分析
# ─────────────────────────────────────────────────────────────────────────────
print("=" * 80)
print("=== 各 (goal_type, language) 的 travel_score 分布 + 最佳閾值 ===")
print("=" * 80)

# 決定各 (type, lang) 的最佳閾值
best_thresholds = {}

all_types = ["travel", "learning", "business", "health", "tech", "finance", "food", "creative"]
all_langs = ["zh-TW", "ja", "en", "mixed"]

print(f"\n{'type':10s} {'lang':6s}  {'chunks':6s}  {'t%>=3':6s}  "
      f"| {'thr=2':>10s}  {'thr=3':>10s}  {'thr=4':>10s}  {'thr=5':>10s}  | best")
print("-" * 100)

for gt in all_types:
    for lang in all_langs:
        key = (gt, lang)
        if key not in Results:
            continue
        # 只取 thr=3 的 total 數
        s3 = Results[key][3]
        total = s3["total"]
        if total == 0:
            continue
        travel_pct = s3["travel_snippets"] / total * 100

        # 計算各閾值錯誤率
        err_rates = {}
        for thr in THRESHOLDS:
            s = Results[key][thr]
            t = s["total"] or 1
            err_rates[thr] = (s["fn"] + s["fp"]) / t * 100

        # 最佳閾值：錯誤率最低（若平手取最大閾值，因為誤殺更嚴重）
        best = min(THRESHOLDS, key=lambda x: (err_rates[x], -x))
        best_thresholds[key] = best

        row = f"{gt:10s} {lang:6s}  {total:6d}  {travel_pct:5.1f}%  |"
        for thr in THRESHOLDS:
            s = Results[key][thr]
            cr, fn, fp = s["cr"], s["fn"], s["fp"]
            row += f"  cr={cr:3d} fn={fn:2d} fp={fp:2d}"
        row += f"  | {'★ '+str(best) if gt != 'travel' else '  n/a'}"
        print(row)
    if gt != "creative":
        print()

# ─────────────────────────────────────────────────────────────────────────────
# 推薦閾值摘要表
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("=== 推薦閾值摘要（非旅遊類型）===")
print("=" * 80)
print(f"\n{'type':12s}", end="")
for lang in all_langs:
    print(f"  {lang:8s}", end="")
print()
print("-" * 60)
for gt in all_types:
    if gt == "travel":
        continue
    print(f"{gt:12s}", end="")
    for lang in all_langs:
        key = (gt, lang)
        if key in best_thresholds:
            print(f"  {best_thresholds[key]:8d}", end="")
        else:
            print(f"  {'N/A':8s}", end="")
    print()

# ─────────────────────────────────────────────────────────────────────────────
# travel_score 分布（多語言 regex 版）
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("=== travel_score 分布（多語言 regex，embedding 查詢到的 chunk）===")
print("=" * 80)
for gt in all_types:
    slist = [s for s in samples if s["goal_type"] == gt]
    if not slist:
        continue
    scores = [s["t_multi"] for s in slist]
    total = len(scores)
    cnt = Counter(scores)
    n_travel = sum(1 for s in scores if s >= 3)
    print(f"\n{gt} ({total} 樣本)：t_multi>=3 = {n_travel/total*100:.1f}%")
    for sc in sorted(cnt.keys()):
        pct = cnt[sc] / total * 100
        bar = "█" * max(1, int(pct / 2)) if pct > 0 else ""
        print(f"  t={sc:2d}: {cnt[sc]:4d} ({pct:5.1f}%) {bar}")

# ─────────────────────────────────────────────────────────────────────────────
# 中文 vs 多語言 regex 的差異
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("=== 中文 regex vs 多語言 regex 的差距（哪些 chunk 被多語言抓到但中文沒抓到）===")
print("=" * 80)
diff_samples = [s for s in samples if s["t_multi"] >= 3 and s["t_zh"] < 3]
if diff_samples:
    gt_cnt = Counter(s["goal_type"] for s in diff_samples)
    lang_cnt = Counter(s["lang"] for s in diff_samples)
    print(f"多語言抓到但中文漏掉的 travel snippet：{len(diff_samples)} 筆")
    print(f"  按 goal_type: {dict(gt_cnt.most_common())}")
    print(f"  按 lang:      {dict(lang_cnt.most_common())}")
else:
    print("無差異（DB 以中文為主，中英文 regex 已足夠）")

# ─────────────────────────────────────────────────────────────────────────────
# food 類型的特殊分析（最容易跟旅遊混）
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 80)
print("=== food 類型深入分析（容易跟旅遊混淆的高風險類別）===")
print("=" * 80)
food_samples = [s for s in samples if s["goal_type"] == "food"]
if food_samples:
    for thr in THRESHOLDS:
        fp = sum(1 for s in food_samples
                 if not s["goal_is_travel"] and s["t_multi"] >= thr
                 and s["t_multi"] >= 3)   # snippet_is_travel
        fn = sum(1 for s in food_samples
                 if not s["goal_is_travel"] and s["t_multi"] >= thr
                 and s["t_multi"] < 3)    # snippet_not_travel
        cr = sum(1 for s in food_samples
                 if not s["goal_is_travel"] and s["t_multi"] >= thr
                 and s["t_multi"] >= 3)
        total = len(food_samples)
        print(f"  thr={thr}: cr={cr} fn={fn} total={total} error%={(fn)/max(total,1)*100:.1f}%")

print("\n=== 分析完成 ===")
