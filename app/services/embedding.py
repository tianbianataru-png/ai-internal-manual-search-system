"""OpenAI の Embedding API で文章をベクトルに変換する。"""
from openai import OpenAI

from app.config import get_settings

# 1回のAPI呼び出しで送る文章の最大数(上限対策)
BATCH_SIZE = 100


class EmbeddingError(Exception):
    """ベクトル化に失敗したとき(メッセージは利用者に見せてよい)。"""


def _get_client() -> OpenAI:
    key = get_settings().openai_api_key
    if not key:
        raise EmbeddingError("OpenAI APIキーが設定されていません。.env の OPENAI_API_KEY を確認してください。")
    return OpenAI(api_key=key)


def embed_texts(texts: list[str], client: OpenAI | None = None) -> list[list[float]]:
    """文章のリストを、同じ順序のベクトルのリストにして返す。"""
    if not texts:
        return []
    client = client or _get_client()
    model = get_settings().embedding_model
    vectors: list[list[float]] = []
    try:
        for i in range(0, len(texts), BATCH_SIZE):
            res = client.embeddings.create(model=model, input=texts[i : i + BATCH_SIZE])
            vectors.extend(d.embedding for d in sorted(res.data, key=lambda d: d.index))
    except EmbeddingError:
        raise
    except Exception as e:
        raise EmbeddingError(f"ベクトル化に失敗しました({type(e).__name__})。時間をおいて再度お試しください。") from e
    return vectors


def embed_query(text: str, client: OpenAI | None = None) -> list[float]:
    """質問文1件をベクトル化する。"""
    return embed_texts([text], client)[0]
