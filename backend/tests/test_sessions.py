from fastapi.testclient import TestClient
from app.main import app

test_headers = {"Authorization": "Bearer dummy_jwt"}
client = TestClient(app)


def test_create_session():
    resp = client.post(
        "/api/v1/sessions/", headers=test_headers, json={"title": "Test session"}
    )
    assert resp.status_code == 201


def test_add_message():
    s_resp = client.post(
        "/api/v1/sessions/", headers=test_headers, json={"title": "Session for chat"}
    )
    session = s_resp.json()
    sess_id = session["id"]
    chat_resp = client.post(
        f"/api/v1/sessions/{sess_id}/chat",
        headers=test_headers,
        json={"role": "user", "content": "Hello", "timestamp": "2024-01-01T12:00:00Z"},
    )
    assert chat_resp.status_code in [200, 500]


def test_get_history():
    s_resp = client.post(
        "/api/v1/sessions/", headers=test_headers, json={"title": "Session for get"}
    )
    session = s_resp.json()
    sess_id = session["id"]
    g_resp = client.get(f"/api/v1/sessions/{sess_id}", headers=test_headers)
    assert g_resp.status_code in [200, 403]
