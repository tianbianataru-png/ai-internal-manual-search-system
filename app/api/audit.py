"""操作ログの閲覧(管理者のみ)。"""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import require_admin
from app.schemas.audit import AuditLogOut
from app.services import audit_service

router = APIRouter(prefix="/api/audit", tags=["audit"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[AuditLogOut])
def list_logs(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), action: str | None = None):
    if action and action not in audit_service.ACTIONS:
        raise HTTPException(status_code=400, detail="操作の種類が正しくありません。")
    return audit_service.list_logs(limit, offset, action)
