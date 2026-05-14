import os
import sqlite3
import json
import chromadb
from pathlib import Path
from datetime import datetime

DB_DIR = Path(__file__).parent.parent.parent / "data"
DB_DIR.mkdir(exist_ok=True)

SQLITE_PATH = DB_DIR / "ragraphe.db"
CHROMA_PATH = DB_DIR / "chroma"

# Collection name includes backend suffix so switching embeddings doesn't require clearing data
_LLM_BACKEND = os.getenv("LLM_BACKEND", "ollama").lower()

# ── Database backend selection ─────────────────────────────────────────────────────────────
# Set the DATABASE_URL environment variable (e.g. postgresql://user:pass@host/db) to switch to PostgreSQL
# Falls back to SQLite if not set
_DATABASE_URL = os.getenv("DATABASE_URL", "")
_DB_BACKEND = "postgresql" if _DATABASE_URL else "sqlite"


def _adapt_sql(sql: str) -> str:
    """In PostgreSQL mode, replace SQLite's ? placeholders with %s"""
    if _DB_BACKEND == "postgresql":
        return sql.replace("?", "%s")
    return sql


class _DBConn:
    """
    Unified SQLite / PostgreSQL connection interface.
    Usage: with _DBConn() as conn: ...
    - execute(sql, params) → cursor (supports fetchall / fetchone)
    - executemany(sql, params_list) → cursor
    - executescript(sql)  → splits on semicolons and executes one at a time (PostgreSQL compatible)
    commit/rollback/close are handled automatically by the context manager.
    """

    def __init__(self):
        if _DB_BACKEND == "postgresql":
            import psycopg2
            self._conn = psycopg2.connect(_DATABASE_URL)
            self._pg = True
        else:
            self._conn = sqlite3.connect(SQLITE_PATH)
            self._conn.row_factory = sqlite3.Row
            self._pg = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self._conn.close()

    def execute(self, sql: str, params=()):
        sql = _adapt_sql(sql)
        if self._pg:
            import psycopg2.extras
            cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(sql, params)
            return cur
        return self._conn.execute(sql, params)

    def executemany(self, sql: str, params_list):
        sql = _adapt_sql(sql)
        if self._pg:
            import psycopg2.extras
            cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.executemany(sql, params_list)
            return cur
        return self._conn.executemany(sql, params_list)

    def executescript(self, sql: str):
        """Execute multiple DDL/DML statements; splits into individual statements for PostgreSQL"""
        if self._pg:
            cur = self._conn.cursor()
            for stmt in sql.split(";"):
                stmt = stmt.strip()
                if stmt:
                    cur.execute(stmt)
        else:
            self._conn.executescript(sql)


# --- ChromaDB (node vectors + knowledge notes) ---

_chroma = chromadb.PersistentClient(path=str(CHROMA_PATH))
nodes_collection = _chroma.get_or_create_collection(
    f"nodes_{_LLM_BACKEND}",
    metadata={"hnsw:space": "cosine"}
)
notes_collection = _chroma.get_or_create_collection(
    f"notes_{_LLM_BACKEND}",
    metadata={"hnsw:space": "cosine"}
)


def upsert_node(node_id: str, name: str, description: str, embedding: list[float]):
    nodes_collection.upsert(
        ids=[node_id],
        embeddings=[embedding],
        documents=[description],
        metadatas=[{"name": name}],
    )


def query_nodes(embedding: list[float], n: int = 10) -> list[dict]:
    results = nodes_collection.query(query_embeddings=[embedding], n_results=n)
    nodes = []
    for i, node_id in enumerate(results["ids"][0]):
        nodes.append({
            "id": node_id,
            "name": results["metadatas"][0][i]["name"],
            "description": results["documents"][0][i],
            "distance": results["distances"][0][i],
        })
    return nodes


def get_node(node_id: str) -> dict | None:
    result = nodes_collection.get(ids=[node_id], include=["metadatas", "documents"])
    if not result["ids"]:
        return None
    return {
        "id": result["ids"][0],
        "name": result["metadatas"][0]["name"],
        "description": result["documents"][0],
    }


def list_all_nodes() -> list[dict]:
    result = nodes_collection.get(include=["metadatas", "documents"])
    nodes = []
    for i, node_id in enumerate(result["ids"]):
        nodes.append({
            "id": node_id,
            "name": result["metadatas"][i]["name"],
            "description": result["documents"][i],
        })
    return nodes


# ── SQLite / PostgreSQL (edges, user states, goals) ──────────────────────────────────

def init_db():
    with _DBConn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS node_edges (
                from_id TEXT NOT NULL,
                to_id   TEXT NOT NULL,
                type    TEXT DEFAULT 'prerequisite',
                PRIMARY KEY (from_id, to_id)
            );

            CREATE TABLE IF NOT EXISTS users (
                id         TEXT PRIMARY KEY,
                name       TEXT NOT NULL DEFAULT '',
                background TEXT NOT NULL DEFAULT '',
                skills     TEXT NOT NULL DEFAULT '[]',
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS user_node_states (
                user_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                state   TEXT NOT NULL CHECK(state IN ('knows','doesnt_know','uncertain')),
                PRIMARY KEY (user_id, node_id)
            );

            CREATE TABLE IF NOT EXISTS goals (
                id          TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL,
                description TEXT NOT NULL,
                context     TEXT,
                goal_type   TEXT DEFAULT 'general',
                created_at  TEXT
            );

            CREATE TABLE IF NOT EXISTS goal_paths (
                goal_id  TEXT NOT NULL,
                node_id  TEXT NOT NULL,
                position INTEGER NOT NULL,
                kept     INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (goal_id, node_id)
            );

            CREATE TABLE IF NOT EXISTS user_node_weights (
                user_id   TEXT NOT NULL,
                node_id   TEXT NOT NULL,
                domain    TEXT NOT NULL,
                weight    INTEGER NOT NULL DEFAULT 0,
                last_used TEXT,
                PRIMARY KEY (user_id, node_id, domain)
            );

            CREATE TABLE IF NOT EXISTS priority_sources (
                id         TEXT PRIMARY KEY,
                name       TEXT NOT NULL,
                url        TEXT NOT NULL,
                goal_types TEXT NOT NULL DEFAULT '[]',
                keywords   TEXT NOT NULL DEFAULT '[]',
                vendor_id  TEXT NOT NULL DEFAULT '',
                priority   INTEGER NOT NULL DEFAULT 100,
                category   TEXT NOT NULL DEFAULT 'general',
                ttl_days   INTEGER NOT NULL DEFAULT 30,
                created_at TEXT
            );

            CREATE TABLE IF NOT EXISTS crawled_urls (
                url         TEXT PRIMARY KEY,
                crawled_at  TEXT NOT NULL,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                category    TEXT NOT NULL DEFAULT 'general',
                expires_at  TEXT
            );

            CREATE TABLE IF NOT EXISTS og_image_cache (
                url        TEXT PRIMARY KEY,
                image_url  TEXT,
                cached_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id         TEXT PRIMARY KEY,
                goal       TEXT NOT NULL DEFAULT '',
                lang       TEXT NOT NULL DEFAULT 'zh-TW',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                data       TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS user_knowledge (
                user_id    TEXT NOT NULL,
                concept    TEXT NOT NULL,
                status     TEXT NOT NULL DEFAULT 'done',
                updated_at TEXT NOT NULL,
                PRIMARY KEY (user_id, concept)
            );

            CREATE TABLE IF NOT EXISTS event_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                node_id    TEXT NOT NULL DEFAULT '',
                node_name  TEXT NOT NULL,
                goal       TEXT NOT NULL DEFAULT '',
                feedback   TEXT NOT NULL CHECK(feedback IN ('good','bad')),
                ts         TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS node_stats (
                node_name  TEXT PRIMARY KEY,
                done_count INTEGER NOT NULL DEFAULT 0,
                last_seen  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS source_credibility (
                source        TEXT PRIMARY KEY,
                credibility   REAL NOT NULL DEFAULT 0.7,
                import_method TEXT NOT NULL DEFAULT 'unknown',
                updated_at    TEXT NOT NULL
            )
        """)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS kb_notes (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                summary     TEXT NOT NULL DEFAULT '',
                links       TEXT NOT NULL DEFAULT '[]',
                source      TEXT NOT NULL DEFAULT '',
                source_name TEXT NOT NULL DEFAULT '',
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_kb_notes_source ON kb_notes (source);
            CREATE INDEX IF NOT EXISTS idx_kb_notes_title  ON kb_notes (title);
        """)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS audit_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id      TEXT NOT NULL,
                run_at      TEXT NOT NULL,
                concept_a   TEXT NOT NULL,
                concept_b   TEXT NOT NULL,
                status      TEXT NOT NULL,
                score       REAL,
                co_mention  INTEGER,
                verifier_id TEXT,
                fix_hint    TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_audit_pair
                ON audit_history (concept_a, concept_b, run_at);

            CREATE TABLE IF NOT EXISTS audit_watchlist (
                concept    TEXT PRIMARY KEY,
                added_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS file_watch_registry (
                file_path   TEXT PRIMARY KEY,
                source_name TEXT NOT NULL,
                last_mtime  REAL NOT NULL DEFAULT 0,
                last_synced TEXT
            );
        """)
        # Add missing columns to old databases (ALTER TABLE doesn't support IF NOT EXISTS, use try/except)
        _migrate(conn)


def _migrate(conn):
    """Safely add missing columns from older database schema versions"""
    migrations = [
        "ALTER TABLE users ADD COLUMN background TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE users ADD COLUMN skills     TEXT NOT NULL DEFAULT '[]'",
        "ALTER TABLE users ADD COLUMN created_at TEXT",
        "ALTER TABLE goals ADD COLUMN goal_type  TEXT DEFAULT 'general'",
        "ALTER TABLE goals ADD COLUMN created_at TEXT",
        "ALTER TABLE priority_sources ADD COLUMN vendor_id  TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE priority_sources ADD COLUMN category   TEXT NOT NULL DEFAULT 'general'",
        "ALTER TABLE priority_sources ADD COLUMN ttl_days   INTEGER NOT NULL DEFAULT 30",
        "ALTER TABLE crawled_urls ADD COLUMN category   TEXT NOT NULL DEFAULT 'general'",
        "ALTER TABLE crawled_urls ADD COLUMN expires_at TEXT",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
        except Exception:
            pass  # Column already exists


def add_edge(from_id: str, to_id: str, edge_type: str = "prerequisite"):
    with _DBConn() as conn:
        conn.execute("""
            INSERT INTO node_edges (from_id, to_id, type) VALUES (?, ?, ?)
            ON CONFLICT(from_id, to_id) DO UPDATE SET type = excluded.type
        """, (from_id, to_id, edge_type))


def get_edges() -> list[dict]:
    with _DBConn() as conn:
        rows = conn.execute("SELECT * FROM node_edges").fetchall()
    return [dict(r) for r in rows]


def set_user_state(user_id: str, node_id: str, state: str):
    with _DBConn() as conn:
        conn.execute("""
            INSERT INTO user_node_states (user_id, node_id, state) VALUES (?, ?, ?)
            ON CONFLICT(user_id, node_id) DO UPDATE SET state = excluded.state
        """, (user_id, node_id, state))


def get_user_states(user_id: str) -> dict[str, str]:
    with _DBConn() as conn:
        rows = conn.execute(
            "SELECT node_id, state FROM user_node_states WHERE user_id = ?",
            (user_id,)
        ).fetchall()
    return {r["node_id"]: r["state"] for r in rows}


def save_goal_path(goal_id: str, user_id: str, description: str, context: str, node_ids: list[str], domain: str = "general"):
    with _DBConn() as conn:
        conn.execute("""
            INSERT INTO goals (id, user_id, description, context) VALUES (?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                user_id     = excluded.user_id,
                description = excluded.description,
                context     = excluded.context
        """, (goal_id, user_id, description, context))
        for i, node_id in enumerate(node_ids):
            conn.execute("""
                INSERT INTO goal_paths (goal_id, node_id, position, kept) VALUES (?, ?, ?, 1)
                ON CONFLICT(goal_id, node_id) DO UPDATE SET position = excluded.position
            """, (goal_id, node_id, i))


def finalize_path(goal_id: str, user_id: str, kept_node_ids: list[str], domain: str = "general"):
    """
    Called after the user confirms a path:
    - Marks which nodes were kept (kept=1) and which were removed (kept=0)
    - Kept nodes get weight +1, removed nodes get weight -1
    """
    now = datetime.now().isoformat()

    with _DBConn() as conn:
        # Fetch all nodes on this path
        rows = conn.execute(
            "SELECT node_id FROM goal_paths WHERE goal_id = ?", (goal_id,)
        ).fetchall()
        all_node_ids = {r["node_id"] for r in rows}
        kept_set = set(kept_node_ids)

        for node_id in all_node_ids:
            kept = node_id in kept_set
            # Update the goal_paths.kept column
            conn.execute(
                "UPDATE goal_paths SET kept = ? WHERE goal_id = ? AND node_id = ?",
                (1 if kept else 0, goal_id, node_id)
            )
            # Update weight
            if kept:
                conn.execute("""
                    INSERT INTO user_node_weights (user_id, node_id, domain, weight, last_used)
                    VALUES (?, ?, ?, 1, ?)
                    ON CONFLICT(user_id, node_id, domain)
                    DO UPDATE SET weight = weight + 1, last_used = excluded.last_used
                """, (user_id, node_id, domain, now))
            else:
                conn.execute("""
                    INSERT INTO user_node_weights (user_id, node_id, domain, weight, last_used)
                    VALUES (?, ?, ?, -1, ?)
                    ON CONFLICT(user_id, node_id, domain)
                    DO UPDATE SET weight = weight - 1, last_used = excluded.last_used
                """, (user_id, node_id, domain, now))


HIDE_THRESHOLD = -3  # Nodes with weight below this threshold are hidden from path planning


def get_user_weights(user_id: str, domain: str) -> dict[str, int]:
    """Returns the weight of all nodes the user has interacted with in the specified domain"""
    with _DBConn() as conn:
        rows = conn.execute(
            "SELECT node_id, weight FROM user_node_weights WHERE user_id = ? AND domain = ?",
            (user_id, domain)
        ).fetchall()
    return {r["node_id"]: r["weight"] for r in rows}


def get_hidden_nodes(user_id: str, domain: str) -> set[str]:
    """Returns node IDs with weight ≤ HIDE_THRESHOLD (excluded from path planning)"""
    with _DBConn() as conn:
        rows = conn.execute(
            "SELECT node_id FROM user_node_weights WHERE user_id = ? AND domain = ? AND weight <= ?",
            (user_id, domain, HIDE_THRESHOLD)
        ).fetchall()
    return {r["node_id"] for r in rows}


def adjust_weight(user_id: str, node_id: str, domain: str, delta: int):
    """Manually adjust a node's weight (delta can be positive or negative)"""
    now = datetime.now().isoformat()
    with _DBConn() as conn:
        conn.execute("""
            INSERT INTO user_node_weights (user_id, node_id, domain, weight, last_used)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, node_id, domain)
            DO UPDATE SET weight = weight + ?, last_used = excluded.last_used
        """, (user_id, node_id, domain, delta, now, delta))


def restore_node(user_id: str, node_id: str, domain: str):
    """Reset a hidden node's weight to 0 (makes it appear again in path planning)"""
    now = datetime.now().isoformat()
    with _DBConn() as conn:
        conn.execute("""
            INSERT INTO user_node_weights (user_id, node_id, domain, weight, last_used)
            VALUES (?, ?, ?, 0, ?)
            ON CONFLICT(user_id, node_id, domain)
            DO UPDATE SET weight = 0, last_used = excluded.last_used
        """, (user_id, node_id, domain, now))


# ── User Profile ─────────────────────────────────────────────────────────────

def upsert_profile(user_id: str, name: str, background: str, skills: list[str]):
    """Insert or update a user profile"""
    now = datetime.now().isoformat()
    with _DBConn() as conn:
        conn.execute("""
            INSERT INTO users (id, name, background, skills, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name       = excluded.name,
                background = excluded.background,
                skills     = excluded.skills
        """, (user_id, name, background, json.dumps(skills, ensure_ascii=False), now))


def get_profile(user_id: str) -> dict:
    """Get a user profile; returns defaults if not found"""
    with _DBConn() as conn:
        row = conn.execute(
            "SELECT id, name, background, skills, created_at FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
    if not row:
        return {"id": user_id, "name": "", "background": "", "skills": [], "created_at": None}
    return {
        "id":         row["id"],
        "name":       row["name"],
        "background": row["background"],
        "skills":     json.loads(row["skills"] or "[]"),
        "created_at": row["created_at"],
    }


# ── Goal History ──────────────────────────────────────────────────────────────

def record_goal(user_id: str, description: str, context: str, goal_type: str) -> str:
    """Record a completed planning goal and return the goal_id"""
    goal_id = str(uuid_hex())
    now = datetime.now().isoformat()
    with _DBConn() as conn:
        conn.execute("""
            INSERT INTO goals (id, user_id, description, context, goal_type, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                user_id     = excluded.user_id,
                description = excluded.description,
                context     = excluded.context,
                goal_type   = excluded.goal_type,
                created_at  = excluded.created_at
        """, (goal_id, user_id, description, context, goal_type, now))
    return goal_id


def get_recent_goals(user_id: str, limit: int = 10) -> list[dict]:
    """Get the user's recent goal history (newest first)"""
    with _DBConn() as conn:
        rows = conn.execute(
            "SELECT id, description, goal_type, created_at FROM goals WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        ).fetchall()
    return [dict(r) for r in rows]


def uuid_hex() -> str:
    import uuid
    return uuid.uuid4().hex[:12]


# ── Priority Sources ──────────────────────────────────────────────────────────

def add_priority_source(name: str, url: str,
                        goal_types: list[str] = None,
                        keywords: list[str] = None,
                        vendor_id: str = "",
                        priority: int = 100,
                        category: str = "general",
                        ttl_days: int = 30) -> str:
    """Add a priority source and return its id"""
    sid = uuid_hex()
    now = datetime.now().isoformat()
    with _DBConn() as conn:
        conn.execute(
            "INSERT INTO priority_sources (id, name, url, goal_types, keywords, vendor_id, priority, category, ttl_days, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (sid, name, url,
             json.dumps(goal_types or [], ensure_ascii=False),
             json.dumps(keywords or [], ensure_ascii=False),
             vendor_id, priority, category, ttl_days, now)
        )
    return sid


def get_matching_sources(node_name: str, goal_type: str = "") -> list[dict]:
    """
    Get priority sources matching a node (sorted by priority).
    Matching logic: empty goal_types = applies to all types; empty keywords = no keyword filter.
    """
    with _DBConn() as conn:
        rows = conn.execute(
            "SELECT * FROM priority_sources ORDER BY priority ASC"
        ).fetchall()

    results = []
    node_lower = node_name.lower()
    for r in rows:
        types    = json.loads(r["goal_types"] or "[]")
        keywords = json.loads(r["keywords"] or "[]")

        # Filter by goal_type
        if types and goal_type and goal_type not in types:
            continue
        # Filter by keyword (any keyword appearing in node name is a match)
        if keywords and not any(kw.lower() in node_lower for kw in keywords):
            continue

        results.append(dict(r))
    return results


def list_priority_sources() -> list[dict]:
    with _DBConn() as conn:
        rows = conn.execute("SELECT * FROM priority_sources ORDER BY priority ASC").fetchall()
    return [dict(r) for r in rows]


def delete_priority_source(source_id: str):
    with _DBConn() as conn:
        conn.execute("DELETE FROM priority_sources WHERE id = ?", (source_id,))


# ── URL Cache ──────────────────────────────────────────────────────────────────

def is_url_cached(url: str) -> bool:
    """Returns whether the URL is within its valid cache period (expires_at determined by category TTL)"""
    with _DBConn() as conn:
        row = conn.execute(
            "SELECT expires_at FROM crawled_urls WHERE url = ?", (url,)
        ).fetchone()
    if not row:
        return False
    expires_at = row["expires_at"]
    if not expires_at:          # NULL = never expires
        return True
    return datetime.now().isoformat() < expires_at


def mark_url_crawled(url: str, chunk_count: int = 0,
                     category: str = "general", ttl_days: int | None = None):
    """Record a URL as crawled and compute expires_at based on category"""
    from ragraphe.core.category import CATEGORY_TTL
    from datetime import timedelta
    days = ttl_days if ttl_days is not None else CATEGORY_TTL.get(category, 30)
    now = datetime.now()
    expires_at = None if days <= 0 else (now + timedelta(days=days)).isoformat()
    with _DBConn() as conn:
        conn.execute("""
            INSERT INTO crawled_urls (url, crawled_at, chunk_count, category, expires_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                crawled_at  = excluded.crawled_at,
                chunk_count = excluded.chunk_count,
                category    = excluded.category,
                expires_at  = excluded.expires_at
        """, (url, now.isoformat(), chunk_count, category, expires_at))


def list_crawled_urls(limit: int = 50) -> list[dict]:
    """List recently crawled URLs (newest first)"""
    with _DBConn() as conn:
        rows = conn.execute(
            "SELECT url, crawled_at, chunk_count FROM crawled_urls ORDER BY crawled_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ── og:image persistent cache ───────────────────────────────────────────────────────

def get_og_image_cache(url: str) -> str | None | bool:
    """
    Returns the cached result:
    - False → not cached
    - None  → cached but no image found
    - str   → image URL
    """
    with _DBConn() as conn:
        row = conn.execute(
            "SELECT image_url FROM og_image_cache WHERE url = ?", (url,)
        ).fetchone()
    if row is None:
        return False   # No cache record
    return row["image_url"]  # None or str


def set_og_image_cache(url: str, image_url: str | None):
    """Write or update the og:image cache entry"""
    now = datetime.now().isoformat()
    with _DBConn() as conn:
        conn.execute("""
            INSERT INTO og_image_cache (url, image_url, cached_at)
            VALUES (?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                image_url = excluded.image_url,
                cached_at = excluded.cached_at
        """, (url, image_url, now))


# ── Session Persistence ────────────────────────────────────────────────────────────

def _json_default(obj):
    """JSON serialization fallback: set/frozenset → list, others → str"""
    if isinstance(obj, (set, frozenset)):
        return list(obj)
    return str(obj)


def save_session(session_id: str, session_data: dict):
    """Serialize and save a session to the database (edge_set is excluded and rebuilt from edges)"""
    now = datetime.now().isoformat()
    data = {k: v for k, v in session_data.items() if k != "edge_set"}
    created_at = data.get("created_at", now)
    with _DBConn() as conn:
        conn.execute("""
            INSERT INTO sessions (id, goal, lang, created_at, updated_at, data)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                goal       = excluded.goal,
                lang       = excluded.lang,
                updated_at = excluded.updated_at,
                data       = excluded.data
        """, (
            session_id,
            session_data.get("goal", ""),
            session_data.get("lang", "zh-TW"),
            created_at,
            now,
            json.dumps(data, ensure_ascii=False, default=_json_default),
        ))


def load_all_sessions() -> dict:
    """Load all sessions from the database; returns {session_id: session_data}"""
    with _DBConn() as conn:
        rows = conn.execute("SELECT id, data FROM sessions").fetchall()
    result = {}
    for row in rows:
        try:
            data = json.loads(row["data"])
            # Rebuild edge_set from edges
            edges = data.get("edges", [])
            data["edge_set"] = {frozenset({e["from_id"], e["to_id"]}) for e in edges}
            result[row["id"]] = data
        except Exception:
            pass
    return result


def list_sessions() -> list[dict]:
    """Returns a summary list of sessions (used by the session picker)"""
    with _DBConn() as conn:
        rows = conn.execute(
            "SELECT id, goal, lang, created_at, updated_at, data FROM sessions ORDER BY updated_at DESC"
        ).fetchall()
    result = []
    for row in rows:
        try:
            data = json.loads(row["data"])
            node_count = len(data.get("nodes", {}))
        except Exception:
            node_count = 0
        result.append({
            "id":         row["id"],
            "goal":       row["goal"],
            "lang":       row["lang"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "node_count": node_count,
        })
    return result


def delete_session(session_id: str):
    """Delete the specified session"""
    with _DBConn() as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))


# ── Cross-Session Knowledge Memory ───────────────────────────────────────────────────────

def upsert_user_knowledge(user_id: str, concepts: list[dict]):
    """Insert or update known concepts for a user (concepts: [{concept, status}])"""
    if not concepts:
        return
    now = datetime.now().isoformat()
    with _DBConn() as conn:
        conn.executemany("""
            INSERT INTO user_knowledge (user_id, concept, status, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, concept) DO UPDATE SET
                status     = excluded.status,
                updated_at = excluded.updated_at
        """, [(user_id, c["concept"], c["status"], now) for c in concepts])


def get_user_knowledge(user_id: str) -> list[dict]:
    """Get all known concepts for a user"""
    with _DBConn() as conn:
        rows = conn.execute(
            "SELECT concept, status FROM user_knowledge WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,)
        ).fetchall()
    return [{"concept": r["concept"], "status": r["status"]} for r in rows]


# ── AI Node Quality Feedback ────────────────────────────────────────────────────────────

def record_node_feedback(session_id: str, node_id: str, node_name: str,
                         goal: str, feedback: str):
    """Record quality feedback for a single node (good / bad)"""
    now = datetime.now().isoformat()
    with _DBConn() as conn:
        conn.execute(
            "INSERT INTO event_log (session_id, node_id, node_name, goal, feedback, ts) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, node_id, node_name, goal, feedback, now),
        )


def get_recent_bad_nodes(limit: int = 20) -> list[str]:
    """Get a deduplicated list of recently marked bad node names (newest first)"""
    with _DBConn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT node_name FROM event_log WHERE feedback='bad' "
            "ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [r["node_name"] for r in rows]


# ── Cross-Session Node Popularity Statistics ─────────────────────────────────────────────────

def update_node_stats(node_names: list[str]):
    """Accumulate completion counts for nodes (called on each session save)"""
    if not node_names:
        return
    now = datetime.now().isoformat()
    with _DBConn() as conn:
        for name in node_names:
            conn.execute("""
                INSERT INTO node_stats (node_name, done_count, last_seen) VALUES (?, 1, ?)
                ON CONFLICT(node_name) DO UPDATE SET
                    done_count = done_count + 1,
                    last_seen  = excluded.last_seen
            """, (name, now))


def get_popular_nodes(min_count: int = 2, limit: int = 30) -> list[dict]:
    """Get popular nodes (marked done across multiple sessions); returns [{name, count}]"""
    with _DBConn() as conn:
        rows = conn.execute(
            "SELECT node_name, done_count FROM node_stats "
            "WHERE done_count >= ? ORDER BY done_count DESC LIMIT ?",
            (min_count, limit),
        ).fetchall()
    return [{"name": r["node_name"], "count": r["done_count"]} for r in rows]


# ── Source credibility ───────────────────────────────────────────────────────

CREDIBILITY_DEFAULTS = {
    "pdf":     0.9,
    "text":    0.9,
    "jsonl":   0.8,
    "url":     0.7,
    "crawler": 0.4,
    "unknown": 0.5,
}


def set_source_credibility(source: str, credibility: float,
                           import_method: str = "unknown") -> None:
    """Record or update the credibility weight for a knowledge source."""
    credibility = max(0.0, min(1.0, credibility))
    with _DBConn() as conn:
        conn.execute("""
            INSERT INTO source_credibility (source, credibility, import_method, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET
                credibility   = excluded.credibility,
                import_method = excluded.import_method,
                updated_at    = excluded.updated_at
        """, (source, credibility, import_method, datetime.now().isoformat()))


def get_source_credibility(source: str) -> float:
    """Return credibility for a source; defaults to 0.5 if unknown."""
    with _DBConn() as conn:
        row = conn.execute(
            "SELECT credibility FROM source_credibility WHERE source = ?", (source,)
        ).fetchone()
    return row["credibility"] if row else CREDIBILITY_DEFAULTS["unknown"]


def get_credibilities_for_sources(sources: list[str]) -> dict[str, float]:
    """Return {source: credibility} for a list of sources. Missing → 0.5."""
    if not sources:
        return {}
    with _DBConn() as conn:
        placeholders = ",".join("?" * len(sources))
        rows = conn.execute(
            f"SELECT source, credibility FROM source_credibility WHERE source IN ({placeholders})",
            sources,
        ).fetchall()
    result = {r["source"]: r["credibility"] for r in rows}
    for s in sources:
        if s not in result:
            result[s] = CREDIBILITY_DEFAULTS["unknown"]
    return result


# ── Audit history ─────────────────────────────────────────────────────────────

def record_audit_run(run_id: str, run_at: str, results: dict, verifier_id: str = "system") -> None:
    """Persist all pairs from an audit run into audit_history."""
    rows = []
    for status_key in ("gaps", "weak", "strong", "skipped"):
        for entry in results.get(status_key, []):
            rows.append((
                run_id,
                run_at,
                entry.get("concept_a", ""),
                entry.get("concept_b", ""),
                status_key.rstrip("s"),   # gaps→gap, weak→weak, strong→strong, skipped→skipped
                entry.get("kb_support_score") or entry.get("details", {}).get("embedding_similarity"),
                entry.get("details", {}).get("co_mention_count"),
                verifier_id,
                entry.get("fix_hints", {}).get("suggested_action", ""),
            ))
    if not rows:
        return
    with _DBConn() as conn:
        conn.executemany("""
            INSERT INTO audit_history
              (run_id, run_at, concept_a, concept_b, status, score, co_mention, verifier_id, fix_hint)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)


def get_audit_history(concept_a: str, concept_b: str, limit: int = 20) -> list[dict]:
    """Return audit history for a concept pair, newest first."""
    lo, hi = sorted([concept_a.strip().lower(), concept_b.strip().lower()])
    with _DBConn() as conn:
        rows = conn.execute("""
            SELECT run_at, concept_a, concept_b, status, score, co_mention, fix_hint
            FROM audit_history
            WHERE (LOWER(concept_a) = ? AND LOWER(concept_b) = ?)
               OR (LOWER(concept_a) = ? AND LOWER(concept_b) = ?)
            ORDER BY run_at DESC LIMIT ?
        """, (lo, hi, hi, lo, limit)).fetchall()
    return [dict(r) for r in rows]


def get_audit_summary() -> dict:
    """Return aggregate stats across all audit runs."""
    with _DBConn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM audit_history").fetchone()[0]
        by_status = conn.execute("""
            SELECT status, COUNT(*) as n FROM audit_history GROUP BY status
        """).fetchall()
        runs = conn.execute("SELECT COUNT(DISTINCT run_id) FROM audit_history").fetchone()[0]
    return {
        "total_entries": total,
        "total_runs": runs,
        "by_status": {r["status"]: r["n"] for r in by_status},
    }


# ── Audit watchlist ───────────────────────────────────────────────────────────

def add_watch_concepts(concepts: list[str]) -> int:
    """Add concepts to the audit watchlist. Returns count of newly added."""
    from datetime import datetime
    now = datetime.utcnow().isoformat()
    added = 0
    with _DBConn() as conn:
        for c in concepts:
            c = c.strip()
            if not c:
                continue
            existing = conn.execute(
                "SELECT 1 FROM audit_watchlist WHERE concept = ?", (c,)
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO audit_watchlist (concept, added_at) VALUES (?, ?)", (c, now)
                )
                added += 1
    return added


def remove_watch_concept(concept: str) -> bool:
    """Remove a concept from the watchlist. Returns True if it existed."""
    with _DBConn() as conn:
        rows = conn.execute(
            "DELETE FROM audit_watchlist WHERE concept = ?", (concept.strip(),)
        ).rowcount
    return rows > 0


def list_watch_concepts() -> list[str]:
    """Return all concepts in the audit watchlist, ordered by added_at."""
    with _DBConn() as conn:
        rows = conn.execute(
            "SELECT concept FROM audit_watchlist ORDER BY added_at"
        ).fetchall()
    return [r["concept"] for r in rows]


# ── File watch registry ───────────────────────────────────────────────────────

def register_file_watch(file_path: str, source_name: str) -> None:
    """Register a file for KB sync tracking."""
    with _DBConn() as conn:
        conn.execute("""
            INSERT INTO file_watch_registry (file_path, source_name, last_mtime)
            VALUES (?, ?, 0)
            ON CONFLICT(file_path) DO UPDATE SET source_name = excluded.source_name
        """, (file_path, source_name))


def list_file_watches() -> list[dict]:
    """Return all registered files with sync state."""
    with _DBConn() as conn:
        rows = conn.execute("""
            SELECT file_path, source_name, last_mtime, last_synced
            FROM file_watch_registry ORDER BY file_path
        """).fetchall()
    return [dict(r) for r in rows]


def get_file_watch(file_path: str) -> dict | None:
    """Return registry entry for a file, or None."""
    with _DBConn() as conn:
        row = conn.execute(
            "SELECT file_path, source_name, last_mtime, last_synced FROM file_watch_registry WHERE file_path = ?",
            (file_path,)
        ).fetchone()
    return dict(row) if row else None


def update_file_sync(file_path: str, mtime: float) -> None:
    """Update the last-synced mtime for a file."""
    from datetime import datetime
    with _DBConn() as conn:
        conn.execute("""
            UPDATE file_watch_registry
            SET last_mtime = ?, last_synced = ?
            WHERE file_path = ?
        """, (mtime, datetime.utcnow().isoformat(), file_path))


# ── KB Notes (Obsidian-style extracted knowledge) ────────────────────────────

def insert_notes(notes: list[dict], source: str, source_name: str = "") -> list[str]:
    """
    Insert extracted Obsidian notes into SQLite and ChromaDB.
    Each note: {title, summary, links: [str]}
    Returns list of inserted note IDs.
    """
    if not notes:
        return []

    now = datetime.now().isoformat()
    ids = []

    # Embed all note titles+summaries in one batch
    _LLM_BACKEND_LOCAL = os.getenv("LLM_BACKEND", "ollama").lower()
    if _LLM_BACKEND_LOCAL == "gemini":
        from ragraphe.llm.gemini_client import embed_batch
    else:
        from ragraphe.llm.ollama_client import embed
        def embed_batch(texts):
            return [embed(t) for t in texts]

    texts = [f"{n['title']}: {n.get('summary', '')}" for n in notes]
    embeddings = embed_batch(texts)

    with _DBConn() as conn:
        for note, emb in zip(notes, embeddings):
            note_id = uuid_hex()
            links_json = json.dumps(note.get("links", []), ensure_ascii=False)
            conn.execute("""
                INSERT INTO kb_notes (id, title, summary, links, source, source_name, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (note_id, note["title"], note.get("summary", ""),
                  links_json, source, source_name, now))
            notes_collection.upsert(
                ids=[note_id],
                embeddings=[emb],
                documents=[note.get("summary", "")],
                metadatas=[{
                    "title":       note["title"],
                    "source":      source,
                    "source_name": source_name,
                    "links":       ",".join(note.get("links", [])),
                }],
            )
            ids.append(note_id)

    return ids


def delete_notes_by_source(source: str) -> int:
    """Delete all notes from a given source. Returns count deleted."""
    with _DBConn() as conn:
        rows = conn.execute(
            "SELECT id FROM kb_notes WHERE source = ?", (source,)
        ).fetchall()
        ids = [r["id"] for r in rows]
        if ids:
            conn.execute(
                f"DELETE FROM kb_notes WHERE source = ?", (source,)
            )
    if ids:
        try:
            notes_collection.delete(ids=ids)
        except Exception:
            pass
    return len(ids)


def query_notes(embedding: list[float], n: int = 10,
                source_filter: str | None = None) -> list[dict]:
    """Vector search over notes. Returns [{id, title, summary, links, source, distance}]."""
    where = {"source": source_filter} if source_filter else None
    kwargs = {"query_embeddings": [embedding], "n_results": min(n, notes_collection.count() or 1)}
    if where:
        kwargs["where"] = where
    results = notes_collection.query(**kwargs)
    out = []
    for i, nid in enumerate(results["ids"][0]):
        meta = results["metadatas"][0][i]
        out.append({
            "id":       nid,
            "title":    meta.get("title", ""),
            "summary":  results["documents"][0][i],
            "links":    [l for l in meta.get("links", "").split(",") if l],
            "source":   meta.get("source", ""),
            "distance": results["distances"][0][i],
        })
    return out


def get_notes_by_source(source: str) -> list[dict]:
    """Return all notes for a given source from SQLite."""
    with _DBConn() as conn:
        rows = conn.execute(
            "SELECT id, title, summary, links, source, source_name, created_at "
            "FROM kb_notes WHERE source = ? ORDER BY created_at",
            (source,)
        ).fetchall()
    return [{**dict(r), "links": json.loads(r["links"] or "[]")} for r in rows]


def list_note_sources() -> list[dict]:
    """Return [{source, source_name, count}] for all note sources."""
    with _DBConn() as conn:
        rows = conn.execute("""
            SELECT source, source_name, COUNT(*) as count
            FROM kb_notes GROUP BY source ORDER BY count DESC
        """).fetchall()
    return [dict(r) for r in rows]


def find_explicit_link(title_a: str, title_b: str) -> bool:
    """
    Check if any note for title_a explicitly links to title_b, or vice versa.
    Used by kb_verify as the explicit_link signal.
    """
    a_lower, b_lower = title_a.lower(), title_b.lower()
    with _DBConn() as conn:
        # Notes whose title matches A — check if B is in their links
        rows_a = conn.execute(
            "SELECT links FROM kb_notes WHERE LOWER(title) = ?", (a_lower,)
        ).fetchall()
        for r in rows_a:
            links = [l.lower() for l in json.loads(r["links"] or "[]")]
            if b_lower in links:
                return True
        # And vice versa
        rows_b = conn.execute(
            "SELECT links FROM kb_notes WHERE LOWER(title) = ?", (b_lower,)
        ).fetchall()
        for r in rows_b:
            links = [l.lower() for l in json.loads(r["links"] or "[]")]
            if a_lower in links:
                return True
    return False
