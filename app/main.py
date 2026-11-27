"""アプリの起動入口。"""
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.ask import router as ask_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.backup import router as backup_router
from app.api.feedback import router as feedback_router
from app.api.history import router as history_router
from app.api.manuals import router as manuals_router
from app.api.users import router as users_router
from app.config import get_settings
from app.db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # 起動時にテーブルを用意する
    yield


FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

app = FastAPI(title="AI社内マニュアル検索システム", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(manuals_router)
app.include_router(ask_router)
app.include_router(history_router)
app.include_router(feedback_router)
app.include_router(audit_router)
app.include_router(backup_router)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """画面(HTML)を返す。"""
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health")
def health() -> dict:
    """動作確認用。サーバーが起動していれば ok を返す。"""
    settings = get_settings()
    return {
        "status": "ok",
        "chat_model": settings.chat_model,
        "embedding_model": settings.embedding_model,
        "openai_api_key_set": bool(settings.openai_api_key),
    }
