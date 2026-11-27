from pydantic import BaseModel


class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    role: str  # admin / user
    created_at: str
    disabled: bool = False  # 管理者が停止中
    locked: bool = False  # ログイン失敗でロック中


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "user"


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


class PasswordIn(BaseModel):
    password: str


class DisabledIn(BaseModel):
    disabled: bool
