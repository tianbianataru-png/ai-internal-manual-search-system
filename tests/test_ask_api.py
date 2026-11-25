import json
from types import SimpleNamespace

import pytest

from app.config import get_settings
from app.db import database, vector_store
from app.main import app  # noqa: F401
from tests.helpers import make_client
from app.services import qa_service
from app.services.qa_service import NOT_FOUND


@pytest.fixture()
def client(tmp_path, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "sqlite_path", tmp_path / "t.db")
    monkeypatch.setattr(s, "chroma_dir", tmp_path / "chroma")
    monkeypatch.setattr(vector_store, "_client", None)
    monkeypatch.setattr(qa_service, "embed_query", lambda q: [1.0, 0.0])
    database.init_db()
    yield make_client()
    monkeypatch.setattr(vector_store, "_client", None)


def _fake_llm(monkeypatch, answer):
    calls = []

    def fake(question, hits, client=None):
        calls.append((question, hits))
        return answer

    monkeypatch.setattr(qa_service, "_generate_answer", fake)
    return calls


def _add_manual_chunk():
    vector_store.add_chunks(
        1, 1, ["有給休暇は入社6か月後から。"], [[1.0, 0.0]], [{"filename": "rule.pdf", "page": 3}]
    )


def test_answer_with_sources_and_history(client, monkeypatch):
    _add_manual_chunk()
    calls = _fake_llm(monkeypatch, "入社6か月後から取得できます。")
    r = client.post("/api/ask", json={"question": "有給はいつから?"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "入社6か月後から取得できます。"
    assert body["sources"] == [
        {"manual_id": 1, "manual_name": "rule.pdf", "page": 3, "text": "有給休暇は入社6か月後から。", "ref": 1}
    ]
    assert len(calls) == 1
    with database.get_connection() as c:
        row = c.execute("SELECT * FROM chat_history").fetchone()
    assert row["question"] == "有給はいつから?"
    assert json.loads(row["sources"])[0]["manual_name"] == "rule.pdf"


def test_no_manuals_does_not_call_llm(client, monkeypatch):
    calls = _fake_llm(monkeypatch, "呼ばれないはず")
    body = client.post("/api/ask", json={"question": "何か"}).json()
    assert body["answer"] == NOT_FOUND and body["sources"] == []
    assert calls == []


def test_irrelevant_chunks_filtered_by_distance(client, monkeypatch):
    vector_store.add_chunks(1, 1, ["無関係"], [[0.0, 1.0]], [{"filename": "x.txt"}])  # 距離1.0
    calls = _fake_llm(monkeypatch, "呼ばれないはず")
    body = client.post("/api/ask", json={"question": "何か"}).json()
    assert body["answer"] == NOT_FOUND and calls == []


def test_llm_says_not_found_hides_sources(client, monkeypatch):
    _add_manual_chunk()
    _fake_llm(monkeypatch, NOT_FOUND + "追記")
    body = client.post("/api/ask", json={"question": "何か"}).json()
    assert body["answer"] == NOT_FOUND and body["sources"] == []


def test_manuals_are_shared_across_users(client, monkeypatch):
    vector_store.add_chunks(9, 2, ["共通の資料"], [[1.0, 0.0]], [{"filename": "o.txt"}])  # 別の管理者が登録
    _fake_llm(monkeypatch, "答え")
    body = client.post("/api/ask", json={"question": "何か"}).json()
    assert body["sources"][0]["manual_name"] == "o.txt"


def test_validation(client):
    assert client.post("/api/ask", json={"question": "  "}).status_code == 400
    assert client.post("/api/ask", json={"question": "あ" * 501}).status_code == 400


def test_chat_failure_returns_502(client, monkeypatch):
    _add_manual_chunk()

    def boom(question, hits, client=None):
        raise qa_service.ChatError("失敗")

    monkeypatch.setattr(qa_service, "_generate_answer", boom)
    r = client.post("/api/ask", json={"question": "何か"})
    assert r.status_code == 502 and r.json()["detail"] == "失敗"


def test_generate_answer_builds_prompt_with_context():
    captured = {}

    def create(model, messages):
        captured["messages"] = messages
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=" 答え "))])

    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    hits = [{"text": "本文", "metadata": {"filename": "a.pdf", "page": 2}, "distance": 0.1}]
    assert qa_service._generate_answer("質問?", hits, fake) == "答え"
    user = captured["messages"][1]["content"]
    assert "a.pdf p.2" in user and "本文" in user and "質問?" in user


def test_only_cited_sources_returned(client, monkeypatch):
    vector_store.add_chunks(
        1, 1, ["有給は6か月後。", "通勤手当は上限あり。"], [[1.0, 0.0], [0.9, 0.1]],
        [{"filename": "a.pdf", "page": 1}, {"filename": "b.pdf", "page": 2}],
    )
    _fake_llm(monkeypatch, "有給は6か月後です。[2]")
    body = client.post("/api/ask", json={"question": "何か"}).json()
    assert len(body["sources"]) == 1 and body["sources"][0]["ref"] == 2
    assert body["sources"][0]["manual_name"] == "b.pdf"


def test_out_of_range_citation_falls_back_to_all_hits(client, monkeypatch):
    _add_manual_chunk()
    _fake_llm(monkeypatch, "答えです。[9]")
    body = client.post("/api/ask", json={"question": "何か"}).json()
    assert [s["ref"] for s in body["sources"]] == [1]


def test_search_limited_to_one_manual(client, monkeypatch):
    vector_store.add_chunks(1, 1, ["A資料"], [[1.0, 0.0]], [{"filename": "a.txt"}])
    vector_store.add_chunks(2, 1, ["B資料"], [[1.0, 0.0]], [{"filename": "b.txt"}])
    _fake_llm(monkeypatch, "答え")
    body = client.post("/api/ask", json={"question": "何か", "manual_id": 2}).json()
    assert [s["manual_name"] for s in body["sources"]] == ["b.txt"]
    none = client.post("/api/ask", json={"question": "何か", "manual_id": 99}).json()
    assert none["answer"] == NOT_FOUND
