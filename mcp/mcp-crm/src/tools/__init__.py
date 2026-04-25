from __future__ import annotations

from typing import Callable

from .contacts import create_contact, get_contact, search_contacts, update_contact
from .accounts import create_account, get_account, search_accounts, update_account
from .deals import create_deal, get_deal, list_deals, update_deal_stage

TOOL_REGISTRY: dict[str, Callable] = {
    # Contacts
    "get_contact": get_contact,
    "search_contacts": search_contacts,
    "create_contact": create_contact,
    "update_contact": update_contact,
    # Accounts
    "get_account": get_account,
    "search_accounts": search_accounts,
    "create_account": create_account,
    "update_account": update_account,
    # Deals
    "get_deal": get_deal,
    "list_deals": list_deals,
    "create_deal": create_deal,
    "update_deal_stage": update_deal_stage,
}

__all__ = [
    "TOOL_REGISTRY",
    "get_contact",
    "search_contacts",
    "create_contact",
    "update_contact",
    "get_account",
    "search_accounts",
    "create_account",
    "update_account",
    "get_deal",
    "list_deals",
    "create_deal",
    "update_deal_stage",
]
