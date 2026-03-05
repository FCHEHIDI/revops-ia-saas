import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_tenant_a_cannot_access_tenant_b_sessions():
    resp = client.get("/api/v1/sessions/?user=tenant_B", headers={"Authorization": "Bearer tenant_A_jwt"})
    assert resp.status_code in [403, 404, 401]

def test_tenant_a_cannot_list_documents_tenant_b():
    resp = client.get("/api/v1/documents/?tenant=tenant_B", headers={"Authorization": "Bearer tenant_A_jwt"})
    assert resp.status_code in [403, 404, 401]
