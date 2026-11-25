from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import get_current_user, require_admin
from app.config import get_settings
from app.schemas.manual import CategoryIn, ManualOut
from app.services import audit_service, manual_service
from app.services.manual_service import ManualError

router = APIRouter(prefix="/api/manuals", tags=["manuals"])


def _http(e: ManualError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=str(e))


@router.post("", response_model=ManualOut, status_code=201)
async def upload_manual(
    file: UploadFile, request: Request, category: str = Form(""), admin: dict = Depends(require_admin)
):
    """マニュアルを登録する。解析に失敗した場合は status='error' と理由を返す。"""
    s = get_settings()
    data = await file.read(s.max_upload_mb * 1024 * 1024 + 1)  # 上限+1バイトまでしか読まない
    try:
        manual = manual_service.register_manual(file.filename or "", data, admin["id"], category)
    except ManualError as e:
        raise _http(e)
    audit_service.record("manual_upload", request, user=admin, detail=manual["filename"])
    return manual


@router.put("/{manual_id}", response_model=ManualOut)
async def update_manual(manual_id: int, file: UploadFile, request: Request, admin: dict = Depends(require_admin)):
    """登録済みマニュアルを新しいファイルで差し替える。失敗した場合、元のマニュアルはそのまま残る。"""
    s = get_settings()
    data = await file.read(s.max_upload_mb * 1024 * 1024 + 1)
    try:
        manual, old_name = manual_service.update_manual(manual_id, file.filename or "", data, admin["id"])
    except ManualError as e:
        raise _http(e)
    detail = manual["filename"] if old_name == manual["filename"] else f"{old_name} → {manual['filename']}"
    audit_service.record("manual_update", request, user=admin, detail=detail)
    return manual


@router.put("/{manual_id}/category", status_code=204)
def change_category(manual_id: int, body: CategoryIn, request: Request, admin: dict = Depends(require_admin)):
    """マニュアルの分類を変更する(空文字で未分類)。"""
    try:
        name, category = manual_service.set_category(manual_id, body.category)
    except ManualError as e:
        raise _http(e)
    audit_service.record("manual_category", request, user=admin, detail=f"{name} → {category or '未分類'}")


@router.get("", response_model=list[ManualOut], dependencies=[Depends(get_current_user)])
def list_manuals():
    return manual_service.list_manuals()


@router.get("/{manual_id}/file", dependencies=[Depends(get_current_user)])
def download_manual(manual_id: int):
    """登録されている元のファイルをダウンロードする(ログイン済みなら誰でも可。マニュアルは全員共通)。"""
    try:
        path, name = manual_service.get_file(manual_id)
    except ManualError as e:
        raise _http(e)
    return FileResponse(path, filename=name)


@router.delete("/{manual_id}", status_code=204)
def delete_manual(manual_id: int, request: Request, admin: dict = Depends(require_admin)):
    name = next((m["filename"] for m in manual_service.list_manuals() if m["id"] == manual_id), f"ID {manual_id}")
    try:
        manual_service.delete_manual(manual_id)
    except ManualError as e:
        raise _http(e)
    audit_service.record("manual_delete", request, user=admin, detail=name)
