"""ログイン確認・権限確認(各APIが Depends で使う)。"""
from fastapi import Depends, HTTPException, Request

from app.services import auth_service

COOKIE_NAME = "session"


def get_current_user(request: Request) -> dict:
    user = auth_service.get_user_by_token(request.cookies.get(COOKIE_NAME))
    if user is None:
        raise HTTPException(status_code=401, detail="ログインが必要です。")
    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="この操作には管理者権限が必要です。")
    return user
