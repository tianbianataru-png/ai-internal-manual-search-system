"""操作ログ(ログイン・ユーザー管理・マニュアル管理の記録)。パスワードなどの秘密は記録しない。"""
import logging

from fastapi import Request

from app.db.database import get_connection

logger = logging.getLogger(__name__)

# 記録する操作の種類
ACTIONS = (
    "login", "login_failed", "logout", "password_change",
    "user_create", "password_reset", "user_delete",
    "manual_upload", "manual_update", "manual_delete",
)
MAX_DETAIL = 200


def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


def record(action: str, request: Request | None = None, user: dict | None = None,
           username: str = "", detail: str = "") -> None:
    """ログを1件残す。記録に失敗しても、本来の操作は止めない。"""
    try:
        if user:
            username = user["username"]
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO audit_log(user_id, username, action, detail, ip) VALUES (?,?,?,?,?)",
                (
                    user["id"] if user else None,
                    (username or "")[:50],
                    action,
                    (detail or "")[:MAX_DETAIL],
                    client_ip(request) if request else "",
                ),
            )
    except Exception:  # noqa: BLE001
        logger.exception("操作ログの記録に失敗しました: %s", action)


def list_logs(limit: int = 100, offset: int = 0, action: str | None = None) -> list[dict]:
    """新しい順。"""
    sql = "SELECT id, username, action, detail, ip, created_at FROM audit_log"
    params: list = []
    if action:
        sql += " WHERE action = ?"
        params.append(action)
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    with get_connection() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
