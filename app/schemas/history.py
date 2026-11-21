from pydantic import BaseModel

from app.schemas.ask import SourceOut


class HistorySummary(BaseModel):
    """一覧用(出典の本文は含めない)。"""

    id: int
    question: str
    answer: str
    source_count: int
    created_at: str


class HistoryDetail(BaseModel):
    id: int
    question: str
    answer: str
    sources: list[SourceOut]
    created_at: str
