"""ユーザー管理(管理者のみ)。"""
from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import require_admin
from app.schemas.auth import DisabledIn, PasswordIn, UserCreate, UserOut
from app.services import audit_service, auth_service
from app.services.auth_service import AuthError

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


def _http(e: AuthError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=str(e))


def _name_of(user_id: int) -> str:
    """ログに残す対象ユーザー名(削除前に調べておく)。"""
    return next((u["username"] for u in auth_service.list_users() if u["id"] == user_id), f"ID {user_id}")


@router.get("", response_model=list[UserOut])
def list_users():
    return auth_service.list_users()


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, request: Request, admin: dict = Depends(require_admin)):
    try:
        created = auth_service.create_user(body.username, body.password, body.role)
    except AuthError as e:
        raise _http(e)
    audit_service.record("user_create", request, user=admin, detail=f"{created['username']}({created['role']})")
    return created


@router.put("/{user_id}/password", status_code=204)
def reset_password(user_id: int, body: PasswordIn, request: Request, admin: dict = Depends(require_admin)):
    name = _name_of(user_id)
    try:
        auth_service.set_password(user_id, body.password)
    except AuthError as e:
        raise _http(e)
    audit_service.record("password_reset", request, user=admin, detail=name)


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, request: Request, admin: dict = Depends(require_admin)):
    name = _name_of(user_id)
    try:
        auth_service.delete_user(user_id, admin["id"])
    except AuthError as e:
        raise _http(e)
    audit_service.record("user_delete", request, user=admin, detail=name)


@router.put("/{user_id}/disabled", status_code=204)
def set_disabled(user_id: int, body: DisabledIn, request: Request, admin: dict = Depends(require_admin)):
    """ユーザーの停止/再開。停止中はログインできず、ログイン中の端末もログアウトされる。"""
    name = _name_of(user_id)
    try:
        auth_service.set_disabled(user_id, body.disabled, admin["id"])
    except AuthError as e:
        raise _http(e)
    audit_service.record("user_disable" if body.disabled else "user_enable", request, user=admin, detail=name)


@router.post("/{user_id}/unlock", status_code=204)
def unlock_user(user_id: int, request: Request, admin: dict = Depends(require_admin)):
    """ログイン失敗によるロックを解除する。"""
    name = _name_of(user_id)
    try:
        auth_service.unlock(user_id)
    except AuthError as e:
        raise _http(e)
    audit_service.record("user_unlock", request, user=admin, detail=name)
