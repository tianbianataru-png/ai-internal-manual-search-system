"""ユーザー管理(管理者のみ)。"""
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import require_admin
from app.schemas.auth import PasswordIn, UserCreate, UserOut
from app.services import auth_service
from app.services.auth_service import AuthError

router = APIRouter(prefix="/api/users", tags=["users"], dependencies=[Depends(require_admin)])


def _http(e: AuthError) -> HTTPException:
    return HTTPException(status_code=e.status_code, detail=str(e))


@router.get("", response_model=list[UserOut])
def list_users():
    return auth_service.list_users()


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate):
    try:
        return auth_service.create_user(body.username, body.password, body.role)
    except AuthError as e:
        raise _http(e)


@router.put("/{user_id}/password", status_code=204)
def reset_password(user_id: int, body: PasswordIn):
    try:
        auth_service.set_password(user_id, body.password)
    except AuthError as e:
        raise _http(e)


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, admin: dict = Depends(require_admin)):
    try:
        auth_service.delete_user(user_id, admin["id"])
    except AuthError as e:
        raise _http(e)
