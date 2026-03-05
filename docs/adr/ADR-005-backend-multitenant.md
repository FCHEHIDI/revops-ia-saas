# ADR-005 : Isolation multi-tenant stricte dans le Backend

- **Date** : 2026-03-05
- **Statut** : Accepté
- **Décideurs** : Architecte Système

---

## Contexte

Le projet est un **SaaS multi-tenant** : plusieurs organisations (tenants) utilisent la même infrastructure applicative, mais leurs données doivent être rigoureusement isolées. Une fuite de données entre tenants est un incident critique de sécurité et de conformité (RGPD, SOC2).

Les modèles d'isolation multi-tenant en base de données sont classiquement au nombre de trois :

1. **Base de données par tenant** : isolation maximale, coût opérationnel maximal
2. **Schéma par tenant** (PostgreSQL schemas) : bonne isolation, migrations complexes
3. **Table partagée avec `tenant_id`** : isolation logique via Row-Level Security (RLS)

Par ailleurs, le système distribué (Backend API + Orchestrateur + MCP + RAG) requiert que l'identité du tenant soit propagée de manière sécurisée à chaque composant, sans possibilité de contournement.

---

## Décision

**L'isolation multi-tenant repose sur Row-Level Security (RLS) PostgreSQL combiné à des scopes JWT portant l'`org_id` et les permissions, avec un middleware d'isolation systématique dans le Backend API.**

### Modèle de données multi-tenant

**Structure des tables :**
- Toutes les tables métier incluent une colonne `tenant_id UUID NOT NULL`
- Index composite `(tenant_id, id)` sur toutes les tables pour les performances
- Contrainte de clé étrangère vers la table `organizations`

**Row-Level Security (RLS) :**
```sql
-- Activation RLS sur chaque table
ALTER TABLE deals ENABLE ROW LEVEL SECURITY;

-- Politique de lecture
CREATE POLICY tenant_isolation_select ON deals
  FOR SELECT
  USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Politique d'écriture
CREATE POLICY tenant_isolation_insert ON deals
  FOR INSERT
  WITH CHECK (tenant_id = current_setting('app.current_tenant_id')::uuid);
```

La variable de session `app.current_tenant_id` est positionnée par le Backend API à chaque connexion, avant toute requête.

### Token JWT

**Structure du payload JWT :**
```json
{
  "sub": "user_uuid",
  "org_id": "tenant_uuid",
  "email": "user@company.com",
  "roles": ["admin", "sales_rep"],
  "permissions": ["deals:read", "deals:write", "analytics:read"],
  "iat": 1741132800,
  "exp": 1741219200
}
```

- L'`org_id` est signé dans le JWT et ne peut pas être falsifié sans la clé secrète
- Les permissions sont granulaires par ressource et action
- La durée de vie est courte (24h) avec refresh token

### Middleware d'isolation Backend API

```python
@app.middleware("http")
async def tenant_isolation_middleware(request: Request, call_next):
    # Extraction et validation du JWT
    token = extract_bearer_token(request)
    payload = verify_jwt(token)  # lève une exception si invalide

    # Injection du tenant_id dans le contexte de la requête
    request.state.tenant_id = payload["org_id"]
    request.state.user_id = payload["sub"]
    request.state.permissions = payload["permissions"]

    # Propagation dans la session DB
    async with get_db_session() as db:
        await db.execute(
            "SELECT set_config('app.current_tenant_id', $1, true)",
            [str(request.state.tenant_id)]
        )

    return await call_next(request)
```

### Propagation du tenant_id aux services downstream

- **Orchestrateur LLM** : `tenant_id` transmis dans le payload de la requête (authentifié par secret inter-service)
- **Serveurs MCP** : `tenant_id` dans chaque appel MCP, validé par le serveur
- **Couche RAG** : namespace de recherche = `f"tenant_{tenant_id}"` — impossible de déborder sur un autre tenant
- **Queue** : chaque job contient `tenant_id` dans ses métadonnées, visible dans les logs

---

## Alternatives considérées

### Base de données par tenant
- **Description** : chaque organisation a sa propre instance PostgreSQL (ou base de données dédiée)
- **Rejeté** :
  - Coût opérationnel prohibitif à l'échelle : 1000 tenants = 1000 bases à sauvegarder, monitorer, migrer
  - Migrations difficiles : chaque migration de schéma doit être appliquée à toutes les bases
  - Ressources gaspillées : la plupart des bases seraient sous-utilisées
  - Complexité du connection pooling : PgBouncer ou similaire ne peut pas pooler efficacement des bases séparées
  - **Cas d'usage** : réservé aux clients enterprise avec exigences de conformité strictes (option possible à terme)

### Schéma PostgreSQL par tenant
- **Description** : chaque tenant a son propre schéma (`tenant_abc.deals`, `tenant_xyz.deals`)
- **Rejeté** :
  - Migrations complexes : `alembic` et les ORMs gèrent mal les migrations multi-schémas
  - Requêtes cross-tenant (analytics globaux pour l'opérateur) nécessitent des vues complexes
  - Performance du `search_path` lors du switching de schéma
  - Le nombre de schémas PostgreSQL a des limites pratiques (~1000 schémas recommandés max)

### Filtrage uniquement applicatif (sans RLS)
- **Description** : chaque requête ORM inclut `WHERE tenant_id = :tenant_id` dans le code applicatif
- **Rejeté** :
  - Risque d'oubli d'un filtre dans une nouvelle requête — erreur humaine inévitable
  - Pas de defense-in-depth : si le middleware est bypassé, les données sont accessibles
  - Le RLS est une garantie au niveau base de données, indépendante du code applicatif

---

## Conséquences

### Positives
- **Defense-in-depth** : même si le middleware applicatif est contourné, le RLS PostgreSQL garantit l'isolation au niveau DB
- **Simplicité des migrations** : une seule base de données, une seule migration Alembic pour tous les tenants
- **Performances** : le connection pooling (PgBouncer) fonctionne normalement sur une base unique
- **Auditabilité** : les logs PostgreSQL permettent de tracer toutes les requêtes par tenant
- **Conformité** : le RLS est une approche reconnue et auditée (SOC2, RGPD)

### Négatives / Risques
- **Complexité des requêtes** : chaque requête doit être consciente du `tenant_id`. Les requêtes ORM mal construites peuvent contourner le RLS si le `set_config` n'est pas positionné.
- **Performance sous charge mixte** : sur une table avec des centaines de millions de lignes et des milliers de tenants, le RLS ajoute un overhead de filtrage. Les index sur `(tenant_id, ...)` sont critiques.
- **Erreurs de configuration RLS** : une politique RLS mal rédigée peut soit être trop permissive, soit bloquer des accès légitimes. Tests d'isolation requis en CI.
- **Migrations sensibles** : certaines migrations (ajout de colonnes, index) sur des tables très volumineuses nécessitent des `CONCURRENTLY` et une planification minutieuse.

### Neutres
- L'approche RLS est compatible avec une future option "base dédiée" pour les clients enterprise : il suffit de déployer une instance séparée pour ce tenant
- Les analytics globaux (métriques SaaS, usage par tenant) peuvent être faits via un rôle DB super-admin sans RLS, distinct du rôle applicatif
