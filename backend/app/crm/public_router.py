"""Router public CRM — accessible via JWT cookie, préfixe /api/v1/crm.

Contraste avec router.py (interne, X-Internal-API-Key, préfixe /internal/v1/crm)
qui est réservé à l'orchestrateur Rust.

Décision architecturale : ADR-009 — modèle hybride CRUD direct + LLM companion.
Les lectures/navigations passent par ce router (< 100ms).
Les analyses et actions complexes passent par le chat → orchestrateur → MCP.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_active_user
from app.common.db import get_db
from app.models.user import User

from .schemas import (
    AccountCreate,
    AccountRead,
    AccountUpdate,
    ContactCreate,
    ContactRead,
    ContactUpdate,
    DealCreate,
    DealRead,
    DealUpdate,
    PaginatedAccounts,
    PaginatedContacts,
    PaginatedDeals,
)
from .service import (
    create_account_service,
    create_contact_service,
    create_deal_service,
    delete_contact_service,
    get_account_by_id,
    get_contact_by_id,
    get_deal_by_id,
    list_deals_service,
    search_accounts_service,
    search_contacts_service,
    update_account_service,
    update_contact_service,
    update_deal_service,
)

router = APIRouter()


def _require_perm(user: User, perm: str) -> None:
    """Lève 403 si l'utilisateur ne possède pas la permission demandée.

    Args:
        user: Utilisateur courant issu du JWT.
        perm: Permission requise (ex: "crm:accounts:write").

    Raises:
        HTTPException: 403 si la permission est absente.
    """
    if perm not in (user.permissions or []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission '{perm}' required",
        )


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------

@router.get("/accounts", response_model=PaginatedAccounts, summary="Liste des comptes")
async def list_accounts(
    query: Optional[str] = None,
    industry: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedAccounts:
    return await search_accounts_service(
        db, query, industry, page, limit, user.org_id, user.id
    )


@router.get("/accounts/{id}", response_model=AccountRead, summary="Détail d'un compte")
async def get_account(
    id: UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> AccountRead:
    return await get_account_by_id(db, id, user.org_id, user.id)


@router.post(
    "/accounts",
    response_model=AccountRead,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un compte",
)
async def create_account(
    data: AccountCreate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> AccountRead:
    _require_perm(user, "crm:accounts:write")
    return await create_account_service(db, data, user.org_id, user.id)


@router.put("/accounts/{id}", response_model=AccountRead, summary="Mettre à jour un compte")
async def update_account(
    id: UUID,
    data: AccountUpdate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> AccountRead:
    _require_perm(user, "crm:accounts:write")
    return await update_account_service(
        db, id, data.model_dump(exclude_unset=True), user.org_id, user.id
    )


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------

@router.get("/contacts", response_model=PaginatedContacts, summary="Liste des contacts")
async def list_contacts(
    query: Optional[str] = None,
    account_id: Optional[UUID] = None,
    page: int = 1,
    limit: int = 20,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedContacts:
    return await search_contacts_service(
        db, query, account_id, page, limit, user.org_id, user.id
    )


@router.get("/contacts/{id}", response_model=ContactRead, summary="Détail d'un contact")
async def get_contact(
    id: UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ContactRead:
    return await get_contact_by_id(db, id, user.org_id, user.id)


@router.post(
    "/contacts",
    response_model=ContactRead,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un contact",
)
async def create_contact(
    data: ContactCreate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ContactRead:
    _require_perm(user, "crm:contacts:write")
    return await create_contact_service(db, data, user.org_id, user.id)


@router.put(
    "/contacts/{id}", response_model=ContactRead, summary="Mettre à jour un contact"
)
async def update_contact(
    id: UUID,
    data: ContactUpdate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> ContactRead:
    _require_perm(user, "crm:contacts:write")
    return await update_contact_service(
        db, id, data.model_dump(exclude_unset=True), user.org_id, user.id
    )


@router.delete(
    "/contacts/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Supprimer un contact",
)
async def delete_contact(
    id: UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Supprime un contact appartenant au tenant courant.

    Args:
        id: UUID du contact à supprimer.
        user: Utilisateur courant (JWT).
        db: Session base de données.

    Raises:
        HTTPException: 403 si permission manquante, 404 si contact introuvable.
    """
    _require_perm(user, "crm:contacts:write")
    await delete_contact_service(db, id, user.org_id, user.id)


# ---------------------------------------------------------------------------
# Deals
# ---------------------------------------------------------------------------

@router.get("/deals", response_model=PaginatedDeals, summary="Liste des deals")
async def list_deals(
    stage: Optional[str] = None,
    owner_id: Optional[UUID] = None,
    page: int = 1,
    limit: int = 20,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedDeals:
    return await list_deals_service(
        db, stage, owner_id, page, limit, user.org_id, user.id
    )


@router.get("/deals/{id}", response_model=DealRead, summary="Détail d'un deal")
async def get_deal(
    id: UUID,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DealRead:
    return await get_deal_by_id(db, id, user.org_id, user.id)


@router.post(
    "/deals",
    response_model=DealRead,
    status_code=status.HTTP_201_CREATED,
    summary="Créer un deal",
)
async def create_deal(
    data: DealCreate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DealRead:
    _require_perm(user, "crm:deals:write")
    return await create_deal_service(db, data, user.org_id, user.id)


@router.put("/deals/{id}", response_model=DealRead, summary="Mettre à jour un deal")
async def update_deal(
    id: UUID,
    data: DealUpdate,
    user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> DealRead:
    _require_perm(user, "crm:deals:write")
    return await update_deal_service(
        db, id, data.model_dump(exclude_unset=True), user.org_id, user.id
    )
