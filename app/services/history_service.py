"""質問履歴の一覧・詳細・削除。履歴は質問した本人(user_id)のものだけを扱う。"""
import json

from app.db.database import get_connection


class HistoryError(Exception):
    """利用者に見せてよいエラー。status_code は HTTP の応答コード。"""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


RATINGS = {"good": 1, "bad": -1}
_RATING_NAMES = {1: "good", -1: "bad"}


def _rating_name(value) -> str | None:
    return _RATING_NAMES.get(value)


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
            "SELECT id, question, answer, sources, rating, created_at FROM chat_history "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset),
        ).fetchall()
    return [
        {
            "id": r["id"],
            "question": r["question"],
            "answer": r["answer"],
            "source_count": len(_load_sources(r["sources"])),
            "rating": _rating_name(r["rating"]),
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def get_history(history_id: int, user_id: int) -> dict:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, question, answer, sources, rating, created_at FROM chat_history "
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
        "rating": _rating_name(row["rating"]),
        "created_at": row["created_at"],
    }


def delete_history(history_id: int, user_id: int) -> None:
    with get_connection() as conn:
        cur = conn.execute(
            "DELETE FROM chat_history WHERE id = ? AND user_id = ?", (history_id, user_id)
        )
        if cur.rowcount == 0:
            raise HistoryError("履歴が見つかりません。", 404)


def set_rating(history_id: int, user_id: int, rating: str | None) -> None:
    """回答の評価をつける。rating が None なら評価を取り消す。評価できるのは質問した本人だけ。"""
    if rating is not None and rating not in RATINGS:
        raise HistoryError("評価が正しくありません。")
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE chat_history SET rating = ? WHERE id = ? AND user_id = ?",
            (RATINGS.get(rating), history_id, user_id),
        )
        if cur.rowcount == 0:
            raise HistoryError("履歴が見つかりません。", 404)


def feedback_summary(bad_limit: int = 30) -> dict:
    """管理者向けの集計。全ユーザー分の評価の件数と、「役に立たなかった」回答の新しい順の一覧。"""
    with get_connection() as conn:
        counts = conn.execute(
            "SELECT COUNT(*) AS total,"
            " COALESCE(SUM(rating = 1), 0) AS good,"
            " COALESCE(SUM(rating = -1), 0) AS bad FROM chat_history"
        ).fetchone()
        bad_rows = conn.execute(
            "SELECT h.id, h.question, h.answer, h.created_at, u.username FROM chat_history h "
            "JOIN users u ON u.id = h.user_id WHERE h.rating = -1 ORDER BY h.id DESC LIMIT ?",
            (bad_limit,),
        ).fetchall()
    total, good, bad = counts["total"], counts["good"], counts["bad"]
    return {
        "total": total,
        "good": good,
        "bad": bad,
        "unrated": total - good - bad,
        "recent_bad": [dict(r) for r in bad_rows],
    }
