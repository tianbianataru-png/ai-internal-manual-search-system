from types import SimpleNamespace

import pytest

from app.services import embedding
from app.services.embedding import EmbeddingError, embed_query, embed_texts


class FakeClient:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail
        self.embeddings = SimpleNamespace(create=self._create)

    def _create(self, model, input):
        if self.fail:
            raise RuntimeError("boom")
        self.calls.append(list(input))
        # 逆順で返しても index で並べ直されることを確認する
        data = [SimpleNamespace(index=i, embedding=[float(len(t))]) for i, t in enumerate(input)]
        return SimpleNamespace(data=list(reversed(data)))


def test_order_and_batching(monkeypatch):
    monkeypatch.setattr(embedding, "BATCH_SIZE", 2)
    c = FakeClient()
    out = embed_texts(["a", "bb", "ccc", "dddd", "e"], c)
    assert out == [[1.0], [2.0], [3.0], [4.0], [1.0]]
    assert [len(x) for x in c.calls] == [2, 2, 1]


def test_empty_makes_no_call():
    assert embed_texts([], FakeClient()) == []


def test_query():
    assert embed_query("abc", FakeClient()) == [3.0]


def test_api_failure_becomes_embedding_error():
    with pytest.raises(EmbeddingError):
        embed_texts(["a"], FakeClient(fail=True))


def test_missing_key(monkeypatch):
    monkeypatch.setattr(embedding.get_settings(), "openai_api_key", "")
    with pytest.raises(EmbeddingError):
        embed_texts(["a"])
