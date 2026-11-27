import gc
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import database, vector_store
from app.main import app  # noqa: F401
from app.services import backup_service
from tests.helpers import make_client


@pytest.fixture()
def env(tmp_path, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "sqlite_path", tmp_path / "data" / "app.db")
    monkeypatch.setattr(s, "chroma_dir", tmp_path / "data" / "chroma")
    monkeypatch.setattr(s, "upload_dir", tmp_path / "data" / "uploads")
    monkeypatch.setattr(vector_store, "_client", None)
    database.init_db()
    yield tmp_path
    monkeypatch.setattr(vector_store, "_client", None)
    gc.collect()


def _seed():
    s = get_settings()
    s.upload_dir.mkdir(parents=True, exist_ok=True)
    f = s.upload_dir / "abc.txt"
    f.write_text("有給は6か月後", encoding="utf-8")
    with database.get_connection() as c:
        c.execute("INSERT INTO manuals(id, user_id, filename, stored_path, file_type, status, chunk_count)"
                  " VALUES (1, 1, 'rule.txt', ?, 'txt', 'ready', 1)", (str(f),))
        c.execute("INSERT INTO chat_history(user_id, question, answer) VALUES (1, '質問', '答え')")
    vector_store.add_chunks(1, 1, ["有給は6か月後"], [[1.0, 0.0]], [{"filename": "rule.txt"}])


def test_backup_download_admin_only_and_contents(env):
    admin = make_client("admin", "admin")
    taro = make_client("taro", "user")
    _seed()
    assert taro.get("/api/backup/download").status_code == 403
    assert TestClient(app).get("/api/backup/download").status_code == 401
    r = admin.get("/api/backup/download")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    zp = env / "got.zip"
    zp.write_bytes(r.content)
    with zipfile.ZipFile(zp) as z:
        assert {"manifest.json", "app.db", "chunks.json", "uploads/abc.txt"} <= set(z.namelist())
        m = json.loads(z.read("manifest.json"))
        assert m["files"] == 1 and m["chunks"] == 1
    assert "backup" in [x["action"] for x in admin.get("/api/audit").json()]


def test_restore_roundtrip(env):
    make_client("admin", "admin")
    _seed()
    zp = env / "b.zip"
    backup_service.create_backup(zp)
    s = get_settings()
    # 元のデータを壊す
    with database.get_connection() as c:
        c.execute("DELETE FROM chat_history")
        c.execute("DELETE FROM manuals")
    vector_store.delete_manual(1)
    (s.upload_dir / "abc.txt").unlink()
    assert vector_store.count() == 0

    info = backup_service.restore_backup(zp)
    assert info["restored_chunks"] == 1
    with database.get_connection() as c:
        assert c.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0] == 1
        row = c.execute("SELECT stored_path FROM manuals").fetchone()
        assert c.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    assert (s.upload_dir / "abc.txt").read_text(encoding="utf-8") == "有給は6か月後"
    assert row["stored_path"] == str(s.upload_dir / "abc.txt")
    hits = vector_store.search([1.0, 0.0], top_k=3)
    assert hits and hits[0]["text"] == "有給は6か月後" and hits[0]["metadata"]["filename"] == "rule.txt"
    # 元のデータは消さずに残している
    assert list(s.sqlite_path.parent.glob("app.db.before-restore-*"))


def test_restore_rejects_bad_zip(env):
    bad = env / "bad.zip"
    bad.write_bytes(b"not a zip")
    with pytest.raises(backup_service.BackupError):
        backup_service.restore_backup(bad)
    evil = env / "evil.zip"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("../evil.txt", "x")
    with pytest.raises(backup_service.BackupError):
        backup_service.restore_backup(evil)
    nomani = env / "nomani.zip"
    with zipfile.ZipFile(nomani, "w") as z:
        z.writestr("app.db", "x")
    with pytest.raises(backup_service.BackupError):
        backup_service.restore_backup(nomani)
