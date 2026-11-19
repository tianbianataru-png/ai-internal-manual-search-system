"""アプリの起動入口。"""
from fastapi import FastAPI

from app.config import get_settings

app = FastAPI(title="AI社内マニュアル検索システム")


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
