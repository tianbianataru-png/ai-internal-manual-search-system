"""バックアップから復元するコマンド。  使い方(サーバーを止めてから): python -m app.restore_backup backup.zip"""
import sys
from pathlib import Path

from app.services.backup_service import BackupError, restore_backup


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("使い方: python -m app.restore_backup <バックアップのZIPファイル>")
        return 1
    path = Path(argv[1])
    if not path.is_file():
        print(f"ファイルが見つかりません: {path}")
        return 1
    print("サーバーを止めていることを確認してください。今あるデータは「…before-restore-日時」という名前で残ります。")
    if input("復元しますか? (yes と入力): ").strip() != "yes":
        print("中止しました。")
        return 1
    try:
        info = restore_backup(path)
    except BackupError as e:
        print(f"復元できませんでした: {e}")
        return 1
    print(f"復元しました(作成日時 {info['created_at']}・元ファイル {info['files']}件・検索データ {info['restored_chunks']}件)。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
