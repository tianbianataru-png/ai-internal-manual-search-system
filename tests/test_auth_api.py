import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import database, vector_store
from app.main import app
from app.services import auth_service, manual_service
from tests.helpers import PASSWORD, make_client


@pytest.fixture()
def env(tmp_path, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "sqlite_path", tmp_path / "t.db")
    monkeypatch.setattr(s, "chroma_dir", tmp_path / "chroma")
    monkeypatch.setattr(s, "upload_dir", tmp_path / "uploads")
    monkeypatch.setattr(vector_store, "_client", None)
    monkeypatch.setattr(manual_service, "embed_texts", lambda texts: [[1.0, 0.0] for _ in texts])
    database.init_db()
    yield
    monkeypatch.setattr(vector_store, "_client", None)


def test_password_hash_roundtrip():
    h = auth_service.hash_password("secret-pass")
    assert "secret-pass" not in h
    assert auth_service.verify_password("secret-pass", h)
    assert not auth_service.verify_password("other", h)
    assert not auth_service.verify_password("x", "broken")


def test_login_logout_me(env):
    auth_service.create_user("Taro", PASSWORD)
    c = TestClient(app)
    assert c.get("/api/auth/me").status_code == 401
    r = c.post("/api/auth/login", json={"username": "taro", "password": PASSWORD})  # 大文字小文字は区別しない
    assert r.status_code == 200 and r.json()["role"] == "user"
    assert "password" not in r.text and "hash" not in r.text
    assert "httponly" in r.headers["set-cookie"].lower()
    assert c.get("/api/auth/me").json()["username"] == "Taro"
    assert c.post("/api/auth/logout").status_code == 204
    assert c.get("/api/auth/me").status_code == 401


def test_wrong_password_and_unknown_user_same_message(env):
    auth_service._failures.clear()
    auth_service.create_user("taro", PASSWORD)
    c = TestClient(app)
    a = c.post("/api/auth/login", json={"username": "taro", "password": "wrong-password"})
    b = c.post("/api/auth/login", json={"username": "nobody", "password": "wrong-password"})
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


def test_login_throttled_after_repeated_failures(env):
    auth_service._failures.clear()
    auth_service.create_user("taro", PASSWORD)
    c = TestClient(app)
    for _ in range(auth_service.MAX_FAILURES):
        assert c.post("/api/auth/login", json={"username": "taro", "password": "bad-password"}).status_code == 401
    # 正しいパスワードでも、制限中は入れない
    assert c.post("/api/auth/login", json={"username": "taro", "password": PASSWORD}).status_code == 429
    auth_service._failures.clear()


def test_expired_session_rejected(env):
    c = make_client("taro", "user")
    with database.get_connection() as conn:
        conn.execute("UPDATE sessions SET expires_at = 0")
    assert c.get("/api/auth/me").status_code == 401


def test_apis_require_login(env):
    c = TestClient(app)
    for method, path in [
        ("get", "/api/manuals"), ("post", "/api/ask"), ("get", "/api/history"),
        ("get", "/api/users"), ("delete", "/api/manuals/1"),
    ]:
        assert getattr(c, method)(path).status_code == 401, path
    assert c.post("/api/manuals", files={"file": ("a.txt", b"x")}).status_code == 401


def test_normal_user_cannot_manage(env):
    make_client("admin", "admin")
    user = make_client("taro", "user")
    assert user.get("/api/manuals").status_code == 200  # 閲覧はできる
    assert user.post("/api/manuals", files={"file": ("a.txt", b"hello")}).status_code == 403
    assert user.delete("/api/manuals/1").status_code == 403
    assert user.get("/api/users").status_code == 403
    assert user.post("/api/users", json={"username": "x", "password": PASSWORD}).status_code == 403
    assert user.put("/api/users/1/password", json={"password": "new-password-1"}).status_code == 403
    assert user.delete("/api/users/1").status_code == 403


def test_admin_uploads_and_user_sees_it(env):
    admin = make_client("admin", "admin")
    user = make_client("taro", "user")
    r = admin.post("/api/manuals", files={"file": ("a.txt", "有給は人事へ。".encode())})
    assert r.status_code == 201
    assert [m["filename"] for m in user.get("/api/manuals").json()] == ["a.txt"]


def test_history_is_per_user(env):
    a = make_client("alice", "user")
    b = make_client("bob", "user")
    with database.get_connection() as conn:
        conn.execute("INSERT INTO chat_history(user_id, question, answer) VALUES (1, 'aliceの質問', 'x')")
    assert len(a.get("/api/history").json()) == 1
    assert b.get("/api/history").json() == []
    hid = a.get("/api/history").json()[0]["id"]
    assert b.get(f"/api/history/{hid}").status_code == 404


def test_admin_user_management(env):
    admin = make_client("admin", "admin")
    r = admin.post("/api/users", json={"username": "taro", "password": PASSWORD, "role": "user"})
    assert r.status_code == 201 and "password" not in r.text
    uid = r.json()["id"]
    assert admin.post("/api/users", json={"username": "TARO", "password": PASSWORD}).status_code == 409
    assert admin.post("/api/users", json={"username": "x", "password": "short"}).status_code == 400
    assert admin.post("/api/users", json={"username": "x", "password": PASSWORD, "role": "root"}).status_code == 400
    assert len(admin.get("/api/users").json()) == 2

    # パスワード変更で、既存のログインは無効になり、新パスワードで入れる
    taro = TestClient(app)
    taro.post("/api/auth/login", json={"username": "taro", "password": PASSWORD})
    assert taro.get("/api/auth/me").status_code == 200
    assert admin.put(f"/api/users/{uid}/password", json={"password": "new-password-1"}).status_code == 204
    assert taro.get("/api/auth/me").status_code == 401
    assert taro.post("/api/auth/login", json={"username": "taro", "password": "new-password-1"}).status_code == 200

    assert admin.delete(f"/api/users/{uid}").status_code == 204
    assert taro.get("/api/auth/me").status_code == 401  # 削除されたユーザーのセッションも消える
    assert admin.delete(f"/api/users/{uid}").status_code == 404


def test_admin_cannot_delete_self(env):
    admin = make_client("admin", "admin")
    me = admin.get("/api/auth/me").json()
    assert admin.delete(f"/api/users/{me['id']}").status_code == 400
    assert len(admin.get("/api/users").json()) == 1


def test_change_own_password(env):
    me = make_client("taro", "user")
    other = TestClient(app)  # 別の端末
    other.post("/api/auth/login", json={"username": "taro", "password": PASSWORD})

    r = me.put("/api/auth/password", json={"current_password": PASSWORD, "new_password": "brand-new-pass"})
    assert r.status_code == 204
    assert me.get("/api/auth/me").status_code == 200  # この端末はログインしたまま
    assert other.get("/api/auth/me").status_code == 401  # 他の端末はログアウト
    fresh = TestClient(app)
    assert fresh.post("/api/auth/login", json={"username": "taro", "password": PASSWORD}).status_code == 401
    assert fresh.post("/api/auth/login", json={"username": "taro", "password": "brand-new-pass"}).status_code == 200


def test_change_own_password_validation(env):
    me = make_client("taro", "user")
    wrong = me.put("/api/auth/password", json={"current_password": "wrong-pass-1", "new_password": "brand-new-pass"})
    assert wrong.status_code == 400
    short = me.put("/api/auth/password", json={"current_password": PASSWORD, "new_password": "short"})
    assert short.status_code == 400
    assert TestClient(app).put(
        "/api/auth/password", json={"current_password": PASSWORD, "new_password": "brand-new-pass"}
    ).status_code == 401
    # 変更されていない
    assert TestClient(app).post("/api/auth/login", json={"username": "taro", "password": PASSWORD}).status_code == 200


def test_change_password_throttled(env):
    me = make_client("taro", "user")
    for _ in range(auth_service.MAX_FAILURES):
        assert me.put("/api/auth/password", json={"current_password": "wrong-pass-1", "new_password": "brand-new-pass"}).status_code == 400
    assert me.put("/api/auth/password", json={"current_password": PASSWORD, "new_password": "brand-new-pass"}).status_code == 429
    auth_service._failures.clear()


def test_admin_reset_password_validation(env):
    admin = make_client("admin", "admin")
    taro = make_client("taro", "user")
    uid = next(u["id"] for u in admin.get("/api/users").json() if u["username"] == "taro")

    # 短すぎるパスワードは拒否され、元のパスワードのまま・ログインも維持される
    assert admin.put(f"/api/users/{uid}/password", json={"password": "short"}).status_code == 400
    assert taro.get("/api/auth/me").status_code == 200
    assert TestClient(app).post("/api/auth/login", json={"username": "taro", "password": PASSWORD}).status_code == 200

    # 存在しないユーザー
    assert admin.put("/api/users/9999/password", json={"password": "new-password-1"}).status_code == 404

    # 未ログインは401、一般ユーザーは(自分自身でも)403
    assert TestClient(app).put(f"/api/users/{uid}/password", json={"password": "new-password-1"}).status_code == 401
    assert taro.put(f"/api/users/{uid}/password", json={"password": "new-password-1"}).status_code == 403


def test_admin_reset_password_replaces_old_password(env):
    admin = make_client("admin", "admin")
    make_client("taro", "user")
    uid = next(u["id"] for u in admin.get("/api/users").json() if u["username"] == "taro")

    assert admin.put(f"/api/users/{uid}/password", json={"password": "new-password-1"}).status_code == 204
    fresh = TestClient(app)
    assert fresh.post("/api/auth/login", json={"username": "taro", "password": PASSWORD}).status_code == 401
    assert fresh.post("/api/auth/login", json={"username": "taro", "password": "new-password-1"}).status_code == 200
    assert admin.get("/api/auth/me").status_code == 200  # 管理者本人のログインは影響を受けない


def test_admin_reset_own_password_logs_out_admin(env):
    admin = make_client("admin", "admin")
    me = admin.get("/api/auth/me").json()
    assert admin.put(f"/api/users/{me['id']}/password", json={"password": "new-password-1"}).status_code == 204
    assert admin.get("/api/auth/me").status_code == 401  # 自分のセッションも無効になる
    assert TestClient(app).post("/api/auth/login", json={"username": "admin", "password": "new-password-1"}).status_code == 200
