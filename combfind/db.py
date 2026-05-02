import sqlite3

import sqlite_vec

SCHEMA_VERSION = 2

_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);

CREATE TABLE IF NOT EXISTS files (
    id           INTEGER PRIMARY KEY,
    path         TEXT NOT NULL UNIQUE,
    language     TEXT,
    content_hash TEXT NOT NULL,
    size_bytes   INTEGER
);

CREATE TABLE IF NOT EXISTS symbols (
    id             INTEGER PRIMARY KEY,
    file_id        INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    name           TEXT NOT NULL,
    qualified_name TEXT,
    kind           TEXT NOT NULL CHECK(kind IN (
                       'function','class','method','interface','struct',
                       'constructor','property','enum','enum_constant',
                       'record','type_alias','module','constant'
                   )),
    signature      TEXT,
    start_line     INTEGER NOT NULL,
    end_line       INTEGER NOT NULL,
    docstring      TEXT,
    content_hash   TEXT
);

CREATE TABLE IF NOT EXISTS "references" (
    src_symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    dst_symbol_id INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL CHECK(kind IN (
                      'call','inherit','import','implement','override'
                  )),
    PRIMARY KEY (src_symbol_id, dst_symbol_id, kind)
);

CREATE TABLE IF NOT EXISTS symbol_embeddings (
    symbol_id INTEGER PRIMARY KEY REFERENCES symbols(id) ON DELETE CASCADE,
    embedding BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS concepts (
    id           INTEGER PRIMARY KEY,
    name         TEXT,
    description  TEXT,
    role         TEXT CHECK(role IN (
                     'interface','implementation','orchestrator',
                     'entry_point','domain_model','infrastructure','cross_cutting'
                 )),
    centroid     BLOB,
    member_count INTEGER,
    member_hash  TEXT
);

CREATE TABLE IF NOT EXISTS concept_members (
    concept_id           INTEGER NOT NULL REFERENCES concepts(id) ON DELETE CASCADE,
    symbol_id            INTEGER NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
    distance_to_centroid REAL NOT NULL,
    PRIMARY KEY (concept_id, symbol_id)
);

CREATE TABLE IF NOT EXISTS concept_embeddings (
    concept_id INTEGER PRIMARY KEY REFERENCES concepts(id) ON DELETE CASCADE,
    embedding  BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    stage        TEXT PRIMARY KEY,
    status       TEXT NOT NULL CHECK(status IN ('pending','running','done','failed')),
    completed_at INTEGER,
    input_hash   TEXT,
    params       TEXT
);

CREATE TABLE IF NOT EXISTS build_config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_symbols_file    ON symbols(file_id);
CREATE INDEX IF NOT EXISTS idx_symbols_qname   ON symbols(qualified_name);
CREATE INDEX IF NOT EXISTS idx_refs_src        ON "references"(src_symbol_id);
CREATE INDEX IF NOT EXISTS idx_refs_dst        ON "references"(dst_symbol_id);
CREATE INDEX IF NOT EXISTS idx_members_concept ON concept_members(concept_id);
CREATE INDEX IF NOT EXISTS idx_members_symbol  ON concept_members(symbol_id);
"""


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_DDL)
    existing = conn.execute("SELECT version FROM schema_version").fetchone()
    if existing is None:
        conn.execute("INSERT INTO schema_version VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()
    elif existing["version"] < SCHEMA_VERSION:
        _migrate(conn, existing["version"])


def _migrate(conn: sqlite3.Connection, from_version: int) -> None:
    if from_version < 2:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(concepts)").fetchall()}
        if "member_hash" not in cols:
            conn.execute("ALTER TABLE concepts ADD COLUMN member_hash TEXT")
    conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
    conn.commit()
