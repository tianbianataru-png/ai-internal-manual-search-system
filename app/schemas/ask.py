from pydantic import BaseModel


class AskIn(BaseModel):
    question: str
    manual_id: int | None = None  # 指定すると、そのマニュアルだけを検索する
    category: str | None = None  # 指定すると、その分類のマニュアルだけを検索する


class SourceOut(BaseModel):
    manual_name: str
    page: int | None = None
    text: str
    manual_id: int | None = None  # ダウンロード用(古い履歴では None)
    ref: int | None = None  # 回答文中の [1] などの番号(古い履歴では None)


class AskOut(BaseModel):
    id: int
    question: str
    answer: str
    sources: list[SourceOut]
