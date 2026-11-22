"""最初の管理者を作るコマンド。  使い方: python -m app.create_admin"""
import getpass
import sys

from app.db.database import init_db
from app.services.auth_service import AuthError, create_user


def main() -> int:
    init_db()
    username = input("管理者のユーザー名: ").strip()
    password = getpass.getpass("パスワード(8文字以上): ")
    if password != getpass.getpass("パスワード(確認): "):
        print("パスワードが一致しません。")
        return 1
    try:
        user = create_user(username, password, "admin")
    except AuthError as e:
        print(f"作成できませんでした: {e}")
        return 1
    print(f"管理者「{user['username']}」を作成しました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
