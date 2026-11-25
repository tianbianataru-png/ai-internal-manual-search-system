import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import database, vector_store
from app.main import app
from app.services import manual_service
from app.services.embedding import EmbeddingError
from tests.helpers import make_client


@pytest.fixture()
def env(tmp_path, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "sqlite_path", tmp_path / "t.db")
    monkeypatch.setattr(s, "chroma_dir", tmp_path / "chroma")
    monkeypatch.setattr(s, "upload_dir", tmp_path / "uploads")
    monkeypatch.setattr(vector_store, "_client", None)
    monkeypatch.setattr(manual_service, "embed_texts", lambda texts: [[1.0, 0.0] for _ in texts])
    database.init_db()
    yield tmp_path
    monkeypatch.setattr(vector_store, "_client", None)


def _upload(client, name="old.txt", content="有給休暇は人事部に申請します。"):
    r = client.post("/api/manuals", files={"file": (name, content.encode())})
    assert r.status_code == 201
    return r.json()


def _update(client, manual_id, name="new.txt", content="有給休暇は勤怠システムから申請します。"):
    return client.put(f"/api/manuals/{manual_id}", files={"file": (name, content.encode())})


def _stored_texts():
    return vector_store.get_collection().get()["documents"]


def _files(tmp_path):
    return sorted(p.name for p in (tmp_path / "uploads").iterdir())


def test_update_replaces_content_and_keeps_id(env):
    admin = make_client("admin", "admin")
    m = _upload(admin)
    old_files = _files(env)
    assert m["updated_at"] is None

    r = _update(admin, m["id"])
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == m["id"] and body["filename"] == "new.txt"
    assert body["status"] == "ready" and body["chunk_count"] == 1 and body["updated_at"]
    assert body["created_at"] == m["created_at"]

    assert _stored_texts() == ["有給休暇は勤怠システムから申請します。"]  # 古い本文は残らない
    assert len(_files(env)) == 1 and _files(env) != old_files  # 古いファイルは消え、新しいファイルだけ残る
    assert [x["id"] for x in admin.get("/api/manuals").json()] == [m["id"]]  # 新規登録にはならない


def test_failed_update_keeps_original(env, monkeypatch):
    admin = make_client("admin", "admin")
    m = _upload(admin)
    files_before = _files(env)

    def boom(texts):
        raise EmbeddingError("埋め込みに失敗しました。")

    monkeypatch.setattr(manual_service, "embed_texts", boom)
    r = _update(admin, m["id"])
    assert r.status_code == 502 and "失敗" in r.json()["detail"]

    assert _stored_texts() == ["有給休暇は人事部に申請します。"]  # 元のまま
    assert _files(env) == files_before  # 新しいファイルも残らない
    now = admin.get("/api/manuals").json()[0]
    assert now["filename"] == "old.txt" and now["status"] == "ready" and now["updated_at"] is None


def test_unparseable_file_keeps_original(env):
    admin = make_client("admin", "admin")
    m = _upload(admin, name="old.txt")
    r = admin.put(f"/api/manuals/{m['id']}", files={"file": ("broken.pdf", b"this is not a pdf")})
    assert r.status_code == 400
    assert _stored_texts() == ["有給休暇は人事部に申請します。"]
    assert admin.get("/api/manuals").json()[0]["filename"] == "old.txt"
    assert len(_files(env)) == 1


def test_update_validation(env):
    admin = make_client("admin", "admin")
    m = _upload(admin)
    assert admin.put(f"/api/manuals/{m['id']}", files={"file": ("x.exe", b"abc")}).status_code == 400
    assert admin.put(f"/api/manuals/{m['id']}", files={"file": ("x.txt", b"")}).status_code == 400
    assert _update(admin, 9999).status_code == 404
    assert _stored_texts() == ["有給休暇は人事部に申請します。"]


def test_update_requires_admin(env):
    admin = make_client("admin", "admin")
    m = _upload(admin)
    user = make_client("taro", "user")
    assert _update(user, m["id"]).status_code == 403
    assert _update(TestClient(app), m["id"]).status_code == 401
    assert _stored_texts() == ["有給休暇は人事部に申請します。"]


def test_update_can_fix_a_failed_registration(env, monkeypatch):
    admin = make_client("admin", "admin")

    def boom(texts):
        raise EmbeddingError("埋め込みに失敗しました。")

    monkeypatch.setattr(manual_service, "embed_texts", boom)
    m = _upload(admin)
    assert m["status"] == "error"

    monkeypatch.setattr(manual_service, "embed_texts", lambda texts: [[1.0, 0.0] for _ in texts])
    r = _update(admin, m["id"])
    assert r.status_code == 200 and r.json()["status"] == "ready" and r.json()["error_message"] is None
    assert len(_stored_texts()) == 1


def test_replace_chunks_removes_stale_chunks(env):
    vector_store.add_chunks(1, 1, ["a", "b", "c"], [[1.0, 0.0]] * 3, [{"filename": "x"}] * 3)
    vector_store.add_chunks(2, 1, ["other"], [[1.0, 0.0]], [{"filename": "y"}])
    vector_store.replace_chunks(1, 1, ["new"], [[1.0, 0.0]], [{"filename": "x"}])
    docs = sorted(vector_store.get_collection().get()["documents"])
    assert docs == ["new", "other"]  # 余った古いチャンクは消え、他のマニュアルには影響しない

    vector_store.replace_chunks(1, 1, ["n1", "n2"], [[1.0, 0.0]] * 2, [{"filename": "x"}] * 2)
    assert sorted(vector_store.get_collection().get()["documents"]) == ["n1", "n2", "other"]


def test_update_is_logged(env):
    admin = make_client("admin", "admin")
    m = _upload(admin)
    _update(admin, m["id"])
    logs = {x["action"]: x for x in admin.get("/api/audit").json()}
    assert logs["manual_update"]["detail"] == "old.txt → new.txt"


def test_init_db_adds_updated_at_to_old_manuals_table(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:  # updated_at 列がない旧バージョンのテーブル
        conn.execute(
            "CREATE TABLE manuals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,"
            " filename TEXT NOT NULL, stored_path TEXT NOT NULL, file_type TEXT NOT NULL,"
            " file_size INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending',"
            " chunk_count INTEGER NOT NULL DEFAULT 0, error_message TEXT,"
            " created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')))"
        )
        conn.execute("INSERT INTO manuals(user_id, filename, stored_path, file_type) VALUES (1, 'a.txt', 'p', 'txt')")
    conn.close()
    monkeypatch.setattr(get_settings(), "sqlite_path", path)
    database.init_db()
    database.init_db()
    with database.get_connection() as c:
        row = c.execute("SELECT filename, updated_at FROM manuals").fetchone()
    assert row["filename"] == "a.txt" and row["updated_at"] is None
