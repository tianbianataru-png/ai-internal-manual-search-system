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


def list_history(user_id: int, limit: int = 50, offset: int = 0,
                 keyword: str | None = None, rating: str | None = None) -> list[dict]:
    """新しい順。keyword は質問・回答の部分一致、rating は good / bad / none(未評価)で絞り込む。"""
    where, params = ["user_id = ?"], [user_id]
    keyword = (keyword or "").strip()
    if keyword:
        esc = keyword.replace("!", "!!").replace("%", "!%").replace("_", "!_")  # LIKEのワイルドカードを文字として扱う
        where.append("(question LIKE ? ESCAPE '!' OR answer LIKE ? ESCAPE '!')")
        params += [f"%{esc}%", f"%{esc}%"]
    if rating:
        if rating == "none":
            where.append("rating IS NULL")
        elif rating in RATINGS:
            where.append("rating = ?")
            params.append(RATINGS[rating])
        else:
            raise HistoryError("評価の指定が正しくありません。", 400)
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, question, answer, sources, rating, created_at FROM chat_history "
            f"WHERE {' AND '.join(where)} ORDER BY id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
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
        rated_rows = conn.execute("SELECT sources, rating FROM chat_history WHERE rating IS NOT NULL").fetchall()
    total, good, bad = counts["total"], counts["good"], counts["bad"]
    return {
        "total": total,
        "good": good,
        "bad": bad,
        "unrated": total - good - bad,
        "recent_bad": [dict(r) for r in bad_rows],
        "by_manual": _by_manual(rated_rows),
    }


def unanswered(limit: int = 50) -> dict:
    """管理者向け。資料が見つからず回答できなかった質問(全ユーザー分・新しい順)と、その件数。
    マニュアルの不足を見つける手がかりにする。"""
    from app.services.qa_service import NOT_FOUND  # 循環import回避のため関数内で読み込む

    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM chat_history WHERE answer = ?", (NOT_FOUND,)).fetchone()[0]
        rows = conn.execute(
            "SELECT h.id, h.question, h.created_at, u.username FROM chat_history h "
            "JOIN users u ON u.id = h.user_id WHERE h.answer = ? ORDER BY h.id DESC LIMIT ?",
            (NOT_FOUND, limit),
        ).fetchall()
    return {"total": total, "items": [dict(r) for r in rows]}


def usage(days: int = 14) -> dict:
    """管理者向けの利用状況。質問数(全体・直近7日/30日)、直近30日の利用者数・回答できなかった数、日別、質問の多いユーザー。"""
    from app.services.qa_service import NOT_FOUND  # 循環import回避のため関数内で読み込む

    with get_connection() as conn:
        c = conn.execute(
            "SELECT COUNT(*) AS total,"
            " COALESCE(SUM(date(created_at) >= date('now','localtime','-6 days')), 0) AS last7,"
            " COALESCE(SUM(date(created_at) >= date('now','localtime','-29 days')), 0) AS last30,"
            " COUNT(DISTINCT CASE WHEN date(created_at) >= date('now','localtime','-29 days') THEN user_id END) AS users30,"
            " COALESCE(SUM(answer = ? AND date(created_at) >= date('now','localtime','-29 days')), 0) AS un30"
            " FROM chat_history",
            (NOT_FOUND,),
        ).fetchone()
        per_day = {
            r["d"]: r["n"]
            for r in conn.execute(
                "SELECT date(created_at) AS d, COUNT(*) AS n FROM chat_history "
                "WHERE date(created_at) >= date('now','localtime',?) GROUP BY d",
                (f"-{days - 1} days",),
            )
        }
        top = conn.execute(
            "SELECT u.username, COUNT(*) AS count FROM chat_history h JOIN users u ON u.id = h.user_id "
            "WHERE date(h.created_at) >= date('now','localtime','-29 days') "
            "GROUP BY h.user_id ORDER BY count DESC, u.username LIMIT 5"
        ).fetchall()
        dates = list(conn.execute(
            "SELECT " + ",".join(f"date('now','localtime','-{i} days')" for i in range(days - 1, -1, -1))
        ).fetchone())
    return {
        "total": c["total"], "last7": c["last7"], "last30": c["last30"],
        "active_users30": c["users30"], "unanswered30": c["un30"],
        "daily": [{"date": d, "count": per_day.get(d, 0)} for d in dates],
        "top_users": [dict(r) for r in top],
    }


NO_SOURCE_LABEL = "(出典なし・資料が見つからなかった回答)"


def _by_manual(rated_rows) -> list[dict]:
    """評価された回答を、出典にしたマニュアル別に数える。1つの回答が複数マニュアルを引用していれば、それぞれに数える。
    「役に立たなかった」の割合が高い順(同率は件数の多い順)に並べる。"""
    stats: dict[str, dict] = {}
    for r in rated_rows:
        names = {s.get("manual_name", "不明") for s in _load_sources(r["sources"]) if isinstance(s, dict)}
        for name in names or {NO_SOURCE_LABEL}:
            st = stats.setdefault(name, {"manual_name": name, "good": 0, "bad": 0})
            st["good" if r["rating"] == 1 else "bad"] += 1
    result = list(stats.values())
    result.sort(key=lambda x: (-x["bad"] / (x["good"] + x["bad"]), -x["bad"], x["manual_name"]))
    return result
