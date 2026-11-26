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


def _add_manual_row(manual_id, name, category, status="ready"):
    with database.get_connection() as c:
        c.execute(
            "INSERT INTO manuals(id, user_id, filename, stored_path, file_type, status, category) VALUES (?,?,?,?,?,?,?)",
            (manual_id, 1, name, "x", "txt", status, category),
        )


def test_search_limited_to_category(client, monkeypatch):
    _add_manual_row(1, "a.txt", "経理")
    _add_manual_row(2, "b.txt", "人事")
    _add_manual_row(3, "c.txt", "経理")
    for mid, name in [(1, "a.txt"), (2, "b.txt"), (3, "c.txt")]:
        vector_store.add_chunks(mid, 1, [f"{name}の資料"], [[1.0, 0.0]], [{"filename": name}])
    _fake_llm(monkeypatch, "答え")

    body = client.post("/api/ask", json={"question": "何か", "category": "経理"}).json()
    assert sorted(s["manual_name"] for s in body["sources"]) == ["a.txt", "c.txt"]

    # 分類 + マニュアルの両方を指定すると、その分類の中のそのマニュアルだけ
    body = client.post("/api/ask", json={"question": "何か", "category": "経理", "manual_id": 3}).json()
    assert [s["manual_name"] for s in body["sources"]] == ["c.txt"]
    body = client.post("/api/ask", json={"question": "何か", "category": "経理", "manual_id": 2}).json()
    assert body["answer"] == NOT_FOUND and body["sources"] == []  # 分類の外のマニュアルは対象外

    # 空文字・未指定は絞り込みなし
    for cat in ("", None):
        body = client.post("/api/ask", json={"question": "何か", "category": cat}).json()
        assert len(body["sources"]) == 3


def test_category_without_manuals_does_not_call_llm(client, monkeypatch):
    _add_manual_row(1, "a.txt", "経理")
    vector_store.add_chunks(1, 1, ["資料"], [[1.0, 0.0]], [{"filename": "a.txt"}])
    calls = _fake_llm(monkeypatch, "呼ばれないはず")
    body = client.post("/api/ask", json={"question": "何か", "category": "存在しない分類"}).json()
    assert body["answer"] == NOT_FOUND and calls == []


def _parse_sse(text):
    out = []
    for block in text.strip().split("\n\n"):
        ev = block.split("\n")[0][len("event: "):]
        data = json.loads(block.split("\n")[1][len("data: "):])
        out.append((ev, data))
    return out


def _fake_stream(monkeypatch, pieces):
    monkeypatch.setattr(qa_service, "_generate_answer_stream", lambda q, h, client=None: iter(pieces))


def test_stream_sends_deltas_then_done_and_saves_history(client, monkeypatch):
    _add_manual_chunk()
    _fake_stream(monkeypatch, ["入社6か月", "後から[1]"])
    r = client.post("/api/ask/stream", json={"question": "有給は?"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = _parse_sse(r.text)
    assert [e for e, _ in events] == ["delta", "delta", "done"]
    done = events[-1][1]
    assert done["answer"] == "入社6か月後から[1]"
    assert done["sources"][0]["manual_name"] == "rule.pdf"
    with database.get_connection() as c:
        assert c.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0] == 1


def test_stream_no_hits_returns_not_found_without_llm(client, monkeypatch):
    _fake_stream(monkeypatch, ["呼ばれないはず"])
    events = _parse_sse(client.post("/api/ask/stream", json={"question": "何か"}).text)
    assert [e for e, _ in events] == ["done"]
    assert events[0][1]["answer"] == NOT_FOUND and events[0][1]["sources"] == []


def test_stream_validation_error_is_400(client):
    assert client.post("/api/ask/stream", json={"question": "  "}).status_code == 400


def test_stream_llm_failure_midway_sends_error_event(client, monkeypatch):
    _add_manual_chunk()

    def boom(q, h, client=None):
        yield "途中"
        raise qa_service.ChatError("失敗しました")

    monkeypatch.setattr(qa_service, "_generate_answer_stream", boom)
    events = _parse_sse(client.post("/api/ask/stream", json={"question": "有給は?"}).text)
    assert [e for e, _ in events] == ["delta", "error"]
    with database.get_connection() as c:
        assert c.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0] == 0
