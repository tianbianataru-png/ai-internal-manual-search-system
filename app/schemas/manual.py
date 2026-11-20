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
