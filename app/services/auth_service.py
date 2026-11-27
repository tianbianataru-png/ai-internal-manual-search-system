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
# 登録済みユーザーは、連続でLOCK_AFTER回失敗するとLOCK_SECONDS秒ロックする(DBに記録。再起動しても残る。管理者が解除できる)
LOCK_AFTER = MAX_FAILURES
LOCK_SECONDS = 900


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
    return {
        "id": row["id"], "username": row["username"], "role": row["role"], "created_at": row["created_at"],
        "disabled": bool(row["disabled"]),
        "locked": bool(row["locked_until"] and row["locked_until"] > time.time()),
    }


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
        conn.execute("UPDATE users SET failed_count=0, locked_until=NULL WHERE id=?", (user_id,))  # ロックも解除


def set_disabled(user_id: int, disabled: bool, acting_user_id: int) -> None:
    """ユーザーの停止/再開。停止するとログイン中の端末もすべてログアウトされる。自分自身は停止できない。"""
    if disabled and user_id == acting_user_id:
        raise AuthError("自分自身は停止できません。")
    with get_connection() as conn:
        cur = conn.execute("UPDATE users SET disabled=? WHERE id=?", (1 if disabled else 0, user_id))
        if cur.rowcount == 0:
            raise AuthError("ユーザーが見つかりません。", 404)
        if disabled:
            conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))


def unlock(user_id: int) -> None:
    """ログイン失敗によるロックを解除する。"""
    with get_connection() as conn:
        cur = conn.execute("UPDATE users SET failed_count=0, locked_until=NULL WHERE id=?", (user_id,))
        if cur.rowcount == 0:
            raise AuthError("ユーザーが見つかりません。", 404)


# ---- ログイン / セッション ----
def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _new_session(conn: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires = int(time.time()) + get_settings().session_hours * 3600
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (int(time.time()),))  # 期限切れの掃除
    conn.execute(
        "INSERT INTO sessions(token_hash, user_id, expires_at) VALUES (?,?,?)",
        (_token_hash(token), user_id, expires),
    )
    return token


def change_own_password(user_id: int, current: str, new: str) -> str:
    """自分のパスワードを変更する。現在のパスワードが必要。

    他の端末のログインはすべて無効になり、今の端末用の新しいセッショントークンを返す。
    """
    _check_password_rule(new or "")
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if row is None:
        raise AuthError("ユーザーが見つかりません。", 404)
    key = row["username"].lower()
    now = time.time()
    recent = [t for t in _failures.get(key, []) if now - t < WINDOW]
    if len(recent) >= MAX_FAILURES:
        raise AuthError("失敗が続いたため、しばらくしてからお試しください。", 429)
    if not verify_password(current or "", row["password_hash"]):
        _failures[key] = recent + [now]
        raise AuthError("現在のパスワードが違います。", 400)
    _failures.pop(key, None)
    with get_connection() as conn:
        conn.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(new), user_id))
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        return _new_session(conn, user_id)


class AccountLocked(AuthError):
    """今回の失敗でアカウントがロックされた(利用者には通常の失敗と同じ応答を返し、操作ログに残す)。"""


def login(username: str, password: str) -> tuple[str, dict]:
    """成功すると (セッショントークン, ユーザー) を返す。

    登録済みユーザーは、連続失敗でDB上のロック(locked_until)がかかる。ロック中は正しいパスワードでも入れない。
    存在しないユーザー名は、メモリ上の回数制限(_failures)で同じように防ぐ。"""
    key = (username or "").strip().lower()
    now = time.time()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM users WHERE username=?", (key,)).fetchone()

    if row is None:
        recent = [t for t in _failures.get(key, []) if now - t < WINDOW]
        if len(recent) >= MAX_FAILURES:
            _failures[key] = recent
            raise AuthError("ログインの失敗が続いたため、しばらくしてからお試しください。", 429)
        verify_password(password or "", _DUMMY_HASH)
        _failures[key] = recent + [now]
        raise AuthError("ユーザー名またはパスワードが違います。", 401)

    if row["locked_until"] and row["locked_until"] > now:
        raise AuthError("ログインの失敗が続いたためロックされています。しばらくしてからお試しいただくか、管理者に解除を依頼してください。", 429)

    if not verify_password(password or "", row["password_hash"]):
        count = row["failed_count"] + 1
        with get_connection() as conn:
            if count >= LOCK_AFTER:
                conn.execute("UPDATE users SET failed_count=0, locked_until=? WHERE id=?",
                             (int(now) + LOCK_SECONDS, row["id"]))
            else:
                conn.execute("UPDATE users SET failed_count=? WHERE id=?", (count, row["id"]))
        if count >= LOCK_AFTER:
            raise AccountLocked("ユーザー名またはパスワードが違います。", 401)
        raise AuthError("ユーザー名またはパスワードが違います。", 401)

    if row["disabled"]:  # パスワードが合っている場合だけ停止を知らせる(ユーザーの存在を推測させないため)
        raise AuthError("このアカウントは停止されています。管理者に連絡してください。", 403)
    with get_connection() as conn:
        conn.execute("UPDATE users SET failed_count=0, locked_until=NULL WHERE id=?", (row["id"],))
        token = _new_session(conn, row["id"])
    return token, _public(row)


def get_user_by_token(token: str | None) -> dict | None:
    if not token:
        return None
    with get_connection() as conn:
        row = conn.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash=? AND s.expires_at >= ? AND u.disabled = 0",
            (_token_hash(token), int(time.time())),
        ).fetchone()
    return _public(row) if row else None


def logout(token: str | None) -> None:
    if token:
        with get_connection() as conn:
            conn.execute("DELETE FROM sessions WHERE token_hash=?", (_token_hash(token),))
