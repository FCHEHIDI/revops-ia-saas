from typing import Iterable

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "admin": [
        "crm:accounts:read",
        "crm:accounts:write",
        "crm:contacts:read",
        "crm:contacts:write",
        "crm:deals:read",
        "crm:deals:write",
        "analytics:view",
        "billing:view",
        "settings:manage",
        "users:manage",
    ],
    "revops": [
        "crm:accounts:read",
        "crm:deals:read",
        "analytics:view",
        "billing:view",
    ],
    "sales": [
        "crm:accounts:read",
        "crm:accounts:write",
        "crm:contacts:read",
        "crm:contacts:write",
        "crm:deals:read",
        "crm:deals:write",
    ],
    "customer_success": [
        "crm:accounts:read",
        "crm:contacts:read",
        "crm:deals:read",
        "crm:contacts:write",
    ],
}


def permissions_for_roles(roles: Iterable[str]) -> list[str]:
    """Build a normalized list of permissions from one or more roles."""
    permissions: list[str] = []
    for role in roles:
        permissions.extend(ROLE_PERMISSIONS.get(role, []))
    return sorted(set(permissions))
