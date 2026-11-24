from pydantic import BaseModel


class AuditLogOut(BaseModel):
    id: int
    username: str
    action: str
    detail: str
    ip: str
    created_at: str
