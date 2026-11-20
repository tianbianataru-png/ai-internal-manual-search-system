"""マニュアルの登録(検証→保存→解析→ベクトル化→DB保存)・一覧・削除。"""
import sqlite3
import uuid
from pathlib import Path

from app.chunking import split_sections
from app.config import get_settings
from app.db import vector_store
from app.db.database import get_connection
from app.parsers import ParseError, parse_file
from app.services.embedding import EmbeddingError, embed_texts


class ManualError(Exception):
    """利用者に見せてよいエラー。status_code は HTTP の応答コード。"""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def validate_upload(filename: str, data: bytes) -> str:
    """形式とサイズを検証し、拡張子(ドットなし・小文字)を返す。"""
    s = get_settings()
    ext = Path(filename or "").suffix.lower().lstrip(".")
    allowed = [e.strip() for e in s.allowed_extensions.split(",")]
    if ext not in allowed:
        raise ManualError(f"未対応のファイル形式です。対応形式: {', '.join(allowed)}")
    if not data:
        raise ManualError("空のファイルです。")
    if len(data) > s.max_upload_mb * 1024 * 1024:
        raise ManualError(f"ファイルサイズが上限({s.max_upload_mb}MB)を超えています。", 413)
    return ext


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d.pop("stored_path", None)
    d.pop("user_id", None)
    return d


def register_manual(filename: str, data: bytes, user_id: int) -> dict:
    """マニュアルを登録する。解析に失敗した場合も記録を残し、status='error' で返す。"""
    ext = validate_upload(filename, data)
    s = get_settings()
    s.upload_dir.mkdir(parents=True, exist_ok=True)
    stored = s.upload_dir / f"{uuid.uuid4().hex}.{ext}"
    stored.write_bytes(data)
    display_name = Path(filename).name

    with get_connection() as conn:
        manual_id = conn.execute(
            "INSERT INTO manuals(user_id, filename, stored_path, file_type, file_size) VALUES (?,?,?,?,?)",
            (user_id, display_name, str(stored), ext, len(data)),
        ).lastrowid

    status, chunk_count, error = "ready", 0, None
    try:
        chunks = split_sections(parse_file(stored))
        texts = [c.text for c in chunks]
        metas = []
        for c in chunks:
            m = {"filename": display_name}
            if c.page is not None:  # Chroma は None を保存できない
                m["page"] = c.page
            metas.append(m)
        vector_store.add_chunks(manual_id, user_id, texts, embed_texts(texts), metas)
        chunk_count = len(chunks)
    except (ParseError, EmbeddingError) as e:
        status, error = "error", str(e)
    except Exception:
        status, error = "error", "予期しないエラーが発生しました。"
    if status == "error":
        vector_store.delete_manual(manual_id)  # 中途半端なデータを残さない

    with get_connection() as conn:
        conn.execute(
            "UPDATE manuals SET status=?, chunk_count=?, error_message=? WHERE id=?",
            (status, chunk_count, error, manual_id),
        )
        row = conn.execute("SELECT * FROM manuals WHERE id=?", (manual_id,)).fetchone()
    return _row_to_dict(row)


def list_manuals(user_id: int) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM manuals WHERE user_id=? ORDER BY id DESC", (user_id,)
        ).fetchall()
    return [_row_to_dict(r) for r in rows]


def delete_manual(manual_id: int, user_id: int) -> None:
    """ファイル・検索データ・DB記録をすべて削除する。"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT stored_path FROM manuals WHERE id=? AND user_id=?", (manual_id, user_id)
        ).fetchone()
        if row is None:
            raise ManualError("マニュアルが見つかりません。", 404)
        vector_store.delete_manual(manual_id)
        conn.execute("DELETE FROM manuals WHERE id=?", (manual_id,))
    Path(row["stored_path"]).unlink(missing_ok=True)
