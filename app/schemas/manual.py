from pydantic import BaseModel


class ManualOut(BaseModel):
    id: int
    filename: str
    file_type: str
    file_size: int
    status: str  # ready / error
    chunk_count: int
    error_message: str | None = None
    created_at: str
    updated_at: str | None = None  # 差し替えた日時(未更新ならなし)
    category: str = ""  # 分類(空なら未分類)


class CategoryIn(BaseModel):
    category: str = ""
