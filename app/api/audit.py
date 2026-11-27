"""操作ログの閲覧(管理者のみ)。"""
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query

from fastapi.responses import Response

from app.api.deps import require_admin
from app.core.csv_util import cell
from app.schemas.audit import AuditLogOut
from app.services import audit_service

router = APIRouter(prefix="/api/audit", tags=["audit"], dependencies=[Depends(require_admin)])


@router.get("", response_model=list[AuditLogOut])
def list_logs(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), action: str | None = None):
    if action and action not in audit_service.ACTIONS:
        raise HTTPException(status_code=400, detail="操作の種類が正しくありません。")
    return audit_service.list_logs(limit, offset, action)


@router.get("/export.csv")
def export_logs(action: str | None = None):
    """操作ログをCSVでダウンロード(種類の絞り込み可。新しい順で最大5000件)。"""
    if action and action not in audit_service.ACTIONS:
        raise HTTPException(status_code=400, detail="操作の種類が正しくありません。")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["日時", "操作", "ユーザー", "内容", "IPアドレス"])
    for r in audit_service.list_logs(5000, 0, action):
        w.writerow([r["created_at"], r["action"], cell(r["username"]), cell(r["detail"]), r["ip"]])
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=audit.csv"})
