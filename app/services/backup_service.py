"""バックアップと復元。

バックアップ(ZIP)の中身:
  manifest.json … 作成日時・件数
  app.db        … SQLiteの一貫したコピー(ユーザー・履歴・マニュアル情報・操作ログ)
  uploads/…     … 登録された元ファイル
  chunks.json   … 検索用データ(文章・ベクトル・出典情報)。復元時にChromaDBへ書き戻す(再計算しないのでAPI料金はかからない)
パスワードのハッシュなどの秘密を含むので、取り扱いに注意すること。
"""
import json
import shutil
import sqlite3
import time
import zipfile
from datetime import datetime
from pathlib import Path

from app.config import get_settings
from app.db import vector_store
from app.db.database import get_connection

FORMAT_VERSION = 1
BATCH = 500


class BackupError(Exception):
    """利用者に見せてよいエラー。"""


def _export_chunks(path: Path) -> int:
    col = vector_store.get_collection()
    total = col.count()
    out = {"ids": [], "documents": [], "metadatas": [], "embeddings": []}
    offset = 0
    while offset < total:
        got = col.get(limit=BATCH, offset=offset, include=["documents", "metadatas", "embeddings"])
        if not got["ids"]:
            break
        out["ids"] += got["ids"]
        out["documents"] += got["documents"]
        out["metadatas"] += got["metadatas"]
        out["embeddings"] += [[float(x) for x in e] for e in got["embeddings"]]
        offset += len(got["ids"])
    path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return len(out["ids"])


def create_backup(dest: Path) -> dict:
    """バックアップZIPを dest に作る。作業用の一時ファイルは dest と同じフォルダに作り、終わったら消す。"""
    s = get_settings()
    work = dest.parent / f"{dest.stem}_work"
    work.mkdir(parents=True, exist_ok=True)
    try:
        db_copy = work / "app.db"
        src = sqlite3.connect(s.sqlite_path)
        try:  # 使用中でも壊れないよう、SQLite標準のバックアップ機能でコピーする
            dst = sqlite3.connect(db_copy)
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        chunks = _export_chunks(work / "chunks.json")
        files = [p for p in s.upload_dir.glob("*") if p.is_file()] if s.upload_dir.exists() else []
        manifest = {
            "format": FORMAT_VERSION,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "files": len(files),
            "chunks": chunks,
        }
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            z.write(db_copy, "app.db")
            z.write(work / "chunks.json", "chunks.json")
            for p in files:
                z.write(p, f"uploads/{p.name}")
        return manifest
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _safe_members(z: zipfile.ZipFile) -> None:
    """ZIPの中に、保存先の外へ書き出すパス(../ や絶対パス)がないか確認する。"""
    for name in z.namelist():
        p = Path(name)
        if p.is_absolute() or ".." in p.parts or name.startswith(("/", "\\")):
            raise BackupError(f"バックアップの中に不正なパスがあります: {name}")


def restore_backup(zip_path: Path) -> dict:
    """バックアップから復元する。サーバーを止めた状態で実行すること。
    今あるデータは削除せず、「…before-restore-日時」という名前に変えて残す。"""
    s = get_settings()
    if not zipfile.is_zipfile(zip_path):
        raise BackupError("バックアップファイル(ZIP)として読み込めません。")
    with zipfile.ZipFile(zip_path) as z:
        _safe_members(z)
        names = set(z.namelist())
        if not {"manifest.json", "app.db", "chunks.json"} <= names:
            raise BackupError("バックアップの形式が正しくありません。")
        manifest = json.loads(z.read("manifest.json"))
        if manifest.get("format") != FORMAT_VERSION:
            raise BackupError("このバックアップは、対応していない形式です。")

        stamp = time.strftime("%Y%m%d-%H%M%S")
        vector_store.close_client()  # 開いているChromaの接続を閉じる(フォルダを移動できるように)
        for p in (s.sqlite_path, s.chroma_dir, s.upload_dir):
            if p.exists():
                p.rename(p.with_name(f"{p.name}.before-restore-{stamp}"))

        s.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        s.upload_dir.mkdir(parents=True, exist_ok=True)
        s.sqlite_path.write_bytes(z.read("app.db"))
        for name in names:
            if name.startswith("uploads/") and not name.endswith("/"):
                (s.upload_dir / Path(name).name).write_bytes(z.read(name))
        chunks = json.loads(z.read("chunks.json").decode("utf-8"))

    # 元ファイルの保存場所は環境ごとに違うので、今のフォルダに合わせて書き直す
    with get_connection() as conn:
        for row in conn.execute("SELECT id, stored_path FROM manuals").fetchall():
            conn.execute("UPDATE manuals SET stored_path=? WHERE id=?",
                         (str(s.upload_dir / Path(row["stored_path"]).name), row["id"]))
        conn.execute("DELETE FROM sessions")  # ログイン中の状態は引き継がない

    col = vector_store.get_collection()
    n = len(chunks["ids"])
    for i in range(0, n, BATCH):
        sl = slice(i, i + BATCH)
        col.add(ids=chunks["ids"][sl], documents=chunks["documents"][sl],
                metadatas=chunks["metadatas"][sl], embeddings=chunks["embeddings"][sl])
    return {**manifest, "restored_chunks": n}
