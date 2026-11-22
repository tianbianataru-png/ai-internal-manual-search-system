"""ログイン・ユーザー管理。パスワードは scrypt でハッシュ化し、セッションはDBで管理する。"""
import hashlib
import hmac
import secrets
import sqlite3
import time

from app.config import get_settings
from app.db.database import get_connection

ROLES = ("admin", "user")
MIN_PASSWORD_LEN = 8
MAX_PASSWORD_LEN = 128

# ログイン失敗の制限(同じユーザー名で、WINDOW秒のあいだにMAX_FAILURES回まで)
MAX_FAILURES = 5
WINDOW = 300
_failures: dict[str, list[float]] = {}


class AuthError(Exception):
    """利用者に見せてよいエラー。status_code は HTTP の応答コード。"""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


# ---- パスワード ----
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
        return hmac.compare_digest(digest, bytes.fromhex(digest_hex))
    except (ValueError, TypeError):
        return False


_DUMMY_HASH = hash_password("dummy-password")  # 存在しないユーザーでも同じ処理時間にするため


def _check_password_rule(password: str) -> None:
    if not (MIN_PASSWORD_LEN <= len(password) <= MAX_PASSWORD_LEN):
        raise AuthError(f"パスワードは{MIN_PASSWORD_LEN}文字以上{MAX_PASSWORD_LEN}文字以内にしてください。")


def _public(row: sqlite3.Row) -> dict:
    return {"id": row["id"], "username": row["username"], "role": row["role"], "created_at": row["created_at"]}


# ---- ユーザー管理 ----
def create_user(username: str, password: str, role: str = "user") -> dict:
    username = (username or "").strip()
    if not (1 <= len(username) <= 50):
        raise AuthError("ユーザー名は1〜50文字で入力してください。")
    if role not in ROLES:
        raise AuthError("権限が正しくありません。")
    _check_password_rule(password or "")
    try:
        with get_connection() as conn:
            uid = conn.execute(
                "INSERT INTO users(username, password_hash, role) VALUES (?,?,?)",
                (username, hash_password(password), role),
            ).lastrowid
            row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    except sqlite3.IntegrityError:
        raise AuthError("そのユーザー名はすでに使われています。", 409)
    return _public(row)


def list_users() -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    return [_public(r) for r in rows]


def delete_user(user_id: int, acting_user_id: int) -> None:
    """ユーザーと、そのセッション・質問履歴を削除する(登録済みマニュアルは共通資料なので残す)。"""
    if user_id == acting_user_id:
        raise AuthError("自分自身は削除できません。")
    with get_connection() as conn:
        row = conn.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
        if row is None:
            raise AuthError("ユーザーが見つかりません。", 404)
        conn.execute("DELETE FROM chat_history WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))  # sessions は連動して消える


def set_password(user_id: int, password: str) -> None:
    """パスワードを変更し、そのユーザーの既存ログインをすべて無効にする。"""
    _check_password_rule(password or "")
    with get_connection() as conn:
        cur = conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?", (hash_password(password), user_id)
        )
        if cur.rowcount == 0:
            raise AuthError("ユーザーが見つかりません。", 404)
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))


# ---- ログイン / セッション ----
def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def login(username: str, password: str) -> tuple[str, dict]:
    """成功すると (セッショントークン, ユーザー) を返す。"""
    key = (username or "").strip().lower()
    now = time.time()
    recent = [t for t in _failures.get(key, []) if now - t < WINDOW]
    if len(recent) >= MAX_FAILURES:
        _failures[key] = recent
        raise AuthError("ログインの失敗が続いたため、しばらくしてからお試しください。", 429)

    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (key,)).fetchone()
    ok = verify_password(password or "", row["password_hash"] if row else _DUMMY_HASH)
    if row is None or not ok:
        _failures[key] = recent + [now]
        raise AuthError("ユーザー名またはパスワードが違います。", 401)
    _failures.pop(key, None)

    token = secrets.token_urlsafe(32)
    expires = int(now) + get_settings().session_hours * 3600
    with get_connection() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (int(now),))  # 期限切れの掃除
        conn.execute(
            "INSERT INTO sessions(token_hash, user_id, expires_at) VALUES (?,?,?)",
            (_token_hash(token), row["id"], expires),
        )
    return token, _public(row)


def get_user_by_token(token: str | None) -> dict | None:
    if not token:
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash=? AND s.expires_at >= ?",
            (_token_hash(token), int(time.time())),
        ).fetchone()
    return _public(row) if row else None


def logout(token: str | None) -> None:
    if token:
        with get_connection() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))
