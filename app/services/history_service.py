"""質問履歴の一覧・詳細・削除。履歴は質問した本人(user_id)のものだけを扱う。"""
import json

from app.db.database import get_connection


class HistoryError(Exception):
    """利用者に見せてよいエラー。status_code は HTTP の応答コード。"""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _load_sources(raw: str) -> list[dict]:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


def list_history(user_id: int, limit: int = 50, offset: int = 0) -> list[dict]:
    """新しい順。"""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, question, answer, sources, created_at FROM chat_history "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "question": r["question"],
            "answer": r["answer"],
            "source_count": len(_load_sources(r["sources"])),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def get_history(history_id: int, user_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, question, answer, sources, created_at FROM chat_history "
            "WHERE id = ? AND user_id = ?",
            (history_id, user_id),
        ).fetchone()
    if row is None:
        raise HistoryError("履歴が見つかりません。", 404)
    return {
        "id": row["id"],
        "question": row["question"],
        "answer": row["answer"],
        "sources": _load_sources(row["sources"]),
        "created_at": row["created_at"],
    }


def delete_history(history_id: int, user_id: int) -> None:
    with get_connection() as conn:
        cur = conn.execute(
            "DELETE FROM chat_history WHERE id = ? AND user_id = ?", (history_id, user_id)
        )
        if cur.rowcount == 0:
            raise HistoryError("履歴が見つかりません。", 404)
