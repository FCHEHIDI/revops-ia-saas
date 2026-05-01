from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID
from app.common.db import get_db
from .permissions import verify_internal_api_key, extract_tenant, extract_user_id, require_permission
from .schemas import (
    AccountCreate, AccountUpdate, AccountRead, PaginatedAccounts,
    ContactCreate, ContactUpdate, ContactRead, PaginatedContacts,
    DealCreate, DealUpdate, DealRead, PaginatedDeals
)
from .service import (
    get_account_by_id, search_accounts_service, create_account_service, update_account_service,
    get_contact_by_id, search_contacts_service, create_contact_service, update_contact_service, delete_contact_service,
    get_deal_by_id, list_deals_service, create_deal_service, update_deal_service
)

router = APIRouter(dependencies=[Depends(verify_internal_api_key)])

# --- Accounts ---
@router.get("/accounts/{id}", response_model=AccountRead)
async def get_account_route(id: UUID,
        tenant_id: UUID = Depends(extract_tenant),
        user_id: Optional[UUID] = Depends(extract_user_id),
        db: AsyncSession = Depends(get_db)):
    return await get_account_by_id(db, id, tenant_id, user_id)

@router.get("/accounts", response_model=PaginatedAccounts)
async def list_accounts_route(query: Optional[str] = None, industry: Optional[str] = None, page: int = 1, limit: int = 20,
        tenant_id: UUID = Depends(extract_tenant),
        user_id: Optional[UUID] = Depends(extract_user_id),
        db: AsyncSession = Depends(get_db)):
    return await search_accounts_service(db, query, industry, page, limit, tenant_id, user_id)

@router.post("/accounts", response_model=AccountRead, dependencies=[Depends(require_permission("crm:accounts:write"))])
async def create_account_route(data: AccountCreate,
        tenant_id: UUID = Depends(extract_tenant),
        user_id: UUID = Depends(extract_user_id),
        db: AsyncSession = Depends(get_db)):
    return await create_account_service(db, data, tenant_id, user_id)

@router.put("/accounts/{id}", response_model=AccountRead, dependencies=[Depends(require_permission("crm:accounts:write"))])
async def update_account_route(id: UUID, data: AccountUpdate,
        tenant_id: UUID = Depends(extract_tenant),
        user_id: UUID = Depends(extract_user_id),
        db: AsyncSession = Depends(get_db)):
    return await update_account_service(db, id, data.model_dump(exclude_unset=True), tenant_id, user_id)

# --- Contacts ---
@router.get("/contacts/{id}", response_model=ContactRead)
async def get_contact_route(id: UUID,
        tenant_id: UUID = Depends(extract_tenant),
        user_id: Optional[UUID] = Depends(extract_user_id),
        db: AsyncSession = Depends(get_db)):
    return await get_contact_by_id(db, id, tenant_id, user_id)

@router.get("/contacts", response_model=PaginatedContacts)
async def list_contacts_route(query: Optional[str] = None, account_id: Optional[UUID] = None, page: int = 1, limit: int = 20,
        tenant_id: UUID = Depends(extract_tenant),
        user_id: Optional[UUID] = Depends(extract_user_id),
        db: AsyncSession = Depends(get_db)):
    return await search_contacts_service(db, query, account_id, page, limit, tenant_id, user_id)

@router.post("/contacts", response_model=ContactRead, dependencies=[Depends(require_permission("crm:contacts:write"))])
async def create_contact_route(data: ContactCreate,
        tenant_id: UUID = Depends(extract_tenant),
        user_id: UUID = Depends(extract_user_id),
        db: AsyncSession = Depends(get_db)):
    return await create_contact_service(db, data, tenant_id, user_id)

@router.put("/contacts/{id}", response_model=ContactRead, dependencies=[Depends(require_permission("crm:contacts:write"))])
async def update_contact_route(id: UUID, data: ContactUpdate,
        tenant_id: UUID = Depends(extract_tenant),
        user_id: UUID = Depends(extract_user_id),
        db: AsyncSession = Depends(get_db)):
    return await update_contact_service(db, id, data.model_dump(exclude_unset=True), tenant_id, user_id)

@router.delete("/contacts/{id}", status_code=204, dependencies=[Depends(require_permission("crm:contacts:write"))])
async def delete_contact_route(id: UUID,
        tenant_id: UUID = Depends(extract_tenant),
        user_id: UUID = Depends(extract_user_id),
        db: AsyncSession = Depends(get_db)):
    await delete_contact_service(db, id, tenant_id, user_id)

# --- Deals ---
@router.get("/deals/{id}", response_model=DealRead)
async def get_deal_route(id: UUID,
        tenant_id: UUID = Depends(extract_tenant),
        user_id: Optional[UUID] = Depends(extract_user_id),
        db: AsyncSession = Depends(get_db)):
    return await get_deal_by_id(db, id, tenant_id, user_id)

@router.get("/deals", response_model=PaginatedDeals)
async def list_deals_route(stage: Optional[str] = None, owner_id: Optional[UUID] = None, page: int = 1, limit: int = 20,
        tenant_id: UUID = Depends(extract_tenant),
        user_id: Optional[UUID] = Depends(extract_user_id),
        db: AsyncSession = Depends(get_db)):
    return await list_deals_service(db, stage, owner_id, page, limit, tenant_id, user_id)

@router.post("/deals", response_model=DealRead, dependencies=[Depends(require_permission("crm:deals:write"))])
async def create_deal_route(data: DealCreate,
        tenant_id: UUID = Depends(extract_tenant),
        user_id: UUID = Depends(extract_user_id),
        db: AsyncSession = Depends(get_db)):
    return await create_deal_service(db, data, tenant_id, user_id)

@router.put("/deals/{id}", response_model=DealRead, dependencies=[Depends(require_permission("crm:deals:write"))])
async def update_deal_route(id: UUID, data: DealUpdate,
        tenant_id: UUID = Depends(extract_tenant),
        user_id: UUID = Depends(extract_user_id),
        db: AsyncSession = Depends(get_db)):
    return await update_deal_service(db, id, data.model_dump(exclude_unset=True), tenant_id, user_id)
