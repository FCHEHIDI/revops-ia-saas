# mcp-analytics

Serveur MCP **read-only** pour les métriques et le reporting RevOps.

Expose 10 tools couvrant le pipeline, la vélocité, la prévision de revenue, le churn, les performances des reps, et les métriques d'activité.

---

## Architecture

```
src/
├── main.rs          — point d'entrée, transport stdio/SSE
├── server.rs        — AnalyticsServer : list_tools + call_tool
├── config.rs        — Config depuis variables d'environnement
├── db.rs            — create_pool + validate_tenant (RLS)
├── audit.rs         — write_audit (INSERT dans audit_events)
├── errors.rs        — AnalyticsError (TenantForbidden, ValidationError, …)
├── schemas.rs       — tous les types d'output partagés
└── tools/
    ├── pipeline.rs   — get_pipeline_metrics, get_deal_velocity, get_funnel_analysis
    ├── revenue.rs    — forecast_revenue, get_mrr_trend
    ├── churn.rs      — compute_churn_rate, get_at_risk_accounts
    ├── performance.rs — get_rep_performance, get_team_leaderboard
    └── activity.rs   — get_activity_metrics
```

---

## Contraintes de sécurité

| Règle | Implémentation |
|-------|---------------|
| Read-only | Aucun `INSERT`/`UPDATE`/`DELETE` sauf `audit_events` |
| Isolation tenant | `validate_tenant()` **en premier** dans chaque handler — retourne `TenantForbidden` (403) si tenant inactif ou inexistant |
| RLS PostgreSQL | `set_config('app.current_tenant_id', ...)` positionné après validation |
| Audit log | `write_audit()` après chaque appel ; erreur d'audit loggée mais non propagée |
| Validation des entrées | `ValidationError` sur `forecast_months > 12`, `risk_threshold` hors [0,1], valeurs enum invalides |

---

## Variables d'environnement

| Variable | Obligatoire | Défaut | Description |
|----------|------------|--------|-------------|
| `DATABASE_URL` | ✅ | — | URL PostgreSQL (ex. `postgres://user:pass@host/db`) |
| `MCP_TRANSPORT` | ❌ | `stdio` | `stdio` ou `sse` |
| `SSE_BIND_ADDR` | ❌ | `0.0.0.0:3003` | Adresse d'écoute en mode SSE |
| `LOG_LEVEL` | ❌ | `info` | Niveau de log `tracing` |

---

## Tools

### `get_pipeline_metrics`

Permission requise : `analytics:pipeline:read`

Métriques agrégées sur une période : taux de conversion par stage, win rate, cycle moyen, revenue généré.

**Input**

| Champ | Type | Requis | Description |
|-------|------|--------|-------------|
| `tenant_id` | UUID | ✅ | Identifiant organisation |
| `user_id` | UUID | ✅ | Utilisateur appelant |
| `period_start` | date | ✅ | Début de période (YYYY-MM-DD) |
| `period_end` | date | ✅ | Fin de période (YYYY-MM-DD) |
| `assigned_to` | UUID | ❌ | Filtrer sur un commercial |
| `include_closed` | bool | ❌ | Inclure les deals fermés |

**Output** : `GetPipelineMetricsOutput` — voir `schemas.rs`

**Erreurs** : `TenantForbidden`, `DatabaseError`

---

### `get_deal_velocity`

Permission requise : `analytics:pipeline:read`

Score de vélocité = `deals_won × win_rate × avg_value / avg_cycle_days`, avec tendance (increasing/decreasing/stable) et ventilation optionnelle.

**Input**

| Champ | Type | Requis | Description |
|-------|------|--------|-------------|
| `tenant_id` | UUID | ✅ | |
| `user_id` | UUID | ✅ | |
| `period_start` | date | ✅ | |
| `period_end` | date | ✅ | |
| `breakdown_by` | string | ❌ | `"stage"` \| `"rep"` \| `"segment"` |

**Erreurs** : `TenantForbidden`, `ValidationError` (breakdown_by invalide), `DatabaseError`

---

### `get_funnel_analysis`

Permission requise : `analytics:pipeline:read`

Analyse complète du funnel : nombre d'entrées/sorties par stage, taux de conversion, temps moyen, identification du bottleneck.

**Input** : `tenant_id`, `user_id`, `period_start`, `period_end`

**Output** : `GetFunnelAnalysisOutput` — stages ordonnés + `overall_conversion` + `bottleneck_stage`

---

### `forecast_revenue`

Permission requise : `analytics:revenue:read`

Prévision mensuelle jusqu'à 12 mois selon trois modèles :

| Modèle | Formule |
|--------|---------|
| `weighted_pipeline` | `SUM(deal.value × probability)` ventilé par mois |
| `conservative` | `weighted_pipeline × 0.7` |
| `linear_trend` | Régression linéaire sur les 6 derniers mois de revenue réel |

**Input**

| Champ | Type | Requis | Description |
|-------|------|--------|-------------|
| `forecast_months` | u8 | ✅ | 1–12 (erreur si > 12) |
| `model` | string | ✅ | voir tableau ci-dessus |
| `include_existing_mrr` | bool | ✅ | Ajouter le MRR courant au forecast |
| `assigned_to` | UUID | ❌ | Filtrer sur un commercial |

**Erreurs** : `TenantForbidden`, `ValidationError` (forecast_months > 12, model invalide), `DatabaseError`

---

### `get_mrr_trend`

Permission requise : `analytics:revenue:read`

Tendance MRR sur N mois : MRR, new MRR, churned MRR, net new MRR, croissance MoM.

**Input** : `tenant_id`, `user_id`, `months` (défaut 12, max 24)

---

### `compute_churn_rate`

Permission requise : `analytics:churn:read`

Churn client (`customer`) ou churn revenue (`revenue`) sur une période, avec NRR et GRR.

| Type | Formule |
|------|---------|
| `customer` | `clients perdus / clients en début de période` |
| `revenue` | `MRR churné / MRR début de période` |

**NRR** = `(MRR_start - MRR_churned + MRR_expansion) / MRR_start`

**Erreurs** : `TenantForbidden`, `ValidationError` (churn_type invalide), `DatabaseError`

---

### `get_at_risk_accounts`

Permission requise : `analytics:churn:read`

Comptes à risque selon un score composite [0–1] :

| Signal | Poids max |
|--------|-----------|
| Inactivité (≥ 90 jours) | 0.40 |
| Factures impayées (×0.15 / facture) | 0.45 |
| Factures en retard (×0.20 / facture) | 0.40 |

**Input**

| Champ | Type | Défaut |
|-------|------|--------|
| `risk_threshold` | f32 | `0.6` |
| `limit` | u32 | `50` |

**Erreurs** : `TenantForbidden`, `ValidationError` (threshold hors [0,1]), `DatabaseError`

---

### `get_rep_performance`

Permission requise : `analytics:performance:read`

Performance individuelle d'un commercial : deals gagnés, revenue, quota attainment, avg deal size, cycle moyen, activités, pipeline coverage.

`quota_attainment = revenue_generated / quota` (quota depuis table `quotas` ou 100 000 € par défaut)

`pipeline_coverage = open_pipeline / quota_restant`

**Erreurs** : `TenantForbidden`, `DatabaseError`

---

### `get_team_leaderboard`

Permission requise : `analytics:performance:read`

Classement de l'équipe selon `revenue`, `deals_won` ou `activities`.

**Input** : `period_start`, `period_end`, `metric`, `limit` (max 100)

**Erreurs** : `TenantForbidden`, `ValidationError` (metric invalide), `DatabaseError`

---

### `get_activity_metrics`

Permission requise : `analytics:activity:read`

Total des activités, ventilation par type avec pourcentages, et tendance journalière.

**Input** : `period_start`, `period_end`, `rep_id?`, `activity_type?`

---

## Tables PostgreSQL utilisées (lecture seule)

| Table | Usage |
|-------|-------|
| `organizations` | Validation tenant (active = true) |
| `deals` | Pipeline, velocity, funnel, forecast, performance |
| `activities` | Métriques d'activité, performance rep |
| `accounts` | Comptes à risque |
| `subscriptions` | MRR trend, churn rate, forecast MRR |
| `invoices` | Score de risque (impayées / en retard) |
| `users` | Noms des reps pour leaderboard |
| `quotas` | Quota attainment (fallback 100k) |
| `audit_events` | **ÉCRITURE uniquement** — log de chaque appel |
