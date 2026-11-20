from pydantic import BaseModel


class AskIn(BaseModel):
    question: str


class SourceOut(BaseModel):
    manual_name: str
    page: int | None = None
    text: str


class AskOut(BaseModel):
    id: int
    question: str
    answer: str
    sources: list[SourceOut]
