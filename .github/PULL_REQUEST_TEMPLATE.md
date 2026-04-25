## Description

<!-- Décris le changement apporté et le problème résolu. Explique le "pourquoi", pas le "comment". -->

Closes #<!-- numéro de l'issue liée -->

---

## Type de changement

<!-- Coche la case correspondante -->

- [ ] `feat` — Nouvelle fonctionnalité
- [ ] `fix` — Correction de bug
- [ ] `hotfix` — Correctif urgent (production)
- [ ] `refactor` — Refactoring sans changement de comportement
- [ ] `chore` — Maintenance (dépendances, config, tooling)
- [ ] `docs` — Documentation uniquement
- [ ] `ci` — Modifications CI/CD
- [ ] `perf` — Amélioration de performance
- [ ] `test` — Ajout ou modification de tests uniquement

---

## Composant(s) modifié(s)

<!-- Coche tous les composants touchés par cette PR -->

- [ ] `backend/` — FastAPI multi-tenant
- [ ] `frontend/` — Next.js
- [ ] `orchestrator/` — LLM Orchestrator (Rust)
- [ ] `mcp/mcp-crm`
- [ ] `mcp/mcp-billing`
- [ ] `mcp/mcp-analytics`
- [ ] `mcp/mcp-sequences`
- [ ] `mcp/mcp-filesystem`
- [ ] `rag/` — RAG Layer
- [ ] `infra/` — Infrastructure
- [ ] `.github/` — CI/CD workflows
- [ ] `docs/` — Documentation / ADR

---

## Checklist technique

### Qualité du code
- [ ] Le code compile et passe les tests en local (`cargo test` / `pytest` / `npm run build`)
- [ ] Le lint passe sans erreur (`cargo clippy` / `ruff` + `mypy` / `eslint`)
- [ ] Le code est formaté (`cargo fmt` / `black` / `prettier`)
- [ ] Aucune variable, import ou fonction inutile laissés dans le code
- [ ] Les fonctions et types complexes sont commentés (intent, pas implémentation)

### Tests
- [ ] Des tests unitaires couvrent les nouveaux comportements
- [ ] Les tests existants ne régressent pas
- [ ] La coverage ne descend pas sous le seuil (80% Python / 70% Rust)

### Sécurité
- [ ] Aucune credential, token, clé API ou secret commité (même en exemple)
- [ ] Le `tenant_id` est validé à chaque point d'entrée multi-tenant (MCP, Backend, RAG)
- [ ] Les entrées utilisateur sont validées (Pydantic, serde, Zod)
- [ ] Les nouvelles dépendances ne contiennent pas de vulnérabilités connues

### Base de données (si applicable)
- [ ] Une migration Alembic est fournie pour les changements de schéma
- [ ] La migration est réversible (`downgrade` implémenté)
- [ ] Les index nécessaires sont créés
- [ ] Le RLS (Row-Level Security) est maintenu pour les nouvelles tables

### API / Contrats d'interface (si applicable)
- [ ] Les breaking changes sont documentés et bumpent la version MAJOR
- [ ] Les nouveaux endpoints sont documentés (docstring FastAPI / OpenAPI)
- [ ] La rétro-compatibilité est maintenue pour les changements non-breaking

### CI/CD (si applicable)
- [ ] Les nouvelles dépendances de workflow utilisent des versions fixées (pas `@latest`)
- [ ] Aucun secret n'est exposé en clair dans les workflows
- [ ] Les permissions des workflows sont minimales (principle of least privilege)

---

## Screenshots / Captures (si UI)

<!-- Ajouter des captures d'écran avant/après pour les changements frontend -->

---

## Notes pour les reviewers

<!-- Informations supplémentaires pour faciliter la review : points d'attention, décisions de design, alternatives considérées -->
