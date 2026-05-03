from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from .repository import (
    get_account, search_accounts, create_account, update_account,
    get_contact, search_contacts, create_contact, update_contact, delete_contact,
    get_deal, list_deals, create_deal, update_deal_stage, update_deal,
)
from .schemas import (
    AccountCreate, AccountRead, PaginatedAccounts,
    ContactCreate, ContactRead, PaginatedContacts,
    DealCreate, DealRead, PaginatedDeals
)
from app.audit.service import log_action
from app.activities.service import record as _record_activity
from app.webhooks.service import publish_event as _publish_webhook_event
from .rag_publisher import publish_deal_index_job

# --- ACCOUNT ---
async def get_account_by_id(db: AsyncSession, account_id: UUID, tenant_id: UUID, user_id: UUID | None) -> AccountRead:
    acc = await get_account(db, account_id)
    if not acc:
        raise HTTPException(status_code=404, detail="Account not found")
    return AccountRead.model_validate(acc)

async def search_accounts_service(db: AsyncSession, query: str | None, industry: str | None, page: int, limit: int, tenant_id: UUID, user_id: UUID | None) -> PaginatedAccounts:
    items, total = await search_accounts(db, query, industry, page, limit)
    await log_action(db, tenant_id, user_id, "crm:accounts:search", "accounts", {})
    return PaginatedAccounts(items=[AccountRead.model_validate(a) for a in items], page=page, limit=limit, total=total)

async def create_account_service(db: AsyncSession, data: AccountCreate, tenant_id: UUID, user_id: UUID) -> AccountRead:
    try:
        acc = await create_account(db, data, user_id, tenant_id)
        await log_action(db, tenant_id, user_id, "crm:accounts:create", "accounts", {"id": str(acc.id)})
        return AccountRead.model_validate(acc)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Account already exists")

async def update_account_service(db: AsyncSession, account_id: UUID, fields: dict, tenant_id: UUID, user_id: UUID) -> AccountRead:
    try:
        acc = await update_account(db, account_id, fields)
        if not acc:
            raise HTTPException(status_code=404, detail="Account not found")
        await log_action(db, tenant_id, user_id, "crm:accounts:update", "accounts", {"id": str(account_id)})
        return AccountRead.model_validate(acc)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Account update conflict")

# --- CONTACT ---
async def get_contact_by_id(db: AsyncSession, contact_id: UUID, tenant_id: UUID, user_id: UUID | None) -> ContactRead:
    c = await get_contact(db, contact_id)
    if not c:
        raise HTTPException(status_code=404, detail="Contact not found")
    return ContactRead.model_validate(c)

async def search_contacts_service(db: AsyncSession, query: str | None, account_id: UUID | None, page: int, limit: int, tenant_id: UUID, user_id: UUID | None) -> PaginatedContacts:
    items, total = await search_contacts(db, query, account_id, page, limit)
    await log_action(db, tenant_id, user_id, "crm:contacts:search", "contacts", {})
    return PaginatedContacts(items=[ContactRead.model_validate(a) for a in items], page=page, limit=limit, total=total)

async def create_contact_service(db: AsyncSession, data: ContactCreate, tenant_id: UUID, user_id: UUID) -> ContactRead:
    try:
        c = await create_contact(db, data, user_id, tenant_id)
        await log_action(db, tenant_id, user_id, "crm:contacts:create", "contacts", {"id": str(c.id)})
        await _record_activity(
            db,
            tenant_id=tenant_id,
            entity_type="contact",
            entity_id=c.id,
            activity_type="contact_created",
            actor_id=user_id,
            payload={"email": c.email, "name": c.name},
        )
        await _publish_webhook_event(
            tenant_id=tenant_id,
            event_type="contact.created",
            payload={"id": str(c.id), "email": c.email, "name": c.name},
        )
        return ContactRead.model_validate(c)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Contact already exists")

async def update_contact_service(db: AsyncSession, contact_id: UUID, fields: dict, tenant_id: UUID, user_id: UUID) -> ContactRead:
    try:
        c = await update_contact(db, contact_id, fields)
        if not c:
            raise HTTPException(status_code=404, detail="Contact not found")
        await log_action(db, tenant_id, user_id, "crm:contacts:update", "contacts", {"id": str(contact_id)})
        return ContactRead.model_validate(c)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Contact update conflict")

async def delete_contact_service(db: AsyncSession, contact_id: UUID, tenant_id: UUID, user_id: UUID) -> None:
    deleted = await delete_contact(db, contact_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Contact not found")
    await log_action(db, tenant_id, user_id, "crm:contacts:delete", "contacts", {"id": str(contact_id)})

# --- DEAL ---
async def get_deal_by_id(db: AsyncSession, deal_id: UUID, tenant_id: UUID, user_id: UUID | None) -> DealRead:
    d = await get_deal(db, deal_id)
    if not d:
        raise HTTPException(status_code=404, detail="Deal not found")
    return DealRead.model_validate(d)

async def list_deals_service(db: AsyncSession, stage: str | None, owner_id: UUID | None, page: int, limit: int, tenant_id: UUID, user_id: UUID | None) -> PaginatedDeals:
    items, total = await list_deals(db, stage, owner_id, page, limit)
    await log_action(db, tenant_id, user_id, "crm:deals:list", "deals", {})
    return PaginatedDeals(items=[DealRead.model_validate(a) for a in items], page=page, limit=limit, total=total)

async def create_deal_service(db: AsyncSession, data: DealCreate, tenant_id: UUID, user_id: UUID) -> DealRead:
    try:
        d = await create_deal(db, data, user_id, tenant_id)
        await log_action(db, tenant_id, user_id, "crm:deals:create", "deals", {"id": str(d.id)})
        await _record_activity(
            db,
            tenant_id=tenant_id,
            entity_type="deal",
            entity_id=d.id,
            activity_type="deal_created",
            actor_id=user_id,
            payload={"account_id": str(d.account_id), "stage": d.stage, "value": str(d.value or "")},
        )
        # Si notes non vide → déclenche publish_deal_index_job
        if d.notes:
            await publish_deal_index_job(d.id, tenant_id, d.notes, {"deal_id": str(d.id), "account_id": str(d.account_id), "stage": d.stage})
        return DealRead.model_validate(d)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Deal already exists")

async def update_deal_service(db: AsyncSession, deal_id: UUID, fields: dict, tenant_id: UUID, user_id: UUID) -> DealRead:
    try:
        # Si on met à jour stage ou notes, déclencher RAG
        stage = fields.get("stage")
        notes = fields.get("notes")
        d = await update_deal_stage(db, deal_id, stage, notes) if stage else await update_deal(db, deal_id, fields)
        if not d:
            raise HTTPException(status_code=404, detail="Deal not found")
        await log_action(db, tenant_id, user_id, "crm:deals:update", "deals", {"id": str(deal_id)})
        if stage:
            await _record_activity(
                db,
                tenant_id=tenant_id,
                entity_type="deal",
                entity_id=deal_id,
                activity_type="deal_stage_changed",
                actor_id=user_id,
                payload={"stage": stage},
            )
        if stage or notes:
            await publish_deal_index_job(deal_id, tenant_id, notes or "", {"deal_id": str(deal_id), "stage": stage})
        # Fire webhook events for terminal stage transitions
        if stage in ("won", "lost"):
            await _publish_webhook_event(
                tenant_id=tenant_id,
                event_type=f"deal.{stage}",
                payload={
                    "id": str(deal_id),
                    "stage": stage,
                    "account_id": str(d.account_id),
                },
            )
        return DealRead.model_validate(d)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Deal update conflict")
