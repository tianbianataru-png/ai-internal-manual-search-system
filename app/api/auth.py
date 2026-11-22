from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.deps import COOKIE_NAME, get_current_user
from app.config import get_settings
from app.schemas.auth import LoginIn, UserOut
from app.services import auth_service
from app.services.auth_service import AuthError

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, response: Response):
    s = get_settings()
    try:
        token, user = auth_service.login(body.username, body.password)
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=s.session_hours * 3600,
        httponly=True,  # JavaScriptからは読めない
        samesite="lax",  # 他サイトからの送信ではCookieを送らない(CSRF対策)
        secure=s.cookie_secure,
    )
    return user


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response):
    auth_service.logout(request.cookies.get(COOKIE_NAME))
    response.delete_cookie(COOKIE_NAME)


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(get_current_user)):
    return user
