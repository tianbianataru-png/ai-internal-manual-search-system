import json

import pytest

from app.config import get_settings
from app.db import database
from app.main import app  # noqa: F401
from tests.helpers import make_client


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "sqlite_path", tmp_path / "t.db")
    database.init_db()
    return make_client()


def _insert(question, answer="答え", sources=None, user_id=1, raw_sources=None):
    raw = raw_sources if raw_sources is not None else json.dumps(sources or [], ensure_ascii=False)
    with database.get_connection() as c:
        return c.execute(
            "INSERT INTO chat_history(user_id, question, answer, sources) VALUES (?,?,?,?)",
            (user_id, question, answer, raw),
        ).lastrowid


def test_list_newest_first_with_source_count(client):
    a = _insert("古い質問")
    b = _insert("新しい質問", sources=[{"manual_name": "a.pdf", "page": 1, "text": "本文"}])
    body = client.get("/api/history").json()
    assert [h["id"] for h in body] == [b, a]
    assert body[0]["source_count"] == 1 and body[1]["source_count"] == 0
    assert "sources" not in body[0]


def test_list_pagination_and_validation(client):
    ids = [_insert(f"q{i}") for i in range(3)]
    r = client.get("/api/history", params={"limit": 1, "offset": 1})
    assert [h["id"] for h in r.json()] == [ids[1]]
    assert client.get("/api/history", params={"limit": 0}).status_code == 422
    assert client.get("/api/history", params={"offset": -1}).status_code == 422


def test_detail_includes_sources(client):
    src = [{"manual_name": "rule.pdf", "page": 3, "text": "有給休暇は入社6か月後から。"}]
    hid = _insert("有給は?", "6か月後です。", src)
    body = client.get(f"/api/history/{hid}").json()
    assert body["question"] == "有給は?" and body["answer"] == "6か月後です。"
    assert body["sources"] == [{**src[0], "manual_id": None, "ref": None}]  # 古い履歴には番号がない


def test_detail_survives_broken_sources_json(client):
    hid = _insert("q", raw_sources="これはJSONではない")
    assert client.get(f"/api/history/{hid}").json()["sources"] == []


def test_delete_then_404(client):
    hid = _insert("消す質問")
    assert client.delete(f"/api/history/{hid}").status_code == 204
    assert client.get(f"/api/history/{hid}").status_code == 404
    assert client.delete(f"/api/history/{hid}").status_code == 404
    assert client.get("/api/history").json() == []


def test_other_users_history_is_invisible(client):
    other = _insert("他人の質問", user_id=2)
    assert client.get("/api/history").json() == []
    assert client.get(f"/api/history/{other}").status_code == 404
    assert client.delete(f"/api/history/{other}").status_code == 404
    with database.get_connection() as c:
        assert c.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0] == 1


def test_search_by_keyword_in_question_or_answer(client):
    a = _insert("有給はいつから?", answer="6か月後です")
    b = _insert("経費精算の方法", answer="システムから申請")
    ids = lambda **p: [h["id"] for h in client.get("/api/history", params=p).json()]
    assert ids(q="有給") == [a]
    assert ids(q="申請") == [b]
    assert ids(q="存在しない") == []
    assert ids(q="  ") == [b, a]


def test_keyword_wildcards_are_literal(client):
    a = _insert("100%達成")
    _insert("普通の質問")
    ids = [h["id"] for h in client.get("/api/history", params={"q": "%"}).json()]
    assert ids == [a]
    assert client.get("/api/history", params={"q": "_"}).json() == []


def test_filter_by_rating_and_combination(client):
    a = _insert("有給A")
    b = _insert("有給B")
    c = _insert("経費")
    client.put(f"/api/history/{a}/rating", json={"rating": "good"})
    client.put(f"/api/history/{b}/rating", json={"rating": "bad"})
    ids = lambda **p: [h["id"] for h in client.get("/api/history", params=p).json()]
    assert ids(rating="good") == [a]
    assert ids(rating="bad") == [b]
    assert ids(rating="none") == [c]
    assert ids(rating="bad", q="有給") == [b]
    assert client.get("/api/history", params={"rating": "x"}).status_code == 400


def test_search_only_sees_own_history(client):
    _insert("他人の秘密", user_id=999)
    assert client.get("/api/history", params={"q": "秘密"}).json() == []


def test_export_csv_with_filter_and_injection_guard(client):
    a = _insert("=SUM(1)の質問", answer="答え,カンマ")
    _insert("経費")
    client.put(f"/api/history/{a}/rating", json={"rating": "good"})
    r = client.get("/api/history/export.csv")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert r.content.startswith("\ufeff".encode())
    rows = list(__import__("csv").reader(r.content.decode("utf-8-sig").splitlines()))
    assert rows[0] == ["日時", "質問", "回答", "出典数", "評価"]
    assert len(rows) == 3
    hit = [x for x in rows if "SUM" in x[1]][0]
    assert hit[1] == "'=SUM(1)の質問" and hit[2] == "答え,カンマ" and hit[4] == "役に立った"
    only = client.get("/api/history/export.csv", params={"rating": "good"}).content.decode("utf-8-sig")
    assert "経費" not in only
    assert client.get("/api/history/export.csv", params={"rating": "x"}).status_code == 400
