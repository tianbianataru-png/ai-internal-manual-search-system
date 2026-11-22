from pydantic import BaseModel


class AskIn(BaseModel):
    question: str
    manual_id: int | None = None  # 指定すると、そのマニュアルだけを検索する


class SourceOut(BaseModel):
    manual_name: str
    page: int | None = None
    text: str
    ref: int | None = None  # 回答文中の [1] などの番号(古い履歴では None)


class AskOut(BaseModel):
    id: int
    question: str
    answer: str
    sources: list[SourceOut]
