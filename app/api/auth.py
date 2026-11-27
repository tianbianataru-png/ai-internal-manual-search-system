from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.deps import COOKIE_NAME, get_current_user
from app.config import get_settings
from app.schemas.auth import ChangePasswordIn, LoginIn, UserOut
from app.services import audit_service, auth_service
from app.services.auth_service import AuthError

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _set_session_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=s.session_hours * 3600,
        httponly=True,  # JavaScriptからは読めない
        samesite="lax",  # 他サイトからの送信ではCookieを送らない(CSRF対策)
        secure=s.cookie_secure,
    )


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response):
    try:
        token, user = auth_service.login(body.username, body.password)
    except AuthError as e:
        audit_service.record("login_failed", request, username=body.username.strip(), detail=str(e))
        if isinstance(e, auth_service.AccountLocked):
            audit_service.record("account_locked", request, username=body.username.strip(),
                                 detail=f"連続{auth_service.LOCK_AFTER}回失敗したため{auth_service.LOCK_SECONDS // 60}分ロック")
        raise HTTPException(status_code=e.status_code, detail=str(e))
    audit_service.record("login", request, user=user)
    _set_session_cookie(response, token)
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME)
    user = auth_service.get_user_by_token(token)
    auth_service.logout(token)
    if user:
        audit_service.record("logout", request, user=user)
    response.delete_cookie(COOKIE_NAME)


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(get_current_user)):
    return user


@router.put("/password", status_code=204)
def change_password(body: ChangePasswordIn, request: Request, response: Response,
                    user: dict = Depends(get_current_user)):
    """自分のパスワードを変更する。この端末はログインしたまま、他の端末はログアウトされる。"""
    try:
        token = auth_service.change_own_password(user["id"], body.current_password, body.new_password)
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    audit_service.record("password_change", request, user=user)
    _set_session_cookie(response, token)
