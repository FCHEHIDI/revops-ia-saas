# Plan du 2 mai 2026

## Contexte

Au 1er mai 2026, les 4 MCPs Rust (billing, analytics, sequences, filesystem) sont
**codés mais non buildables offline** (sqlx macros compilent contre une vraie DB).
L'orchestrateur ne connaît que les 12 outils mcp-crm.
Tous les services démarrent correctement avec Docker Desktop actif.

---

## P0 — Débloquer les builds Rust MCPs (matin)

**Objectif : tous les MCPs compilent en CI sans DB live.**

Docker Desktop doit être démarré avant de commencer.

```bash
cd mcp/mcp-billing
DATABASE_URL=postgresql://revops:revops@localhost:5433/revops cargo sqlx prepare

cd ../mcp-analytics
DATABASE_URL=postgresql://revops:revops@localhost:5433/revops cargo sqlx prepare

cd ../mcp-sequences
DATABASE_URL=postgresql://revops:revops@localhost:5433/revops cargo sqlx prepare

cd ../mcp-filesystem
DATABASE_URL=postgresql://revops:revops@localhost:5433/revops cargo sqlx prepare
```

Puis vérifier que le build offline fonctionne :

```bash
SQLX_OFFLINE=true cargo build
```

Committer les répertoires `.sqlx/` générés dans chaque MCP.

---

## P1 — Câbler les 4 MCPs dans l'orchestrateur (milieu de journée)

**Fichier cible** : `orchestrator/src/context/builder.rs`, fonction `default_tool_definitions()`.

### mcp-billing — 8 outils à ajouter

```
mcp_billing__get_invoice
mcp_billing__list_invoices
mcp_billing__list_overdue_payments
mcp_billing__get_subscription
mcp_billing__check_subscription_status
mcp_billing__update_subscription_status
mcp_billing__get_customer_billing_summary
mcp_billing__get_mrr
```

### mcp-analytics — 9 outils à ajouter

```
mcp_analytics__get_pipeline_metrics
mcp_analytics__get_deal_velocity
mcp_analytics__get_funnel_analysis
mcp_analytics__get_mrr_trend
mcp_analytics__forecast_revenue
mcp_analytics__get_rep_performance
mcp_analytics__get_team_leaderboard
mcp_analytics__get_activity_metrics
mcp_analytics__compute_churn_rate
mcp_analytics__get_at_risk_accounts
```

### mcp-sequences — 11 outils à ajouter

```
mcp_sequences__create_sequence
mcp_sequences__update_sequence
mcp_sequences__delete_sequence
mcp_sequences__get_sequence
mcp_sequences__list_sequences
mcp_sequences__enroll_contact
mcp_sequences__unenroll_contact
mcp_sequences__list_enrollments
mcp_sequences__pause_sequence
mcp_sequences__resume_sequence
mcp_sequences__get_sequence_performance
```

### mcp-filesystem — à lire dans `mcp/mcp-filesystem/src/http.rs` avant d'ajouter

---

## P1 — History pruning dans le context builder (après-midi)

**Fichier cible** : `orchestrator/src/context/builder.rs`, remplacement du `take(6)`.

Stratégie : budget de caractères (~12 000 chars ≈ 3 000 tokens).
Garder les messages les plus récents, élaguer les plus anciens en premier.

```rust
// Avant
let history: Vec<_> = history.into_iter().rev().take(6).rev().collect();

// Après (budget chars)
const HISTORY_CHAR_BUDGET: usize = 12_000;
let history = prune_history_by_budget(history, HISTORY_CHAR_BUDGET);
```

Ajouter un test unitaire dans `orchestrator/tests/` qui valide la troncature.

---

## P2 — Commit et push de tout (fin de journée)

```bash
# Frontend proxy + BACKEND_URL fixes
git add frontend/next.config.ts frontend/src/lib/api.ts frontend/src/lib/auth.ts
git commit -m "fix(frontend): Next.js API proxy rewrite + correct BACKEND_URL defaults"

# MCPs sqlx offline
git add mcp/mcp-billing/.sqlx mcp/mcp-analytics/.sqlx mcp/mcp-sequences/.sqlx mcp/mcp-filesystem/.sqlx
git commit -m "build(mcp): add sqlx offline snapshots for all Rust MCPs"

# Orchestrateur câblage + pruning
git add orchestrator/src/context/builder.rs
git commit -m "feat(orchestrator): wire billing/analytics/sequences/filesystem tools + history char-budget pruning"

git push
```

---

## Rappels techniques critiques

- Docker Desktop doit être démarré avant `cargo sqlx prepare` ET avant uvicorn
- `get_current_user` → importer de `app.dependencies`, PAS de `app.auth.dependencies`
- System Python (`Python311`) fait tourner uvicorn — `.venv` est incomplet (pas de `pydantic_settings`)
- `parse_tool_name()` splitte `mcp_billing__get_invoice` → prefix=`mcp_billing`, tool=`get_invoice`
- `resolve_server_url()` dans `mcp_client/mod.rs` reconnaît déjà tous les prefixes
- FastAPI 0.115 : DELETE 204 → `response_model=None, response_class=Response`
- Test user : `admin@demo.io` / `Demo1234!` (tenant_id: `6cb9d763-d846-427b-b05c-3d7068cfc532`)
