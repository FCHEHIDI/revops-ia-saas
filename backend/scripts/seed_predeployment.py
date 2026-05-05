#!/usr/bin/env python3
"""Seed script for predeployment mock client profiles.

This script creates a minimal set of organizations, users, and accounts for
predeployment smoke tests and multi-tenant validation.

Usage:
    cd backend
    python scripts/seed_predeployment.py

It is idempotent: existing orgs, users, and accounts are preserved.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.auth.roles import permissions_for_roles
from app.auth.service import get_password_hash
from app.crm.models import Account
from app.models.organization import Organization
from app.models.user import User

DATABASE_URL = os.environ["DATABASE_URL"]
MOCK_PASSWORD = "acme1234"

ORGS = [
    {"name": "Acme RevOps", "slug": "acme-revops", "plan": "growth"},
    {"name": "Demo Health Ops", "slug": "demo-health", "plan": "starter"},
    {"name": "Enterprise Retail", "slug": "enterprise-retail", "plan": "business"},
]

USERS = [
    {
        "org_slug": "acme-revops",
        "email": "admin@acme.io",
        "full_name": "Alice Admin",
        "job_title": "RevOps Admin",
        "roles": ["admin"],
    },
    {
        "org_slug": "acme-revops",
        "email": "sales@acme.io",
        "full_name": "Sam Sales",
        "job_title": "Sales Director",
        "roles": ["sales"],
    },
    {
        "org_slug": "demo-health",
        "email": "ops@demo-health.io",
        "full_name": "Olivia Ops",
        "job_title": "Customer Success Lead",
        "roles": ["customer_success"],
    },
]

ACCOUNTS = [
    {
        "org_slug": "acme-revops",
        "name": "Cloudify SAS",
        "domain": "cloudify.io",
        "industry": "SaaS",
        "size": "51-200",
        "arr": 1200000,
    },
    {
        "org_slug": "demo-health",
        "name": "MedRecord Cloud",
        "domain": "medrecord.io",
        "industry": "Health",
        "size": "51-200",
        "arr": 1600000,
    },
    {
        "org_slug": "enterprise-retail",
        "name": "Retail Pulse",
        "domain": "retailpulse.io",
        "industry": "Retail",
        "size": "201-500",
        "arr": 2400000,
    },
]


def _get_org(session: AsyncSession, slug: str) -> Organization | None:
    return session.scalar(select(Organization).where(Organization.slug == slug))


def _get_user(session: AsyncSession, email: str) -> User | None:
    return session.scalar(select(User).where(User.email == email))


def _get_account(session: AsyncSession, org_id, name: str) -> Account | None:
    return session.scalar(select(Account).where(Account.org_id == org_id, Account.name == name))


async def seed() -> None:
    engine = create_async_engine(DATABASE_URL, future=True)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session() as session:
        org_map: dict[str, Organization] = {}
        for org_data in ORGS:
            org = await _get_org(session, org_data["slug"])
            if org is None:
                org = Organization(name=org_data["name"], slug=org_data["slug"], plan=org_data["plan"])
                session.add(org)
                await session.flush()
                print(f"Created org: {org.slug}")
            else:
                print(f"Org already exists: {org.slug}")
            org_map[org.slug] = org

        user_objects: dict[str, User] = {}
        for user_data in USERS:
            org = org_map[user_data["org_slug"]]
            user = await _get_user(session, user_data["email"])
            if user is None:
                user = User(
                    org_id=org.id,
                    email=user_data["email"],
                    password_hash=get_password_hash(MOCK_PASSWORD),
                    full_name=user_data["full_name"],
                    job_title=user_data["job_title"],
                    roles=user_data["roles"],
                    permissions=permissions_for_roles(user_data["roles"]),
                )
                session.add(user)
                await session.flush()
                print(f"Created user: {user.email} for org {org.slug}")
            else:
                if not user.permissions:
                    user.permissions = permissions_for_roles(user.roles)
                    session.add(user)
                    print(f"Updated permissions for existing user: {user.email}")
                else:
                    print(f"User already exists: {user.email}")
            user_objects[user.email] = user

        for account_data in ACCOUNTS:
            org = org_map[account_data["org_slug"]]
            account = await _get_account(session, org.id, account_data["name"])
            if account is None:
                account = Account(
                    org_id=org.id,
                    name=account_data["name"],
                    domain=account_data["domain"],
                    industry=account_data["industry"],
                    size=account_data["size"],
                    arr=account_data["arr"],
                )
                session.add(account)
                print(f"Created account: {account.name} for org {org.slug}")
            else:
                print(f"Account already exists: {account.name} for org {org.slug}")

        await session.commit()

    await engine.dispose()
    print("\nPredeployment mocks seeded successfully.")
    print("Available test credentials:")
    print("  admin@acme.io / acme1234")
    print("  sales@acme.io / acme1234")
    print("  ops@demo-health.io / acme1234")


if __name__ == "__main__":
    import asyncio

    asyncio.run(seed())
