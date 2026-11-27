import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import database, vector_store
from app.main import app
from app.services import audit_service, auth_service, manual_service
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


def _logs(admin, **params):
    r = admin.get("/api/audit", params=params)
    assert r.status_code == 200
    return r.json()


def _actions(admin):
    return [x["action"] for x in reversed(_logs(admin))]  # 古い順


def test_login_logout_and_failure_are_logged(env):
    admin = make_client("admin", "admin")
    c = TestClient(app)
    c.post("/api/auth/login", json={"username": "taro", "password": "wrong-password"})
    auth_service.create_user("taro", PASSWORD, "user")
    c.post("/api/auth/login", json={"username": "taro", "password": PASSWORD})
    c.post("/api/auth/logout")

    by_action = {x["action"]: x for x in _logs(admin)}
    assert by_action["login_failed"]["username"] == "taro" and by_action["login_failed"]["detail"]
    assert by_action["login"]["ip"] != ""
    assert _actions(admin) == ["login", "login_failed", "login", "logout"]


def test_password_is_never_logged(env):
    admin = make_client("admin", "admin")
    TestClient(app).post("/api/auth/login", json={"username": "admin", "password": "secret-wrong-pw"})
    admin.post("/api/users", json={"username": "taro", "password": "secret-new-user-pw"})
    text = str(_logs(admin))
    assert "secret-wrong-pw" not in text and "secret-new-user-pw" not in text


def test_user_and_password_actions_logged(env):
    admin = make_client("admin", "admin")
    r = admin.post("/api/users", json={"username": "taro", "password": PASSWORD, "role": "user"})
    uid = r.json()["id"]
    admin.put(f"/api/users/{uid}/password", json={"password": "new-password-1"})
    admin.put("/api/users/9999/password", json={"password": "new-password-1"})  # 失敗は記録しない
    admin.delete(f"/api/users/{uid}")

    logs = {x["action"]: x for x in _logs(admin)}
    assert logs["user_create"]["detail"] == "taro(user)" and logs["user_create"]["username"] == "admin"
    assert logs["password_reset"]["detail"] == "taro"
    assert logs["user_delete"]["detail"] == "taro"  # 削除後もユーザー名が残る
    assert _actions(admin).count("password_reset") == 1


def test_own_password_change_logged(env):
    me = make_client("taro", "user")
    me.put("/api/auth/password", json={"current_password": "wrong-pass-1", "new_password": "brand-new-pass"})
    ok = me.put("/api/auth/password", json={"current_password": PASSWORD, "new_password": "brand-new-pass"})
    assert ok.status_code == 204
    admin = make_client("admin", "admin")
    changes = [x for x in _logs(admin) if x["action"] == "password_change"]
    assert len(changes) == 1 and changes[0]["username"] == "taro"


def test_manual_upload_and_delete_logged(env):
    admin = make_client("admin", "admin")
    r = admin.post("/api/manuals", files={"file": ("rule.txt", "有給休暇は人事部に申請します。".encode())})
    assert r.status_code == 201
    assert admin.delete(f"/api/manuals/{r.json()['id']}").status_code == 204
    logs = {x["action"]: x for x in _logs(admin)}
    assert logs["manual_upload"]["detail"] == "rule.txt"
    assert logs["manual_delete"]["detail"] == "rule.txt"


def test_audit_admin_only_filter_and_paging(env):
    taro = make_client("taro", "user")
    assert taro.get("/api/audit").status_code == 403
    assert TestClient(app).get("/api/audit").status_code == 401

    admin = make_client("admin", "admin")
    for i in range(5):
        admin.post("/api/users", json={"username": f"u{i}", "password": PASSWORD})
    assert len(_logs(admin, action="user_create")) == 5
    assert all(x["action"] == "login" for x in _logs(admin, action="login"))
    ids = [x["id"] for x in _logs(admin)]
    assert ids == sorted(ids, reverse=True)  # 新しい順
    assert [x["id"] for x in _logs(admin, limit=2, offset=1)] == ids[1:3]
    assert admin.get("/api/audit", params={"action": "hack"}).status_code == 400
    assert admin.get("/api/audit", params={"limit": 0}).status_code == 422


def test_logging_failure_does_not_break_operation(env, monkeypatch):
    admin = make_client("admin", "admin")

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(audit_service, "get_connection", boom)
    r = admin.post("/api/users", json={"username": "taro", "password": PASSWORD})
    assert r.status_code == 201  # ログが書けなくても本来の操作は成功する


def test_audit_csv_export(env):
    admin = make_client("admin", "admin")
    admin.post("/api/users", json={"username": "=cmd", "password": PASSWORD, "role": "user"})
    r = admin.get("/api/audit/export.csv")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert r.text.startswith("\ufeff日時,操作,ユーザー")
    assert "user_create" in r.text and "'=cmd" in r.text
    only = admin.get("/api/audit/export.csv", params={"action": "login"}).text
    assert "user_create" not in only
    assert admin.get("/api/audit/export.csv", params={"action": "bogus"}).status_code == 400


def test_audit_csv_admin_only(env):
    admin = make_client("admin", "admin")
    admin.post("/api/users", json={"username": "taro", "password": PASSWORD, "role": "user"})
    user = TestClient(app)
    user.post("/api/auth/login", json={"username": "taro", "password": PASSWORD})
    assert user.get("/api/audit/export.csv").status_code == 403
