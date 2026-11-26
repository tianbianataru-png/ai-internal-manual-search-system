from typing import Literal

from pydantic import BaseModel

from app.schemas.ask import SourceOut


class HistorySummary(BaseModel):
    """一覧用(出典の本文は含めない)。"""

    id: int
    question: str
    answer: str
    source_count: int
    rating: Literal["good", "bad"] | None = None
    created_at: str


class HistoryDetail(BaseModel):
    id: int
    question: str
    answer: str
    sources: list[SourceOut]
    rating: Literal["good", "bad"] | None = None
    created_at: str


class RatingIn(BaseModel):
    rating: Literal["good", "bad"] | None  # None で評価を取り消す


class BadAnswer(BaseModel):
    id: int
    username: str
    question: str
    answer: str
    created_at: str


class UnansweredItem(BaseModel):
    id: int
    username: str
    question: str
    created_at: str


class Unanswered(BaseModel):
    total: int
    items: list[UnansweredItem]


class ManualFeedback(BaseModel):
    manual_name: str
    good: int
    bad: int


class FeedbackSummary(BaseModel):
    total: int
    good: int
    bad: int
    unrated: int
    recent_bad: list[BadAnswer]
    by_manual: list[ManualFeedback]
