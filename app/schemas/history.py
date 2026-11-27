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


class DailyCount(BaseModel):
    date: str
    count: int


class UserCount(BaseModel):
    username: str
    count: int


class Usage(BaseModel):
    total: int
    last7: int
    last30: int
    active_users30: int
    unanswered30: int
    daily: list[DailyCount]  # 直近14日(古い順・0件の日も含む)
    top_users: list[UserCount]  # 直近30日の質問が多い順(最大5人)


class ManualUsage(BaseModel):
    manual_id: int
    manual_name: str
    category: str
    total: int  # 出典にされた回答の数(累計)
    last30: int  # 直近30日
    last_cited_at: str | None  # 最後に出典にされた日時(一度もなければ None)
