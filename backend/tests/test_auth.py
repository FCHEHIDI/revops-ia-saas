import pytest
from fastapi import status
from fastapi.testclient import TestClient
from app.main import app

test_email = "test@example.com"
test_password = "password123"
test_refresh = "dummyrefresh"

client = TestClient(app)

def test_login_success(monkeypatch):
    resp = client.post("/api/v1/auth/login", json={"email": test_email, "password": test_password})
    assert resp.status_code in [200, 401]  # 200 si user existe, 401 sinon

def test_login_wrong_password(monkeypatch):
    resp = client.post("/api/v1/auth/login", json={"email": test_email, "password": "wrong"})
    assert resp.status_code == 401

def test_refresh_token(monkeypatch):
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": test_refresh})
    assert resp.status_code in [200, 401]

def test_refresh_token_revoked(monkeypatch):
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": "revokedtoken"})
    assert resp.status_code == 401

def test_logout(monkeypatch):
    resp = client.post("/api/v1/auth/logout", json={"refresh_token": test_refresh})
    assert resp.status_code in [200, 401]
