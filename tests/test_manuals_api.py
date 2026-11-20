import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import database, vector_store
from app.main import app
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
    yield TestClient(app)
    monkeypatch.setattr(vector_store, "_client", None)


def _upload(client, name="a.txt", content="有給休暇は人事部に申請します。".encode()):
    return client.post("/api/manuals", files={"file": (name, content)})


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
