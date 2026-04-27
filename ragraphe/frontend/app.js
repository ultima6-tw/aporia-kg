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
