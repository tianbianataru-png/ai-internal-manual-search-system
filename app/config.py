"""設定の読み込み。.env の値をここ経由で使う。"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    openai_api_key: str = ""
    chat_model: str = "gpt-5-mini"
    embedding_model: str = "text-embedding-3-small"

    data_dir: Path = BASE_DIR / "data"
    sqlite_path: Path = BASE_DIR / "data" / "app.db"
    chroma_dir: Path = BASE_DIR / "data" / "chroma"
    upload_dir: Path = BASE_DIR / "data" / "uploads"

    max_upload_mb: int = 20
    allowed_extensions: str = "pdf,docx,txt"

    # ログイン
    session_hours: int = 8
    cookie_secure: bool = False  # HTTPSで公開するときは true にする


@lru_cache
def get_settings() -> Settings:
    return Settings()
