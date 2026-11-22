from fastapi.testclient import TestClient

from app.main import app
from app.services import auth_service

PASSWORD = "password-123"


def make_client(username: str = "admin", role: str = "admin") -> TestClient:
    """ユーザーを作ってログイン済みのクライアントを返す(DBは初期化済みであること)。"""
    auth_service._failures.clear()
    auth_service.create_user(username, PASSWORD, role)
    client = TestClient(app)
    r = client.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200
    return client
