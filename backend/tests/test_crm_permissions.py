import pytest
from backend.app.crm.permissions import verify_internal_api_key, extract_tenant
from fastapi import HTTPException
import uuid

def test_verify_internal_api_key():
    with pytest.raises(HTTPException):
        verify_internal_api_key("wrong-key")
    # Should pass with correct key (from env)

@pytest.mark.parametrize("tenant_id,should_pass", [
    (str(uuid.uuid4()), True),
    ("not-a-uuid", False)
])
def test_extract_tenant(tenant_id, should_pass):
    if should_pass:
        assert extract_tenant(tenant_id)
    else:
        with pytest.raises(HTTPException):
            extract_tenant(tenant_id)
