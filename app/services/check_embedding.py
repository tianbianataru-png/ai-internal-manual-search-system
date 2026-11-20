"""Embedding の実動作確認。実行: python -m app.services.check_embedding"""
import math

from app.services.embedding import EmbeddingError, embed_texts

try:
    v = embed_texts(["有給休暇の申請方法", "年次休暇を取るには", "経費精算の手順"])
except EmbeddingError as e:
    print("失敗:", e)
    raise SystemExit(1)


def cos(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.hypot(*a) * math.hypot(*b))


print("ベクトルの次元数:", len(v[0]))
print("類似(有給 vs 年次休暇):", round(cos(v[0], v[1]), 3))
print("無関係(有給 vs 経費):", round(cos(v[0], v[2]), 3))
