from fastapi import APIRouter, HTTPException, UploadFile

from app.config import get_settings
from app.schemas.manual import ManualOut
from app.services import manual_service
from app.services.manual_service import ManualError

router = APIRouter(prefix="/api/manuals", tags=["manuals"])


def _http(e: ManualError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=str(e))


@router.post("", response_model=ManualOut, status_code=201)
async def upload_manual(file: UploadFile):
    """マニュアルを登録する。解析に失敗した場合は status='error' と理由を返す。"""
    s = get_settings()
    data = await file.read(s.max_upload_mb * 1024 * 1024 + 1)  # 上限+1バイトまでしか読まない
    try:
        return manual_service.register_manual(file.filename or "", data, s.default_user_id)
    except ManualError as e:
        raise _http(e)


@router.get("", response_model=list[ManualOut])
def list_manuals():
    return manual_service.list_manuals(get_settings().default_user_id)


@router.delete("/{manual_id}", status_code=204)
def delete_manual(manual_id: int):
    try:
        manual_service.delete_manual(manual_id, get_settings().default_user_id)
    except ManualError as e:
        raise _http(e)
