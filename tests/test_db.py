import pytest

from app.config import get_settings
from app.db import database, vector_store


@pytest.fixture()
def tmp_env(tmp_path, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "sqlite_path", tmp_path / "t.db")
    monkeypatch.setattr(s, "chroma_dir", tmp_path / "chroma")
    monkeypatch.setattr(vector_store, "_client", None)
    yield
    monkeypatch.setattr(vector_store, "_client", None)


def test_tables_created_and_user_id(tmp_env):
    database.init_db()
    database.init_db()  # 2回呼んでも壊れない
    with database.get_connection() as c:
        for table in ("manuals", "chat_history"):
            cols = [r["name"] for r in c.execute(f"PRAGMA table_info({table})")]
            assert "user_id" in cols
        c.execute(
            "INSERT INTO manuals(user_id, filename, stored_path, file_type) VALUES (1,'a.pdf','x','pdf')"
        )
    with database.get_connection() as c:
        assert c.execute("SELECT status FROM manuals").fetchone()["status"] == "pending"


def test_vector_store_roundtrip(tmp_env):
    vector_store.add_chunks(1, 1, ["りんご", "みかん"], [[1.0, 0.0], [0.0, 1.0]])
    vector_store.add_chunks(2, 2, ["他人の文書"], [[1.0, 0.0]])
    hits = vector_store.search([1.0, 0.0], user_id=1, top_k=2)
    assert hits[0]["text"] == "りんご"
    assert all(h["metadata"]["user_id"] == 1 for h in hits)
    vector_store.delete_manual(1)
    assert vector_store.count() == 1
