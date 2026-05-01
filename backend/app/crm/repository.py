from typing import Optional, Tuple, List
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, or_, func
from sqlalchemy.exc import IntegrityError

from .models import Account, Contact, Deal
from .schemas import AccountCreate, ContactCreate, DealCreate

# -- ACCOUNTS --
async def get_account(db: AsyncSession, account_id: UUID) -> Optional[Account]:
    result = await db.execute(select(Account).where(Account.id == account_id))
    return result.scalar_one_or_none()

async def search_accounts(db: AsyncSession, query: Optional[str], industry: Optional[str], page: int, limit: int) -> Tuple[List[Account], int]:
    q = select(Account)
    if query:
        q = q.where(or_(Account.name.ilike(f"%{query}%"), Account.domain.ilike(f"%{query}%")))
    if industry:
        q = q.where(Account.industry == industry)
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    rows = await db.execute(q.offset((page - 1) * limit).limit(limit))
    return rows.scalars().all(), total

async def create_account(db: AsyncSession, data: AccountCreate, created_by: UUID, tenant_id: UUID) -> Account:
    account = Account(**data.model_dump(), created_by=created_by, org_id=tenant_id)
    db.add(account)
    try:
        await db.commit()
        await db.refresh(account)
        return account
    except IntegrityError:
        await db.rollback()
        raise

async def update_account(db: AsyncSession, account_id: UUID, fields: dict) -> Optional[Account]:
    q = update(Account).where(Account.id == account_id).values(**fields).execution_options(synchronize_session="fetch")
    await db.execute(q)
    await db.commit()
    return await get_account(db, account_id)

# -- CONTACTS --
async def get_contact(db: AsyncSession, contact_id: UUID) -> Optional[Contact]:
    result = await db.execute(select(Contact).where(Contact.id == contact_id))
    return result.scalar_one_or_none()

async def search_contacts(db: AsyncSession, query: Optional[str], account_id: Optional[UUID], page: int, limit: int) -> Tuple[List[Contact], int]:
    q = select(Contact)
    if query:
        q = q.where(or_(Contact.first_name.ilike(f"%{query}%"), Contact.last_name.ilike(f"%{query}%"), Contact.email.ilike(f"%{query}%")))
    if account_id:
        q = q.where(Contact.account_id == account_id)
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    ordered = q.order_by(Contact.created_at.desc()).offset((page - 1) * limit).limit(limit)
    rows = await db.execute(ordered)
    return rows.scalars().all(), total

async def create_contact(db: AsyncSession, data: ContactCreate, created_by: UUID, tenant_id: UUID) -> Contact:
    contact = Contact(**data.model_dump(), created_by=created_by, org_id=tenant_id)
    db.add(contact)
    try:
        await db.commit()
        await db.refresh(contact)
        return contact
    except IntegrityError:
        await db.rollback()
        raise

async def update_contact(db: AsyncSession, contact_id: UUID, fields: dict) -> Optional[Contact]:
    q = update(Contact).where(Contact.id == contact_id).values(**fields).execution_options(synchronize_session="fetch")
    await db.execute(q)
    await db.commit()
    return await get_contact(db, contact_id)

async def delete_contact(db: AsyncSession, contact_id: UUID) -> bool:
    """Delete a contact by ID. Returns True if deleted, False if not found."""
    contact = await get_contact(db, contact_id)
    if not contact:
        return False
    await db.delete(contact)
    await db.commit()
    return True

# -- DEALS --
async def get_deal(db: AsyncSession, deal_id: UUID) -> Optional[Deal]:
    result = await db.execute(select(Deal).where(Deal.id == deal_id))
    return result.scalar_one_or_none()

async def list_deals(db: AsyncSession, stage: Optional[str], owner_id: Optional[UUID], page: int, limit: int) -> Tuple[List[Deal], int]:
    q = select(Deal)
    if stage:
        q = q.where(Deal.stage == stage)
    if owner_id:
        q = q.where(Deal.owner_id == owner_id)
    total = await db.scalar(select(func.count()).select_from(q.subquery()))
    rows = await db.execute(q.offset((page-1)*limit).limit(limit))
    return rows.scalars().all(), total

async def create_deal(db: AsyncSession, data: DealCreate, created_by: UUID, tenant_id: UUID) -> Deal:
    deal = Deal(**data.model_dump(), created_by=created_by, org_id=tenant_id)
    db.add(deal)
    try:
        await db.commit()
        await db.refresh(deal)
        return deal
    except IntegrityError:
        await db.rollback()
        raise

async def update_deal_stage(db: AsyncSession, deal_id: UUID, new_stage: str, notes: Optional[str] = None) -> Optional[Deal]:
    update_fields = {"stage": new_stage}
    if notes is not None:
        update_fields["notes"] = notes
    q = update(Deal).where(Deal.id == deal_id).values(**update_fields).execution_options(synchronize_session="fetch")
    await db.execute(q)
    await db.commit()
    return await get_deal(db, deal_id)


async def update_deal(db: AsyncSession, deal_id: UUID, fields: dict) -> Optional[Deal]:
    if not fields:
        return await get_deal(db, deal_id)
    q = update(Deal).where(Deal.id == deal_id).values(**fields).execution_options(synchronize_session="fetch")
    await db.execute(q)
    await db.commit()
    return await get_deal(db, deal_id)
