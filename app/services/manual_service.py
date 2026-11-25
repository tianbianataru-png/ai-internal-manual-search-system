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


def _chunk_and_embed(stored: Path, display_name: str) -> tuple[list[str], list[list[float]], list[dict]]:
    """ファイルを解析して分割し、ベクトル化する。(texts, embeddings, metadatas) を返す。"""
    chunks = split_sections(parse_file(stored))
    texts = [c.text for c in chunks]
    metas = []
    for c in chunks:
        m = {"filename": display_name}
        if c.page is not None:  # Chroma は None を保存できない
            m["page"] = c.page
        metas.append(m)
    return texts, embed_texts(texts), metas


def register_manual(filename: str, data: bytes, user_id: int) -> dict:
    """マニュアルを登録する(user_id は登録した管理者)。解析に失敗した場合も記録を残し、status='error' で返す。"""
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
        texts, embeddings, metas = _chunk_and_embed(stored, display_name)
        vector_store.add_chunks(manual_id, user_id, texts, embeddings, metas)
        chunk_count = len(texts)
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


def _remove_file(path) -> None:
    """ファイルを消す。消せなくても(使用中など)本来の処理は失敗にしない。"""
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def update_manual(manual_id: int, filename: str, data: bytes, user_id: int) -> tuple[dict, str]:
    """登録済みマニュアルを新しいファイルで差し替える(IDはそのまま)。

    新しいファイルの解析とベクトル化が成功してから入れ替えるので、失敗しても元のマニュアルは変わらない。
    解析に失敗して「エラー」状態になっていたマニュアルの再登録にも使える。
    戻り値は (更新後の情報, 差し替え前のファイル名)。
    """
    ext = validate_upload(filename, data)
    with get_connection() as conn:
        old = conn.execute("SELECT filename, stored_path FROM manuals WHERE id=?", (manual_id,)).fetchone()
    if old is None:
        raise ManualError("マニュアルが見つかりません。", 404)

    s = get_settings()
    s.upload_dir.mkdir(parents=True, exist_ok=True)
    stored = s.upload_dir / f"{uuid.uuid4().hex}.{ext}"
    stored.write_bytes(data)
    display_name = Path(filename).name
    try:
        try:
            texts, embeddings, metas = _chunk_and_embed(stored, display_name)
        except ParseError as e:
            raise ManualError(f"ファイルを解析できませんでした: {e}")
        except EmbeddingError as e:
            raise ManualError(str(e), 502)
        if not texts:
            raise ManualError("ファイルから文章を取り出せませんでした。")
        try:
            vector_store.replace_chunks(manual_id, user_id, texts, embeddings, metas)
        except Exception:
            raise ManualError("検索データの更新に失敗しました。もう一度お試しください。", 500)
        with get_connection() as conn:
            conn.execute(
                "UPDATE manuals SET user_id=?, filename=?, stored_path=?, file_type=?, file_size=?,"
                " status='ready', chunk_count=?, error_message=NULL, updated_at=datetime('now','localtime')"
                " WHERE id=?",
                (user_id, display_name, str(stored), ext, len(data), len(texts), manual_id),
            )
            row = conn.execute("SELECT * FROM manuals WHERE id=?", (manual_id,)).fetchone()
    except Exception:
        _remove_file(stored)  # 失敗したら、保存した新ファイルは残さない
        raise
    _remove_file(old["stored_path"])
    return _row_to_dict(row), old["filename"]


def list_manuals() -> list[dict]:
    """マニュアルは全社共通。全員が閲覧でき、登録・削除は管理者だけ(API側で制限)。"""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM manuals ORDER BY id DESC").fetchall()
    return [_row_to_dict(r) for r in rows]


def delete_manual(manual_id: int) -> None:
    """ファイル・検索データ・DB記録をすべて削除する。"""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT stored_path FROM manuals WHERE id=?", (manual_id,)
        ).fetchone()
        if row is None:
            raise ManualError("マニュアルが見つかりません。", 404)
        vector_store.delete_manual(manual_id)
        conn.execute("DELETE FROM manuals WHERE id=?", (manual_id,))
    Path(row["stored_path"]).unlink(missing_ok=True)
