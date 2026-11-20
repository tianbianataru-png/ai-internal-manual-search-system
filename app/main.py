"""アプリの起動入口。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.ask import router as ask_router
from app.api.manuals import router as manuals_router
from app.config import get_settings
from app.db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # 起動時にテーブルを用意する
    yield


app = FastAPI(title="AI社内マニュアル検索システム", lifespan=lifespan)
app.include_router(manuals_router)
app.include_router(ask_router)


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
