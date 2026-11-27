import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import database
from app.main import app
from tests.helpers import make_client


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "sqlite_path", tmp_path / "t.db")
    database.init_db()


def _insert(user_id, question="質問", answer="答え"):
    with database.get_connection() as c:
        return c.execute(
            "INSERT INTO chat_history(user_id, question, answer) VALUES (?,?,?)", (user_id, question, answer)
        ).lastrowid


def _uid(client):
    return client.get("/api/auth/me").json()["id"]


def test_rate_change_and_clear(env):
    taro = make_client("taro", "user")
    hid = _insert(_uid(taro))
    assert taro.get(f"/api/history/{hid}").json()["rating"] is None

    assert taro.put(f"/api/history/{hid}/rating", json={"rating": "good"}).status_code == 204
    assert taro.get(f"/api/history/{hid}").json()["rating"] == "good"
    assert taro.get("/api/history").json()[0]["rating"] == "good"  # 一覧にも出る

    assert taro.put(f"/api/history/{hid}/rating", json={"rating": "bad"}).status_code == 204  # 変更
    assert taro.get(f"/api/history/{hid}").json()["rating"] == "bad"

    assert taro.put(f"/api/history/{hid}/rating", json={"rating": None}).status_code == 204  # 取り消し
    assert taro.get(f"/api/history/{hid}").json()["rating"] is None


def test_rate_validation_and_ownership(env):
    taro = make_client("taro", "user")
    hid = _insert(_uid(taro))
    assert taro.put(f"/api/history/{hid}/rating", json={"rating": "great"}).status_code == 422
    assert taro.put(f"/api/history/{hid}/rating", json={}).status_code == 422
    assert taro.put("/api/history/9999/rating", json={"rating": "good"}).status_code == 404
    assert TestClient(app).put(f"/api/history/{hid}/rating", json={"rating": "good"}).status_code == 401

    # 他人の回答は評価できない(管理者でも)
    admin = make_client("admin", "admin")
    assert admin.put(f"/api/history/{hid}/rating", json={"rating": "bad"}).status_code == 404
    assert taro.get(f"/api/history/{hid}").json()["rating"] is None


def test_summary_admin_only(env):
    taro = make_client("taro", "user")
    assert taro.get("/api/feedback/summary").status_code == 403
    assert TestClient(app).get("/api/feedback/summary").status_code == 401


def test_summary_counts_and_recent_bad(env):
    admin = make_client("admin", "admin")
    taro = make_client("taro", "user")
    assert admin.get("/api/feedback/summary").json() == {
        "total": 0, "good": 0, "bad": 0, "unrated": 0, "recent_bad": [], "by_manual": []
    }

    a, b, c, d = (_insert(_uid(taro), question=f"質問{i}") for i in range(4))
    e = _insert(_uid(admin), question="管理者の質問")
    taro.put(f"/api/history/{a}/rating", json={"rating": "good"})
    taro.put(f"/api/history/{b}/rating", json={"rating": "bad"})
    taro.put(f"/api/history/{c}/rating", json={"rating": "bad"})
    admin.put(f"/api/history/{e}/rating", json={"rating": "good"})

    s = admin.get("/api/feedback/summary").json()
    assert (s["total"], s["good"], s["bad"], s["unrated"]) == (5, 2, 2, 1)
    assert [x["id"] for x in s["recent_bad"]] == [c, b]  # 新しい順
    assert s["recent_bad"][0]["username"] == "taro" and s["recent_bad"][0]["question"] == "質問2"

    taro.put(f"/api/history/{c}/rating", json={"rating": None})  # 取り消すと一覧から消える
    assert [x["id"] for x in admin.get("/api/feedback/summary").json()["recent_bad"]] == [b]


def test_summary_by_manual(env):
    import json

    admin = make_client("admin", "admin")
    taro = make_client("taro", "user")

    def ask_with(names, rating):
        sources = json.dumps([{"manual_name": n, "page": 1, "text": "x", "ref": i} for i, n in enumerate(names, 1)])
        with database.get_connection() as c:
            hid = c.execute(
                "INSERT INTO chat_history(user_id, question, answer, sources) VALUES (?,?,?,?)",
                (_uid(taro), "q", "a", sources),
            ).lastrowid
        if rating:
            taro.put(f"/api/history/{hid}/rating", json={"rating": rating})

    ask_with(["A.pdf"], "bad")
    ask_with(["A.pdf", "B.pdf"], "bad")  # 複数引用は両方に数える
    ask_with(["B.pdf"], "good")
    ask_with(["B.pdf"], "good")
    ask_with(["A.pdf"], None)  # 未評価は数えない
    ask_with([], "bad")  # 出典なし

    rows = admin.get("/api/feedback/summary").json()["by_manual"]
    got = {r["manual_name"]: (r["good"], r["bad"]) for r in rows}
    assert got == {"A.pdf": (0, 2), "B.pdf": (2, 1), "(出典なし・資料が見つからなかった回答)": (0, 1)}
    assert rows[-1]["manual_name"] == "B.pdf"  # 「役に立たなかった」の割合が最も低いものが最後


def test_init_db_adds_rating_column_to_old_database(tmp_path, monkeypatch):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:  # rating 列がない旧バージョンのテーブル
        conn.execute(
            "CREATE TABLE chat_history (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,"
            " question TEXT NOT NULL, answer TEXT NOT NULL, sources TEXT NOT NULL DEFAULT '[]',"
            " created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')))"
        )
        conn.execute("INSERT INTO chat_history(user_id, question, answer) VALUES (1, '古い質問', '古い答え')")
    conn.close()
    monkeypatch.setattr(get_settings(), "sqlite_path", path)
    database.init_db()
    database.init_db()  # 2回呼んでも安全
    with database.get_connection() as c:
        row = c.execute("SELECT question, rating FROM chat_history").fetchone()
    assert row["question"] == "古い質問" and row["rating"] is None


def test_unanswered_lists_not_found_questions_admin_only(env):
    from app.services.qa_service import NOT_FOUND

    admin = make_client("boss", "admin")
    taro = make_client("taro", "user")
    a = _insert(_uid(taro), "資料なしの質問", NOT_FOUND)
    _insert(_uid(taro), "答えられた質問", "有給は6か月後です")
    b = _insert(_uid(admin), "別の質問", NOT_FOUND)
    assert taro.get("/api/feedback/unanswered").status_code == 403
    body = admin.get("/api/feedback/unanswered").json()
    assert body["total"] == 2
    assert [x["id"] for x in body["items"]] == [b, a]  # 新しい順
    assert body["items"][1]["username"] == "taro" and "answer" not in body["items"][0]


def test_usage_counts_admin_only(env):
    from app.services.qa_service import NOT_FOUND

    admin = make_client("boss", "admin")
    taro = make_client("taro", "user")
    _insert(_uid(taro), "q1", "a")
    _insert(_uid(taro), "q2", NOT_FOUND)
    _insert(_uid(admin), "q3", "a")
    with database.get_connection() as conn:  # 40日前の質問は直近30日に入らない
        conn.execute(
            "INSERT INTO chat_history(user_id, question, answer, created_at) "
            "VALUES (?, 'old', 'a', datetime('now','localtime','-40 days'))", (_uid(taro),))
    assert taro.get("/api/feedback/usage").status_code == 403
    u = admin.get("/api/feedback/usage").json()
    assert (u["total"], u["last7"], u["last30"]) == (4, 3, 3)
    assert u["active_users30"] == 2 and u["unanswered30"] == 1
    assert len(u["daily"]) == 14 and u["daily"][-1]["count"] == 3 and u["daily"][0]["count"] == 0
    assert u["top_users"][0] == {"username": "taro", "count": 2}


def test_manual_usage_counts_citations_admin_only(env):
    import json

    admin = make_client("boss", "admin")
    taro = make_client("taro", "user")
    with database.get_connection() as c:
        for name, cat in (("a.pdf", "経理"), ("b.pdf", ""), ("unused.pdf", "人事")):
            c.execute("INSERT INTO manuals(user_id, filename, stored_path, file_type, category) VALUES (1,?,?,?,?)",
                      (name, name, "pdf", cat))
        ids = {r["filename"]: r["id"] for r in c.execute("SELECT id, filename FROM manuals")}

        def add(sources, when):
            c.execute("INSERT INTO chat_history(user_id, question, answer, sources, created_at) VALUES (1,'q','a',?,?)",
                      (json.dumps(sources), when))

        s_a = {"manual_id": ids["a.pdf"], "manual_name": "a.pdf"}
        add([s_a, s_a], "2099-01-01 10:00:00")  # 同じ回答で2回引用しても1回
        add([s_a, {"manual_id": ids["b.pdf"], "manual_name": "b.pdf"}], "2099-01-02 10:00:00")
        add([s_a], "2000-01-01 10:00:00")  # 古い(直近30日に入らない)
        add([{"manual_id": 9999, "manual_name": "deleted.pdf"}], "2099-01-03 10:00:00")  # 削除済みは無視
        add([], "2099-01-04 10:00:00")
    assert taro.get("/api/feedback/manual-usage").status_code == 403
    rows = {r["manual_name"]: r for r in admin.get("/api/feedback/manual-usage").json()}
    assert set(rows) == {"a.pdf", "b.pdf", "unused.pdf"}
    assert (rows["a.pdf"]["total"], rows["a.pdf"]["last_cited_at"]) == (3, "2099-01-02 10:00:00")
    assert rows["a.pdf"]["category"] == "経理" and rows["b.pdf"]["total"] == 1
    assert rows["unused.pdf"]["total"] == 0 and rows["unused.pdf"]["last_cited_at"] is None
    order = [r["manual_name"] for r in admin.get("/api/feedback/manual-usage").json()]
    assert order[0] == "unused.pdf"  # 使われていないものが先頭
