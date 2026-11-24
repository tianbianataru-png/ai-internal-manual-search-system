from pydantic import BaseModel


class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    role: str  # admin / user
    created_at: str


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "user"


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


class PasswordIn(BaseModel):
    password: str
