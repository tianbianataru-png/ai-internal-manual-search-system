"""SQLite の接続とテーブル定義。"""
import sqlite3
from contextlib import contextmanager
from typing import Iterator

from app.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user',  -- admin / user
    created_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,  -- トークン本体ではなくハッシュだけを保存する
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at INTEGER NOT NULL   -- UNIX秒
);

CREATE TABLE IF NOT EXISTS manuals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    filename    TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    file_type   TEXT NOT NULL,
    file_size   INTEGER NOT NULL DEFAULT 0,
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending / ready / error
    chunk_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_manuals_user ON manuals(user_id);

CREATE TABLE IF NOT EXISTS chat_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    question   TEXT NOT NULL,
    answer     TEXT NOT NULL,
    sources    TEXT NOT NULL DEFAULT '[]',  -- 出典情報(JSON文字列)
    rating     INTEGER,                     -- 回答の評価: 1=役に立った / -1=役に立たなかった / NULL=未評価
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_history(user_id, created_at);
"""


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """接続を開き、正常終了ならコミット、例外ならロールバックして閉じる。"""
    path = get_settings().sqlite_path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """テーブルがなければ作る(何度呼んでも安全)。"""
    with get_connection() as conn:
        conn.executescript(SCHEMA)
        # 以前のバージョンで作られたDBには rating 列がないので追加する
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(chat_history)")]
        if "rating" not in cols:
            conn.execute("ALTER TABLE chat_history ADD COLUMN rating INTEGER")
