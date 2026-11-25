"""ChromaDB(ベクトルDB)への接続と基本操作。

埋め込みベクトルは呼び出し側(ステップ5)で作って渡す。
ここでは保存・検索・削除だけを担当する。
"""
import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection

from app.config import get_settings

COLLECTION_NAME = "manual_chunks"

_client: ClientAPI | None = None


def get_client() -> ClientAPI:
    global _client
    if _client is None:
        path = get_settings().chroma_dir
        path.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(path))
    return _client


def get_collection() -> Collection:
    # cosine 距離を使う(文章の意味の近さを測るのに一般的)
    return get_client().get_or_create_collection(
        name=COLLECTION_NAME, metadata={"hnsw:space": "cosine"}
    )


def add_chunks(
    manual_id: int,
    user_id: int,
    texts: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict] | None = None,
) -> None:
    """マニュアル1件分のチャンクを保存する。"""
    if not texts:
        return
    metas = []
    for i in range(len(texts)):
        m = dict(metadatas[i]) if metadatas else {}
        m.update({"manual_id": manual_id, "user_id": user_id, "chunk_index": i})
        metas.append(m)
    get_collection().add(
        ids=[f"{manual_id}-{i}" for i in range(len(texts))],
        documents=texts,
        embeddings=embeddings,
        metadatas=metas,
    )


def replace_chunks(
    manual_id: int,
    user_id: int,
    texts: list[str],
    embeddings: list[list[float]],
    metadatas: list[dict],
) -> None:
    """マニュアル1件分のチャンクを新しい内容に差し替える。

    先に新しいチャンクを上書き保存し、そのあとで余った古いチャンクだけを消す。
    途中で失敗しても、古い内容がまるごと消えることはない。
    """
    metas = []
    for i in range(len(texts)):
        m = dict(metadatas[i])
        m.update({"manual_id": manual_id, "user_id": user_id, "chunk_index": i})
        metas.append(m)
    new_ids = [f"{manual_id}-{i}" for i in range(len(texts))]
    col = get_collection()
    col.upsert(ids=new_ids, documents=texts, embeddings=embeddings, metadatas=metas)
    stale = [i for i in col.get(where={"manual_id": manual_id}, include=[])["ids"] if i not in new_ids]
    if stale:
        col.delete(ids=stale)


def search(
    query_embedding: list[float],
    user_id: int | None = None,
    top_k: int = 5,
    manual_id: int | None = None,
    manual_ids: list[int] | None = None,
) -> list[dict]:
    """質問ベクトルに近いチャンクを返す。user_id(登録者)・manual_id・manual_ids(複数)で絞り込める。"""
    conds = []
    if user_id is not None:
        conds.append({"user_id": user_id})
    if manual_id is not None:
        conds.append({"manual_id": manual_id})
    if manual_ids is not None:
        conds.append({"manual_id": {"$in": manual_ids}})
    where = None if not conds else conds[0] if len(conds) == 1 else {"$and": conds}
    res = get_collection().query(
        query_embeddings=[query_embedding], n_results=top_k, where=where
    )
    return [
        {"text": doc, "metadata": meta, "distance": dist}
        for doc, meta, dist in zip(
            res["documents"][0], res["metadatas"][0], res["distances"][0]
        )
    ]


def delete_manual(manual_id: int) -> None:
    """マニュアル1件分のチャンクをすべて削除する。"""
    get_collection().delete(where={"manual_id": manual_id})


def count() -> int:
    return get_collection().count()
