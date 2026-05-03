# Next Features — RevOps IA SaaS

Classées par ROI (valeur métier / effort de développement).

---

## 1. Email Delivery pour les Sequences ⚡ (P0 produit)

**Pourquoi** : les sequences existent mais n'envoient rien — c'est la fonctionnalité principale
d'un outil RevOps sales. Sans email réel, c'est une base de données de brouillons.

**Ce qu'on construit** :
- Intégration Resend ou SendGrid dans `mcp-sequences`
- Outil MCP `send_step_email(sequence_id, contact_id, step_index)`
- Worker Redis qui dépile les envois planifiés
- Tracking ouvertures via pixel 1×1 (URL `GET /track/{uuid}` → backend → update `opened_at`)
- Tracking clics via redirect `GET /click/{uuid}?url=...` → backend → update `clicked_at`

**Tables** :
```sql
email_sends(id, tenant_id, sequence_id, contact_id, step_index, sent_at, opened_at, clicked_at, status)
```

**Valeur** : transforme les sequences en produit concret et mesurable.

---

## 2. Webhooks sortants (P0 intégrations)

**Pourquoi** : les clients ont déjà des outils (Slack, Zapier, n8n, HubSpot, Stripe).
Les webhooks permettent de s'insérer dans leur workflow sans migration.

**Ce qu'on construit** :
- Table `webhook_endpoints(tenant_id, event_type, url, secret, active)`
- Events supportés : `deal.won`, `deal.lost`, `contact.created`, `invoice.overdue`, `sequence.completed`
- Worker Redis qui consomme les events et appelle les URLs configurées
- HMAC-SHA256 sur le payload (header `X-Revops-Signature`)
- UI de configuration dans le dashboard (CRUD endpoints + logs des derniers appels)

**Valeur** : intégration native dans l'écosystème du client → réduction du churn.

---

## 3. AI Lead Scoring (P1 différenciation)

**Pourquoi** : l'orchestrateur a déjà accès aux données CRM, billing et analytics.
Le scoring est la killer feature IA d'un RevOps tool.

**Ce qu'on construit** :
- Outil MCP `score_lead(contact_id)` dans `mcp-crm` ou `mcp-analytics`
- Agrégation : firmographie (taille entreprise, secteur), engagement (emails ouverts, clics),
  historique deals (nb deals, valeur, durée cycle), tenure (ancienneté comme client)
- LLM génère un score 0–100 + explication en langage naturel
- Score mis en cache avec TTL 24h, recalculé sur event (nouveau deal, email ouvert, etc.)
- Badge score visible sur la fiche contact dans le CRM frontend

**Valeur** : les sales reps savent sur quels leads se concentrer → conversion améliorée.

---

## 4. Timeline d'activité par entité CRM (P1 rétention)

**Pourquoi** : avant chaque appel, le commercial a besoin d'un historique complet.
Vue 360° = argument de rétention fort.

**Ce qu'on construit** :
- Table `activities(tenant_id, entity_type, entity_id, actor_id, type, payload JSONB, created_at)`
- Types : `email_sent`, `email_opened`, `deal_created`, `deal_stage_changed`, `note_added`,
  `sequence_enrolled`, `ai_chat_message`, `invoice_paid`, `invoice_overdue`
- Tous les MCPs publient dans cette table lors des mutations
- Outil MCP `get_activity_timeline(entity_type, entity_id, limit)` dans `mcp-crm`
- Composant React `<ActivityTimeline>` sur les pages contact/account/deal

**Valeur** : vision temps réel de chaque relation client → réduit le temps de préparation des appels.

---

## 5. API Keys publiques (P1 segment developer)

**Pourquoi** : les clients power-user veulent accéder à leurs données programmatiquement.
Ouvre un tier "developer" et facilite les intégrations custom.

**Ce qu'on construit** :
- Table `api_keys(id, tenant_id, key_hash, name, scopes[], last_used_at, expires_at, active)`
- Format : `rk_live_xxxxxxxxxxxx` (32 chars aléatoires, stocké haché bcrypt)
- Middleware FastAPI : `Authorization: Bearer rk_live_xxx` accepté en plus des cookies
- Rate limiting par key via Redis (compteur avec TTL 60s)
- UI de gestion : créer / révoquer des clés, voir `last_used_at`, scopes disponibles
- Scopes : `crm:read`, `crm:write`, `billing:read`, `analytics:read`, `sequences:write`

**Valeur** : intégrations custom sans OAuth complexity → adoption par les équipes techniques.

---

## 6. Playbooks IA (P2 feature flagship)

**Pourquoi** : c'est le cœur d'un vrai outil RevOps — automatiser les workflows de vente
sans code, déclenchés par des events métier.

**Ce qu'on construit** :
- Table `playbooks(tenant_id, name, trigger_event, conditions JSONB, actions JSONB, active)`
- Exemples de triggers : `deal.stale_14d`, `contact.no_activity_7d`, `invoice.overdue`
- Exemples d'actions : `enroll_in_sequence`, `notify_rep`, `update_deal_stage`, `create_task`
- Worker cron Redis (toutes les heures) qui évalue les conditions et exécute les actions
- UI builder visuel (trigger → conditions → actions, style Zapier simplifié)
- L'IA peut suggérer des playbooks à partir d'une description en langage naturel

**Valeur** : automatisation des workflows sales sans code → différenciation majeure vs CRM classiques.

---

## 7. Rapports PDF générés par l'IA (P2 wow factor)

**Pourquoi** : les managers veulent partager des rapports propres. Un bouton "Générer le rapport"
qui produit un PDF professionnel est un argument de vente immédiat.

**Ce qu'on construit** :
- Endpoint `POST /api/v1/reports/generate` → job asynchrone avec ID
- L'orchestrateur appelle les analytics MCPs, agrège les données, génère du Markdown structuré
- Conversion Markdown → PDF via Puppeteer (HTML template + CSS Tailwind)
- Stockage du PDF dans `mcp-filesystem` (lié au tenant)
- SSE de progression (`generating_data` → `rendering` → `done`) + lien de téléchargement
- Types de rapports : Pipeline, MRR, Team Performance, Churn Analysis

**Valeur** : outil de présentation interne → le SaaS est visible dans les réunions des clients.

---

## 8. Usage Metering par tenant (P2 revenue model)

**Pourquoi** : sans metering, impossible de facturer au usage ni de détecter les abus.
Prérequis pour un modèle pay-as-you-go.

**Ce qu'on construit** :
- Middleware orchestrateur qui log tokens LLM consommés après chaque `done` event
- Table `usage_events(tenant_id, event_type, quantity, metadata JSONB, ts)`
- Types trackés : `llm_tokens_input`, `llm_tokens_output`, `mcp_calls`, `emails_sent`, `documents_indexed`
- Flush Redis → PostgreSQL toutes les 5 min via worker background
- Endpoint `GET /api/v1/billing/usage?period=current_month` exposé dans le dashboard
- Alertes configurables : quota 80% → notification SSE → email

**Valeur** : base du modèle de pricing — permet de passer de flat fee à usage-based.

---

## 9. Custom Fields sur les entités CRM (P2 flexibilité)

**Pourquoi** : chaque client B2B a ses propres champs métier (secteur, ICP score, technologie stack...).
Sans custom fields, les clients exportent vers Excel.

**Ce qu'on construit** :
- Colonne `custom_fields JSONB` déjà possible sur contacts/accounts/deals (migration Alembic)
- Table `field_definitions(tenant_id, entity_type, field_key, label, field_type, required, position)`
- Types supportés : `text`, `number`, `date`, `select`, `multi_select`, `boolean`, `url`
- Endpoint CRUD `POST /api/v1/crm/field-definitions`
- UI d'administration dans les settings du tenant
- Les formulaires CRM frontend se génèrent dynamiquement depuis `field_definitions`
- Outil MCP `get_custom_fields_schema(entity_type)` pour que Xenito connaisse le schéma

**Valeur** : adoption par des secteurs verticaux spécifiques (immobilier, SaaS, agences...).

---

## 10. Meeting Notes → RAG (P2 différenciation forte)

**Pourquoi** : les notes de réunion contiennent les vraies informations commerciales.
Rendre ces notes searchables par Xenito est une différenciation claire vs un CRM classique.

**Ce qu'on construit** :
- Upload de notes texte ou audio (Whisper API pour transcription)
- Pipeline : transcription → chunking → embeddings → Qdrant (lié à `entity_id` + `tenant_id`)
- Outil MCP `ingest_meeting_note(content, entity_type, entity_id, meeting_date)` dans `mcp-filesystem`
- Outil MCP `search_meeting_notes(query, entity_id)` retourne les passages pertinents
- Le context builder de l'orchestrateur inclut les meeting notes dans le RAG retrieval
- UI : page "Notes" sur la fiche contact/account avec historique des transcriptions

**Valeur** : Xenito répond à "qu'est-ce qui s'est dit lors du dernier appel avec Acme Corp ?"
→ fonctionnalité qu'aucun CRM classique ne propose nativement.

---

## Ordre d'implémentation recommandé

```
Semaine 1 (2–9 mai)
├── P0 : sqlx prepare + wire 4 MCPs              ← débloque tout
├── P0 : Email delivery sequences                ← produit fonctionnel
└── P1 : Timeline d'activité                     ← rétention

Semaine 2 (12–16 mai)
├── P1 : Lead scoring IA                         ← différenciation
├── P1 : API Keys publiques                      ← segment developer
└── P1 : Webhooks sortants                       ← intégrations

Semaine 3–4 (19–30 mai)
├── P2 : Usage metering                          ← revenue model
├── P2 : Custom fields CRM                       ← flexibilité verticale
├── P2 : Rapports PDF IA                         ← wow factor
└── P2 : Meeting notes RAG                       ← différenciation forte

Mois 2
└── P2 : Playbooks IA                            ← feature flagship
```
