import pytest

from app.config import get_settings
from app.db import database, vector_store
from app.main import app  # noqa: F401
from tests.helpers import make_client
from app.services import manual_service
from app.services.embedding import EmbeddingError


@pytest.fixture()
def client(tmp_path, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "sqlite_path", tmp_path / "t.db")
    monkeypatch.setattr(s, "chroma_dir", tmp_path / "chroma")
    monkeypatch.setattr(s, "upload_dir", tmp_path / "uploads")
    monkeypatch.setattr(vector_store, "_client", None)
    monkeypatch.setattr(manual_service, "embed_texts", lambda texts: [[1.0, 0.0] for _ in texts])
    database.init_db()
    yield make_client()
    monkeypatch.setattr(vector_store, "_client", None)


def _upload(client, name="a.txt", content="有給休暇は人事部に申請します。".encode()):
    return client.post("/api/manuals", files={"file": (name, content)})


def test_download_original_file(client):
    from fastapi.testclient import TestClient

    content = "有給休暇は人事部に申請します。".encode()
    mid = _upload(client, name="就業規則.txt", content=content).json()["id"]
    r = client.get(f"/api/manuals/{mid}/file")
    assert r.status_code == 200 and r.content == content
    assert "filename*=utf-8''" in r.headers["content-disposition"].lower()

    taro = make_client("taro", "user")  # 一般ユーザーもダウンロードできる
    assert taro.get(f"/api/manuals/{mid}/file").content == content
    assert TestClient(app).get(f"/api/manuals/{mid}/file").status_code == 401  # 未ログインは不可
    assert client.get("/api/manuals/9999/file").status_code == 404


def test_upload_list_delete(client, tmp_path):
    r = _upload(client)
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "ready" and body["chunk_count"] == 1 and body["filename"] == "a.txt"
    assert vector_store.count() == 1
    assert len(list((tmp_path / "uploads").iterdir())) == 1

    assert [m["id"] for m in client.get("/api/manuals").json()] == [body["id"]]

    assert client.delete(f"/api/manuals/{body['id']}").status_code == 204
    assert client.get("/api/manuals").json() == []
    assert vector_store.count() == 0
    assert list((tmp_path / "uploads").iterdir()) == []
    assert client.delete(f"/api/manuals/{body['id']}").status_code == 404


def test_rejects_bad_extension_empty_and_oversize(client, monkeypatch):
    assert _upload(client, "a.exe").status_code == 400
    assert _upload(client, "a.txt", b"").status_code == 400
    monkeypatch.setattr(get_settings(), "max_upload_mb", 0)
    assert _upload(client).status_code == 413


def test_parse_failure_is_recorded_as_error(client):
    r = _upload(client, "bad.pdf", b"not a pdf")
    assert r.status_code == 201
    assert r.json()["status"] == "error" and r.json()["error_message"]
    assert vector_store.count() == 0


def test_embedding_failure_leaves_no_vectors(client, monkeypatch):
    def boom(texts):
        raise EmbeddingError("失敗")

    monkeypatch.setattr(manual_service, "embed_texts", boom)
    r = _upload(client)
    assert r.json()["status"] == "error" and r.json()["error_message"] == "失敗"
    assert vector_store.count() == 0


def test_category_upload_change_and_validation(client):
    from fastapi.testclient import TestClient

    r = client.post("/api/manuals", files={"file": ("a.txt", "経費は経理部へ。".encode())}, data={"category": "  経理 "})
    assert r.status_code == 201 and r.json()["category"] == "経理"  # 前後の空白は除く
    mid = r.json()["id"]
    assert _upload(client, name="b.txt").json()["category"] == ""  # 未指定は未分類

    assert client.put(f"/api/manuals/{mid}/category", json={"category": "人事"}).status_code == 204
    assert [m["category"] for m in client.get("/api/manuals").json() if m["id"] == mid] == ["人事"]
    assert client.put(f"/api/manuals/{mid}/category", json={"category": ""}).status_code == 204  # 未分類に戻す
    assert client.put(f"/api/manuals/{mid}/category", json={"category": "あ" * 31}).status_code == 400
    assert client.put("/api/manuals/9999/category", json={"category": "x"}).status_code == 404

    taro = make_client("taro", "user")  # 変更は管理者だけ
    assert taro.put(f"/api/manuals/{mid}/category", json={"category": "x"}).status_code == 403
    assert TestClient(app).put(f"/api/manuals/{mid}/category", json={"category": "x"}).status_code == 401

    client.put(f"/api/manuals/{mid}/category", json={"category": "経理"})
    logs = client.get("/api/audit?action=manual_category").json()
    assert logs and "a.txt → 経理" in logs[0]["detail"]


def test_update_keeps_category(client):
    r = client.post("/api/manuals", files={"file": ("a.txt", "旧い内容です。".encode())}, data={"category": "経理"})
    mid = r.json()["id"]
    r2 = client.put(f"/api/manuals/{mid}", files={"file": ("a.txt", "新しい内容です。".encode())})
    assert r2.status_code == 200 and r2.json()["category"] == "経理"  # 差し替えても分類は残る


def test_init_db_adds_category_column_to_old_database(tmp_path, monkeypatch):
    import sqlite3

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE manuals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, filename TEXT NOT NULL,"
            " stored_path TEXT NOT NULL, file_type TEXT NOT NULL, file_size INTEGER NOT NULL DEFAULT 0,"
            " status TEXT NOT NULL DEFAULT 'pending', chunk_count INTEGER NOT NULL DEFAULT 0, error_message TEXT,"
            " created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')))"
        )
        conn.execute("INSERT INTO manuals(user_id, filename, stored_path, file_type) VALUES (1,'旧.txt','x','txt')")
    conn.close()
    monkeypatch.setattr(get_settings(), "sqlite_path", path)
    database.init_db()
    database.init_db()
    with database.get_connection() as c:
        assert c.execute("SELECT category FROM manuals").fetchone()["category"] == ""
