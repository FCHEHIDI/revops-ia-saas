#!/usr/bin/env python3
"""Seed script — données de démonstration pour "Acme RevOps".

Idempotent : si l'org slug ``acme-revops`` existe déjà, le script s'arrête
sans modifier les données existantes.

Usage (depuis le répertoire backend/) :
    python scripts/seed_demo.py

Prérequis :
    - DATABASE_URL dans .env ou dans l'environnement
    - Migrations 0001-0003 appliquées (alembic upgrade head)
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# ── Permet d'importer les modules de l'application ───────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import dotenv
dotenv.load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.auth.service import get_password_hash
from app.crm.models import Account, Contact, Deal
from app.models.activity import Activity
from app.models.organization import Organization
from app.models.user import User

# ── Config ────────────────────────────────────────────────────────────────────

DATABASE_URL = os.environ["DATABASE_URL"]
DEMO_PASSWORD = "acme1234"

# ── Données statiques ─────────────────────────────────────────────────────────

ACCOUNTS_DATA: list[dict] = [
    # SaaS (10)
    {"name": "Cloudify SAS",         "domain": "cloudify.io",       "industry": "SaaS",    "size": "51-200",   "arr": 1_200_000},
    {"name": "DataSync Labs",         "domain": "datasync.dev",      "industry": "SaaS",    "size": "11-50",    "arr":   480_000},
    {"name": "PipelineAI",           "domain": "pipelineai.io",     "industry": "SaaS",    "size": "201-500",  "arr": 3_500_000},
    {"name": "Retool Pro",            "domain": "retoolpro.com",     "industry": "SaaS",    "size": "51-200",   "arr":   850_000},
    {"name": "Notionify",            "domain": "notionify.app",     "industry": "SaaS",    "size": "1-10",     "arr":   120_000},
    {"name": "Zapier Clone Co",      "domain": "zapclone.io",       "industry": "SaaS",    "size": "11-50",    "arr":   330_000},
    {"name": "Basecamp EU",          "domain": "basecampeu.com",    "industry": "SaaS",    "size": "51-200",   "arr":   960_000},
    {"name": "Segment Replica",      "domain": "segmentrep.io",     "industry": "SaaS",    "size": "201-500",  "arr": 2_100_000},
    {"name": "Mixpanel FR",          "domain": "mixpanelfr.com",    "industry": "SaaS",    "size": "51-200",   "arr": 1_450_000},
    {"name": "Amplitude Clone",      "domain": "amplitudeclone.io", "industry": "SaaS",    "size": "11-50",    "arr":   560_000},
    # FinTech (8)
    {"name": "FinCore SA",           "domain": "fincore.fr",        "industry": "FinTech", "size": "51-200",   "arr": 2_800_000},
    {"name": "PayBridge EU",         "domain": "paybridge.eu",      "industry": "FinTech", "size": "201-500",  "arr": 5_200_000},
    {"name": "Ledger Analytics",     "domain": "ledgeranalytics.io","industry": "FinTech", "size": "11-50",    "arr":   720_000},
    {"name": "Stripe Competitor",    "domain": "stripeco.io",       "industry": "FinTech", "size": "201-500",  "arr": 4_100_000},
    {"name": "Crypto Custody Ltd",   "domain": "cryptocustody.com", "industry": "FinTech", "size": "51-200",   "arr": 1_900_000},
    {"name": "Neobank Pro",          "domain": "neobankpro.eu",     "industry": "FinTech", "size": "51-200",   "arr": 1_100_000},
    {"name": "Invoice Rocket",       "domain": "invoicerocket.io",  "industry": "FinTech", "size": "11-50",    "arr":   390_000},
    {"name": "Treasury AI",          "domain": "treasuryai.com",    "industry": "FinTech", "size": "11-50",    "arr":   610_000},
    # Health (6)
    {"name": "MedRecord Cloud",      "domain": "medrecord.io",      "industry": "Health",  "size": "51-200",   "arr": 1_600_000},
    {"name": "HealthTrack SAS",      "domain": "healthtrack.fr",    "industry": "Health",  "size": "11-50",    "arr":   450_000},
    {"name": "ClinicalAI Europe",    "domain": "clinicalai.eu",     "industry": "Health",  "size": "201-500",  "arr": 3_200_000},
    {"name": "Pharma Connect",       "domain": "pharmaconnect.com", "industry": "Health",  "size": "51-200",   "arr":   980_000},
    {"name": "TeleHealth Pro",       "domain": "telehealthpro.io",  "industry": "Health",  "size": "11-50",    "arr":   310_000},
    {"name": "BioData Systems",      "domain": "biodata.io",        "industry": "Health",  "size": "11-50",    "arr":   270_000},
    # Retail (6)
    {"name": "Retail Pulse",         "domain": "retailpulse.io",    "industry": "Retail",  "size": "201-500",  "arr": 2_400_000},
    {"name": "Ecom Boost",           "domain": "ecomboost.fr",      "industry": "Retail",  "size": "51-200",   "arr":   870_000},
    {"name": "Inventory AI",         "domain": "inventoryai.com",   "industry": "Retail",  "size": "51-200",   "arr":   640_000},
    {"name": "ShopSync Europe",      "domain": "shopsync.eu",       "industry": "Retail",  "size": "201-500",  "arr": 1_800_000},
    {"name": "Loyalty Cloud",        "domain": "loyaltycloud.io",   "industry": "Retail",  "size": "11-50",    "arr":   420_000},
    {"name": "POS Analytics",        "domain": "posanalytics.com",  "industry": "Retail",  "size": "11-50",    "arr":   290_000},
]

FIRST_NAMES = [
    "Alice", "Bob", "Claire", "David", "Emma", "François", "Gabrielle", "Hugo",
    "Isabelle", "Jules", "Karima", "Luca", "Marie", "Nathan", "Olivia", "Pierre",
    "Quentin", "Rachel", "Sébastien", "Théo", "Ursula", "Victor", "Wendy",
    "Xavier", "Yasmine", "Zoé", "Adam", "Beatrice", "Cédric", "Diane",
]
LAST_NAMES = [
    "Martin", "Bernard", "Leroy", "Dupont", "Moreau", "Simon", "Laurent",
    "Lefebvre", "Michel", "Garcia", "David", "Bertrand", "Thomas", "Robert",
    "Richard", "Petit", "Durand", "Blanc", "Garnier", "Rousseau",
]
JOB_TITLES = [
    "VP Sales", "Account Executive", "Sales Manager", "Director of Revenue",
    "Head of Growth", "Chief Revenue Officer", "Business Development Manager",
    "Enterprise Account Manager", "SDR", "Customer Success Manager",
]

DEAL_TEMPLATES = [
    # (title_tpl, stage, amount, probability, days_to_close, notes)
    ("Renouvellement annuel {account}",          "won",           150_000, 100,  -30,  "Contrat signé en mars. Renouvellement 3 ans."),
    ("Expansion licence {account}",             "negotiation",   220_000,  80,   20,  "Dernière révision des CGU en cours avec la direction juridique."),
    ("Intégration enterprise {account}",        "proposal",      380_000,  60,   45,  "Proposal envoyée, attente du COMEX."),
    ("Pilote POC {account}",                     "prospecting",    45_000,  20,   90,  "Premier appel de découverte fait. Budget non confirmé."),
    ("Migration cloud {account}",               "qualification",  120_000,  40,   60,  "RFP reçue. Qualification budget en cours."),
    ("Upsell Analytics {account}",              "closing",       175_000,  90,   10,  "Bon de commande en attente de signature DSI."),
    ("Partenariat revendeur {account}",         "lost",           80_000,   0,  -15,  "Perdu face à un concurrent sur le prix. Raison: pricing."),
    ("Module compliance {account}",             "proposal",      210_000,  55,   35,  "RFP en cours d'évaluation. Démo planifiée semaine prochaine."),
    ("Contrat cadre pluriannuel {account}",     "won",           500_000, 100,  -60,  "Contrat signé. ARR mis à jour."),
    ("Accélérateur RevOps {account}",           "negotiation",   290_000,  75,   25,  "Négociation sur le périmètre support 24/7."),
    ("Audit sécurité {account}",                "qualification",  95_000,  35,   50,  "CISO impliqué. Questionnaire sécurité envoyé."),
    ("Déploiement multi-sites {account}",       "proposal",      430_000,  50,   40,  "Architecture proposée. Validation technique en cours."),
    ("Renouvellement + upsell {account}",       "closing",       195_000,  85,    5,  "Champion côté client validé. Executive brief programmé."),
    ("Onboarding startup {account}",            "won",            18_000, 100,  -10,  "Petit compte. Signé en 2 semaines. Bon indicateur ICP."),
    ("Deal stratégique 2026 {account}",         "prospecting",   600_000,  15,  120,  "Identification du compte. Pas encore de contact qualifié."),
    ("Formation & adoption {account}",          "proposal",       65_000,  60,   30,  "Équipe CS impliquée. SOW en rédaction."),
    ("Intégration CRM tiers {account}",         "negotiation",   145_000,  70,   18,  "Mapping champs en cours avec équipe technique client."),
    ("Licence startup S2 {account}",            "qualification",  38_000,  30,   55,  "Passage en comité d'investissement prévu."),
    ("Extension géographique {account}",        "won",           320_000, 100,  -20,  "Expansion Benelux validée. Contrat actif."),
    ("Plateforme BI {account}",                 "lost",          270_000,   0,  -45,  "Perdu : client est allé en interne. Décision stratégique."),
    ("POC IA générative {account}",             "proposal",      180_000,  55,   50,  "LLM use-case identifié. Budget R&D validé."),
    ("Support premium {account}",               "closing",        48_000,  88,    8,  "Avenant support en attente signature RH."),
    ("Démo enterprise pipeline {account}",      "prospecting",   750_000,  10,  180,  "Grand compte identifié via LinkedIn Sales Nav."),
    ("Contrat gouvernance data {account}",      "negotiation",   390_000,  78,   22,  "DPO impliqué. DPIA en cours."),
    ("Renouvellement PME {account}",            "won",            22_000, 100,   -5,  "Auto-renouvellement accepté. Pas d'escalade."),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_email(first: str, last: str, domain: str) -> str:
    """Génère une adresse e-mail propre à partir d'un prénom, nom et domaine."""
    clean = lambda s: (
        s.lower()
        .replace("é", "e").replace("è", "e").replace("ê", "e").replace("ë", "e")
        .replace("à", "a").replace("â", "a").replace("ä", "a")
        .replace("ô", "o").replace("ö", "o")
        .replace("û", "u").replace("ü", "u").replace("ù", "u")
        .replace("î", "i").replace("ï", "i")
        .replace("ç", "c").replace("ñ", "n")
        .replace(" ", "").replace("-", "")
        .replace("'", "")
    )
    return f"{clean(first)}.{clean(last)}@{domain}"


# ── Helpers activités ─────────────────────────────────────────────────────────

_ACTIVITY_TYPES = [
    ("note_added",         "contact"),
    ("deal_stage_changed", "deal"),
    ("email_sent",         "contact"),
    ("ai_chat_message",    "deal"),
    ("note_added",         "deal"),
    ("email_opened",       "contact"),
]
_NOTE_TEXTS = [
    "Call découverte effectué. Budget confirmé à 200K€.",
    "Démo réalisée. Feedback très positif de la DSI.",
    "Devis envoyé. En attente de validation direction.",
    "Point hebdo : avancement conforme au plan.",
    "Escalade vers le CTO — décision attendue sous 2 semaines.",
    "Renouvellement confirmé par email.",
    "RDV planifié pour présentation executive.",
    "Contrat en relecture juridique.",
    "KO suite à changement de priorités chez le prospect.",
    "Champion identifié : Directeur Commercial.",
    "POC démarré. Résultats attendus en J+15.",
    "Mise à jour CRM après appel de suivi.",
    "Invitation salon envoyée. Participation confirmée.",
    "Feedback négatif sur la tarification — à retravailler.",
    "Nouveau contact identifié dans l'org.",
    "LLM a suggéré un follow-up immédiat.",
    "Email de relance envoyé (J+7 sans réponse).",
    "Réunion avec équipe technique validée.",
    "Analyse de compétitivité demandée par le prospect.",
    "Champion en vacances — reprise prévue semaine prochaine.",
]


async def _seed_activities_only(db: AsyncSession, org: "Organization") -> None:
    """Insère 50 activités pour une org existante (patch idempotent).

    Args:
        db: Session SQLAlchemy async.
        org: Organisation cible (acme-revops).
    """
    from sqlalchemy import func as sqlfunc

    rng = random.Random(42)
    now_utc = datetime.now(timezone.utc)

    # Récupérer utilisateurs, deals, contacts existants
    users_res = (await db.execute(select(User).where(User.org_id == org.id))).scalars().all()
    deals_res = (await db.execute(select(Deal).where(Deal.org_id == org.id))).scalars().all()
    contacts_res = (await db.execute(select(Contact).where(Contact.org_id == org.id))).scalars().all()

    await db.execute(
        text("SELECT set_config('app.current_tenant_id', :tid, true)"),
        {"tid": str(org.id)},
    )

    current_count_result = await db.execute(
        select(sqlfunc.count()).select_from(Activity).where(Activity.tenant_id == org.id)
    )
    current_count = current_count_result.scalar() or 0
    needed = 50 - current_count

    inserted = 0
    for i in range(needed):
        atype, entity_type = _ACTIVITY_TYPES[i % len(_ACTIVITY_TYPES)]
        actor = users_res[i % len(users_res)] if users_res else None
        days_ago = rng.randint(0, 90)
        created_ts = now_utc - timedelta(days=days_ago, hours=rng.randint(0, 23))

        if entity_type == "deal" and deals_res:
            entity_id = deals_res[i % len(deals_res)].id
        elif contacts_res:
            entity_id = contacts_res[i % len(contacts_res)].id
        else:
            continue

        note_text = rng.choice(_NOTE_TEXTS)
        act = Activity(
            id=uuid.uuid4(),
            tenant_id=org.id,
            entity_type=entity_type,
            entity_id=entity_id,
            actor_id=actor.id if actor else None,
            type=atype,
            payload={"note": note_text},
        )
        act.created_at = created_ts  # type: ignore[assignment]
        db.add(act)
        inserted += 1

    await db.flush()
    print(f"  + {inserted} activités ajoutées (total: {current_count + inserted})")
    await _write_fixture(db, org)
    await db.commit()
    print("\n✅  Activités seed terminé avec succès !")


async def _write_fixture(db: AsyncSession, org: "Organization") -> None:
    """Écrit le fichier fixture JSON pour les tests.

    Args:
        db: Session SQLAlchemy async.
        org: Organisation cible.
    """
    from sqlalchemy import func as sqlfunc

    now_utc = datetime.now(timezone.utc)
    users_res = (await db.execute(select(User).where(User.org_id == org.id))).scalars().all()
    accounts_count = (await db.execute(
        select(sqlfunc.count()).select_from(Account).where(Account.org_id == org.id)
    )).scalar() or 0
    contacts_count = (await db.execute(
        select(sqlfunc.count()).select_from(Contact).where(Contact.org_id == org.id)
    )).scalar() or 0
    deals_count = (await db.execute(
        select(sqlfunc.count()).select_from(Deal).where(Deal.org_id == org.id)
    )).scalar() or 0
    activities_count = (await db.execute(
        select(sqlfunc.count()).select_from(Activity).where(Activity.tenant_id == org.id)
    )).scalar() or 0

    fixture_path = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "demo_seed.json"
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture: dict = {
        "meta": {
            "generated_at": now_utc.isoformat(),
            "seed": 42,
            "password": DEMO_PASSWORD,
        },
        "org": {"id": str(org.id), "name": org.name, "slug": org.slug, "plan": org.plan},
        "users": [
            {"id": str(u.id), "email": u.email, "full_name": u.full_name, "roles": u.roles}
            for u in users_res
        ],
        "accounts_count": accounts_count,
        "contacts_count": contacts_count,
        "deals_count": deals_count,
        "activities_count": activities_count,
    }
    fixture_path.write_text(json.dumps(fixture, indent=2, ensure_ascii=False))
    rel = fixture_path.relative_to(Path(__file__).resolve().parent.parent.parent)
    print(f"  + Fixture JSON → {rel}")


# ── Seed principal ────────────────────────────────────────────────────────────

async def seed(db: AsyncSession) -> None:
    """Insère toutes les données de démonstration de façon idempotente.

    Args:
        db: Session SQLAlchemy async (sans RLS actif — script d'amorçage).

    Raises:
        SystemExit: Si une erreur critique survient pendant l'insertion.
    """
    rng = random.Random(42)  # Graine fixe → résultat reproductible

    # ── 1. Organisation ───────────────────────────────────────────────────────
    existing_org = (
        await db.execute(select(Organization).where(Organization.slug == "acme-revops"))
    ).scalar_one_or_none()

    if existing_org is not None:
        # Org existe déjà — vérifier si les activités manquent
        from sqlalchemy import func as sqlfunc
        act_count_result = await db.execute(
            select(sqlfunc.count()).select_from(Activity).where(Activity.tenant_id == existing_org.id)
        )
        act_count = act_count_result.scalar() or 0
        if act_count >= 50:
            print("✓  Organisation 'acme-revops' déjà présente avec activités — seed ignoré.")
            return
        print(f"  ↻  Organisation existe, mais seulement {act_count} activité(s). Ajout des activités manquantes…")
        await _seed_activities_only(db, existing_org)
        return

    org = Organization(
        id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        name="Acme RevOps",
        slug="acme-revops",
        plan="pro",
    )
    db.add(org)
    await db.flush()
    print(f"  + Organisation : {org.name} ({org.id})")

    # ── Activation RLS pour les inserts suivants ───────────────────────────────
    # Les tables accounts/contacts/deals ont RLS activé.  On doit positionner
    # app.current_tenant_id AVANT d'insérer des lignes.
    await db.execute(
        text("SELECT set_config('app.current_tenant_id', :tid, true)"),
        {"tid": str(org.id)},
    )

    # ── 2. Utilisateurs ───────────────────────────────────────────────────────
    users_spec = [
        {
            "id":          uuid.UUID("00000000-0000-0000-0000-000000000010"),
            "email":       "admin@acme.io",
            "full_name":   "Alice Admin",
            "roles":       ["admin"],
            "permissions": [
                "crm:accounts:write", "crm:contacts:write", "crm:deals:write",
                "crm:accounts:read",  "crm:contacts:read",  "crm:deals:read",
            ],
        },
        {
            "id":          uuid.UUID("00000000-0000-0000-0000-000000000011"),
            "email":       "sales@acme.io",
            "full_name":   "Sam Sales",
            "roles":       ["sales"],
            "permissions": [
                "crm:accounts:read", "crm:contacts:read",
                "crm:deals:write",   "crm:deals:read",
            ],
        },
        {
            "id":          uuid.UUID("00000000-0000-0000-0000-000000000012"),
            "email":       "ops@acme.io",
            "full_name":   "Oscar Ops",
            "roles":       ["revops"],
            "permissions": [
                "crm:accounts:read", "crm:contacts:read", "crm:deals:read",
            ],
        },
    ]

    user_objects: list[User] = []
    for spec in users_spec:
        u = User(
            id=spec["id"],
            org_id=org.id,
            email=spec["email"],
            full_name=spec["full_name"],
            password_hash=get_password_hash(DEMO_PASSWORD),
            roles=spec["roles"],
            permissions=spec["permissions"],
            is_active=True,
        )
        db.add(u)
        user_objects.append(u)
    await db.flush()
    print(f"  + {len(user_objects)} utilisateurs créés (mdp: {DEMO_PASSWORD})")

    admin_user = user_objects[0]
    sales_user = user_objects[1]

    # ── 3. Accounts ───────────────────────────────────────────────────────────
    account_objects: list[Account] = []
    for idx, data in enumerate(ACCOUNTS_DATA):
        acc = Account(
            id=uuid.uuid4(),
            org_id=org.id,
            name=data["name"],
            domain=data["domain"],
            industry=data["industry"],
            size=data["size"],
            arr=data["arr"],
            status="active",
            created_by=admin_user.id,
        )
        db.add(acc)
        account_objects.append(acc)
    await db.flush()
    print(f"  + {len(account_objects)} comptes créés")

    # ── 4. Contacts (80 répartis sur les 30 comptes) ──────────────────────────
    contact_objects: list[Contact] = []
    used_emails: set[str] = set()

    for i in range(80):
        account = account_objects[i % len(account_objects)]
        first = rng.choice(FIRST_NAMES)
        last = rng.choice(LAST_NAMES)

        # Déduplique les emails dans ce batch
        base_email = _make_email(first, last, account.domain or "acme-demo.io")
        email = base_email
        suffix = 1
        while email in used_emails:
            email = f"{base_email.split('@')[0]}{suffix}@{base_email.split('@')[1]}"
            suffix += 1
        used_emails.add(email)

        c = Contact(
            id=uuid.uuid4(),
            org_id=org.id,
            account_id=account.id,
            first_name=first,
            last_name=last,
            email=email,
            phone=f"+33 6 {rng.randint(10, 99)} {rng.randint(10, 99)} {rng.randint(10, 99)} {rng.randint(10, 99)}",
            job_title=rng.choice(JOB_TITLES),
            status="active",
            created_by=admin_user.id,
        )
        db.add(c)
        contact_objects.append(c)
    await db.flush()
    print(f"  + {len(contact_objects)} contacts créés")

    # ── 5. Deals (25) ─────────────────────────────────────────────────────────
    today = date.today()
    deal_owners = [sales_user, admin_user, sales_user]  # distribution réaliste

    for idx, tmpl in enumerate(DEAL_TEMPLATES):
        title_tpl, stage, amount, probability, days_delta, notes = tmpl
        account = account_objects[idx % len(account_objects)]
        contact = contact_objects[idx % len(contact_objects)]
        owner = deal_owners[idx % len(deal_owners)]

        close_date = today + timedelta(days=days_delta)
        # Légère variation sur les montants pour rendre les données crédibles
        jitter = rng.uniform(0.85, 1.15)
        final_amount = round(amount * jitter, -2)  # arrondi à la centaine

        deal = Deal(
            id=uuid.uuid4(),
            org_id=org.id,
            account_id=account.id,
            contact_id=contact.id,
            owner_id=owner.id,
            title=title_tpl.format(account=account.name),
            stage=stage,
            amount=final_amount,
            currency="EUR",
            close_date=close_date,
            probability=probability,
            notes=notes,
            created_by=admin_user.id,
        )
        db.add(deal)
    await db.flush()
    print(f"  + {len(DEAL_TEMPLATES)} deals créés")

    # ── 6 & 7. Activités + fixture JSON ───────────────────────────────────────
    await _seed_activities_only(db, org)
    # _seed_activities_only calls db.commit() internally, so we exit here.

    print("\n✅  Seed terminé avec succès !")
    print(f"\n  Logins disponibles (mdp commun : {DEMO_PASSWORD})")
    print("  ┌─────────────────────┬──────────┐")
    print("  │ admin@acme.io       │ admin    │")
    print("  │ sales@acme.io       │ sales    │")
    print("  │ ops@acme.io         │ revops   │")
    print("  └─────────────────────┴──────────┘")


# ── Entrypoint ────────────────────────────────────────────────────────────────

async def main() -> None:
    """Point d'entrée principal du script de seed.

    Raises:
        KeyError: Si DATABASE_URL n'est pas défini dans l'environnement.
    """
    engine = create_async_engine(DATABASE_URL, future=True, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    print("\n🌱  Démarrage du seed de démonstration Acme RevOps…\n")
    async with session_factory() as db:
        try:
            await seed(db)
        except Exception as exc:
            await db.rollback()
            print(f"\n❌  Erreur pendant le seed : {exc}", file=sys.stderr)
            raise

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
