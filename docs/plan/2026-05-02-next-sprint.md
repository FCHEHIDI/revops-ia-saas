# Plan de sprint — reprise du 2 mai 2026

> Session du 1er mai : 10h → 01h13. Frontend v1 Venetian Cyber-Gothic stabilisé, mergé sur main, pushé sur GitHub.

---

## État exact au moment de la pause

### Ce qui tourne en local (commandes de démarrage)

```bash
# Infra
docker compose -f infra/docker/docker-compose.dev.yml up -d

# Backend FastAPI
cd backend && uvicorn app.main:app --port 18000 --reload

# Orchestrateur Rust
cd orchestrator && cargo run

# MCP CRM
cd mcp/mcp-crm && uvicorn src.main:app --port 19001 --reload

# MCP Billing (Rust)
cd mcp/mcp-billing && cargo run

# Frontend
cd frontend && npm run dev
```

**Credentials démo** : `admin@acme.io` / `acme1234` — org `acme-revops`  
**Frontend** : http://localhost:3000  
**Backend** : http://localhost:18000  
**Orchestrateur** : http://localhost:8003

---

## Ce qui est livré et stable ✅

| Composant | État |
|---|---|
| Design System Venetian Cyber-Gothic | ✅ stable, 0 erreurs TS |
| Auth multi-tenant RLS | ✅ 28 tests passants |
| Orchestrateur Rust SSE | ✅ streaming end-to-end |
| MCP routing | ✅ keyword-based mock |
| RAG parser multi-format | ✅ PDF/DOCX/XLSX parsé |
| 8 pages UI | ✅ Login/Xenito/Dashboard/CRM/Analytics/Billing/Séquences/Documents |
| Notifications Venetian | ✅ bellRing + badgePulse + pulseMarbre |
| Command palette Cmd+K | ✅ |
| Seed SQL (50 contacts, invoices, séquences) | ✅ |
| Screenshots docs/screenshots/ | ✅ 8 pages |

---

## Gaps critiques — ordre d'attaque

### 🔴 Sprint 1 — Cette semaine (impact immédiat)

#### 1. MCP live data (~2-3 jours)
**Problème** : Xenito répond avec des données mockées hardcodées dans `orchestrator/src/llm_client/mock.rs`.  
**Ce qu'il faut faire** :
- Brancher l'orchestrateur sur les vrais endpoints MCP au lieu du mock keyword-based
- `mcp-crm` (`:19001`) expose déjà les tools → l'orchestrateur doit les appeler via HTTP
- Fichiers clés :
  - `orchestrator/src/llm_client/mock.rs` — remplacer par vraie couche HTTP vers MCP
  - `orchestrator/src/api/chat.rs` — pipeline SSE
  - `mcp/mcp-crm/src/` — endpoints déjà opérationnels

#### 2. CI/CD GitHub Actions minimal (~1 jour)
**Ce qu'il faut faire** :
- `.github/workflows/ci.yml` : lint + `pytest` backend + `next build` sur chaque push/PR
- Évite qu'un push casse le build sans qu'on le sache

---

### 🟠 Sprint 2 — Semaine suivante

#### 3. RAG pipeline end-to-end (~2 jours)
**Problème** : upload UI fonctionne, indexation pgvector non câblée jusqu'à Xenito.  
**Ce qu'il faut faire** :
- `rag/app/routers/ingest.py` → déclenché depuis l'upload frontend
- Orchestrateur doit interroger RAG avant de répondre si document pertinent
- Xenito doit pouvoir répondre à `"que dit mon contrat NovaTech ?"`

#### 4. CRUD CRM depuis l'UI (~3 jours)
**Problème** : CRM en lecture seule côté UI.  
**Ce qu'il faut faire** :
- Modal "Nouveau contact" + "Nouveau deal"
- Edit inline dans le tableau contacts
- Endpoints backend déjà partiellement là (`POST /crm/contacts`)

---

### 🟡 Sprint 3 — Après

| Axe | Effort | Impact |
|---|---|---|
| Playwright E2E (login→chat→CRUD) | 2j | Stabilité |
| Observabilité OTEL + coûts Groq | 2j | Ops |
| Notifications temps réel (WebSocket) | 1j | UX |
| Mobile responsiveness | 1j | Accessibilité |
| Onboarding / register flow complet | 1j | Produit |

---

## Fichiers à regarder en premier demain

```
orchestrator/src/llm_client/mock.rs     ← remplacer le mock par HTTP MCP
orchestrator/src/api/chat.rs            ← pipeline SSE
mcp/mcp-crm/src/main.py                 ← tools déjà exposés
.github/workflows/                      ← à créer (CI/CD)
```

---

## Git — état de la branche

```
main (origin/main) — HEAD à jour
  55ab8e6  merge: feat/ux-venise-cyber-gothique → main
  970d0aa  docs: README v1
  6c7e6dd  feat(frontend): Venetian Cyber-Gothic UI v1

Branche locale conservée : feat/ux-venise-cyber-gothique (peut être supprimée)
Fichiers non commités : backend/app/auth/router.py|schemas.py|main.py (en cours)
```

---

*Bonne nuit — on reprend sur le MCP live data.*
