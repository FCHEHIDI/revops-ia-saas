# Autopilote — Boucle d'agents pour RevOps IA SaaS

> **Rôle** : ce document décrit la **procédure d'autopilote** que l'agent principal (Cursor) doit suivre pour faire avancer le projet **sans intervention humaine** entre deux jalons.
>
> **Principe** : les subagents spécialisés (`.cursor/agents/*.md`) connaissent leur rôle. L'agent principal n'écrit pas le code à leur place : il **planifie**, **dispatche**, **agrège** et **valide**.

---

## 1. Sources de vérité

Avant tout cycle, l'agent principal **doit** charger en contexte :

| Document | Rôle |
|---|---|
| `docs/PROJECT_MANAGER_CHARTER.md` | Vision, rôles agents, standards |
| `docs/ARCHITECTURE.md` | Architecture cible 8 couches |
| `docs/adr/README.md` + ADRs `001`–`008` | Décisions structurantes |
| `.cursor/agents/*.md` | Identité de chaque subagent |

Toute proposition incohérente avec ces sources est **rejetée** sans débat.

---

## 2. Phases du projet

| Phase | Périmètre | Statut |
|---|---|---|
| **Phase 1** | Backend FastAPI multi-tenant (auth cookie, RLS, sessions, documents, audit) | ✅ Terminée |
| **Phase 2** | MCP CRM (`mcp-crm` Python + `backend/app/crm/` + intégration orchestrator) | 🔄 En cours |
| **Phase 3** | MCP Billing + MCP Analytics | ⏳ À venir |
| **Phase 4** | MCP Sequences + MCP Filesystem + RAG ingestion E2E | ⏳ À venir |
| **Phase 5** | Frontend chat + vues structurées | ⏳ À venir |
| **Phase 6** | Production hardening (observabilité, scaling, multi-region) | ⏳ À venir |

L'autopilote travaille **uniquement sur la phase courante**, sauf instruction explicite.

---

## 3. Boucle d'autopilote (par cycle)

```
┌────────────────────────────────────────────────────────────────────┐
│  STEP 0 — Snapshot                                                 │
│  - git status / git diff --stat                                    │
│  - lecture rapide des sources de vérité (§1)                       │
│  - identification de la phase courante                             │
└──────────────────────────┬─────────────────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────────────────┐
│  STEP 1 — Décomposition en pistes (tracks)                         │
│  Une piste = un sous-objectif indépendant pris en charge par UN    │
│  subagent spécialisé. Pistes parallèles autant que possible.       │
└──────────────────────────┬─────────────────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────────────────┐
│  STEP 2 — Dispatch parallèle                                       │
│  Lancer les subagents simultanément (un seul tool-call batch).     │
│  Chaque prompt agent contient :                                    │
│    - les ADR / charte applicables                                  │
│    - le périmètre exact (fichiers à créer/modifier)                │
│    - les contraintes (tests, sécurité, conventions)                │
│    - le format de réponse attendu (résumé + diff)                  │
└──────────────────────────┬─────────────────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────────────────┐
│  STEP 3 — Agrégation                                               │
│  Lire les rapports des subagents.                                  │
│  Détecter conflits / régressions / non-conformités ADR.            │
└──────────────────────────┬─────────────────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────────────────┐
│  STEP 4 — Revue (Reviewer)                                         │
│  Le Reviewer lit l'intégralité des changements et émet :           │
│   ✅ APPROVED → continuer                                          │
│   ⚠️  NEEDS_FIX → re-dispatch ciblé sur la piste fautive           │
│   ⛔ REJECTED → revert + ré-architecture                           │
└──────────────────────────┬─────────────────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────────────────┐
│  STEP 5 — Versioning                                               │
│  L'agent Versioning crée des commits Conventional Commits          │
│  séparés par piste, et ouvre une PR si demandé.                    │
└──────────────────────────┬─────────────────────────────────────────┘
                           ▼
┌────────────────────────────────────────────────────────────────────┐
│  STEP 6 — Boucle ou stop                                           │
│  Si la phase courante n'est pas terminée → retour STEP 1           │
│  Sinon → mettre à jour la phase, mettre à jour ARCHITECTURE.md,    │
│  notifier l'utilisateur.                                           │
└────────────────────────────────────────────────────────────────────┘
```

---

## 4. Mapping subagents

| Subagent | À utiliser pour |
|---|---|
| `architecte-systeme` | Toute décision structurante, rédaction d'ADR |
| `developpeur-backend` | API multi-tenant, endpoints `/api/v1/*` et `/internal/v1/*`, SQLAlchemy, Alembic |
| `developpeur-mcp` | Serveurs MCP (Python pour CRM/Billing/Analytics/Sequences, Rust pour Filesystem si DB direct) |
| `developpeur-rag` | Vector store, embeddings, retrievers, ingestion async |
| `developpeur-orchestrateur` | Logique Rust orchestrator (context builder, queue, routing, prompt assembly) |
| `developpeur-frontend` | UI Next.js, chat IA, vues structurées |
| `DevOps` | Docker, K8s, Terraform, CI, observabilité |
| `Reviewer` | Revue obligatoire avant tout commit/merge |
| `Versioning & CI/CD` | Conventional Commits, branches, tags, releases, GH Actions |

**Règle absolue** : le Reviewer doit valider **avant** que le Versioning agent ne crée un commit.

---

## 5. Contraintes inviolables

1. **Multi-tenant** : tout endpoint, tool MCP ou job queue **doit** propager `tenant_id` (= `org_id`).
2. **MCP sans accès DB direct** (ADR-008) : les MCPs n'appellent que `/internal/v1/*` du backend.
3. **Orchestrateur stateless** (ADR-002) : aucun état global mutable, contexte reconstruit à chaque requête.
4. **Tests obligatoires** sur les chemins critiques (auth, RLS, multi-tenant, tools MCP).
5. **Conventional Commits** : `feat(scope)`, `fix(scope)`, `refactor(scope)`, `docs(scope)`, `chore(scope)`, `test(scope)`, `ci(scope)`. Footer `BREAKING CHANGE:` si rupture.
6. **Aucun secret en clair** : `.env.example` documente, `.env` est gitignored, secrets de prod via vault / GitHub Actions secrets.
7. **Linting/format** : `ruff` + `black` (Python), `cargo fmt` + `cargo clippy` (Rust), `eslint` + `prettier` (TS).

---

## 6. Format des prompts subagents

Chaque dispatch doit contenir :

```
## Contexte
- ADR concernés : [...]
- Charte : docs/PROJECT_MANAGER_CHARTER.md (déjà lue, à respecter)
- Phase courante : [...]

## Mission
[1-3 phrases — l'objectif unique de la piste]

## Périmètre
- Fichiers à créer : [liste exhaustive]
- Fichiers à modifier : [liste exhaustive]
- Fichiers interdits de modification : [si applicable]

## Contraintes techniques
- [stack, conventions, patterns à respecter]

## Sortie attendue
- [résumé exécutif, liste des fichiers touchés, points d'attention]
- Pas de commit (laisser à l'agent Versioning)
```

---

## 7. Cycle courant — Phase 2 finalisation

| Track | Subagent | Mission |
|---|---|---|
| A | `developpeur-backend` | Implémenter `backend/app/crm/` (modèles, migration `0002_crm_schema`, schémas, repo, service, permissions, router, intégration `main.py`) |
| B | `developpeur-mcp` | Finaliser `mcp/mcp-crm/` Python (vérifier 12 tools, tests respx, Dockerfile, env) |
| C | `Reviewer` | Auditer les 1074 lignes de modifs Rust orchestrator non commitées (queue/DLQ/worker/context builder/tests) — verdict APPROVED / NEEDS_FIX / REJECTED |
| D | `DevOps` | `docker-compose.dev.yml` + CI workflow Python pour mcp-crm + Makefile updates |
| E | `Versioning & CI/CD` | Commits Conventional par track après validation Reviewer |

---

*Mis à jour à chaque transition de phase. Toute évolution structurelle de la boucle nécessite un ADR.*
