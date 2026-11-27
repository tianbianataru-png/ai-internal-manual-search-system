"""バックアップのダウンロード(管理者のみ)。復元はサーバーを止めてコマンドで行う(README参照)。"""
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.api.deps import require_admin
from app.services import audit_service, backup_service

router = APIRouter(prefix="/api/backup", tags=["backup"])


@router.get("/download")
def download_backup(request: Request, admin: dict = Depends(require_admin)):
    """DB・元ファイル・検索データをまとめたZIPを作ってダウンロードさせる。"""
    tmp = Path(tempfile.mkdtemp(prefix="backup_"))
    name = f"backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.zip"
    try:
        manifest = backup_service.create_backup(tmp / name)
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise HTTPException(status_code=500, detail="バックアップの作成に失敗しました。")
    audit_service.record("backup", request, user=admin, detail=f"元ファイル{manifest['files']}件・検索データ{manifest['chunks']}件")
    return FileResponse(tmp / name, media_type="application/zip", filename=name,
                        background=BackgroundTask(shutil.rmtree, tmp, ignore_errors=True))
