# ADR-010 : Architecture Multi-MCP avec RAG et Filesystem

- **Date** : 2026-04-30
- **Statut** : Accepté
- **Décideurs** : Architecte Système
- **Concerne** : ADR-001 (Rust pour MCP), ADR-004 (RAG), ADR-007 (monorepo), ADR-008 (MCP CRM)

---

## Contexte

La Phase 3 du projet RevOps IA SaaS ajoute deux nouveaux serveurs MCP :

1. **`mcp-filesystem`** (Rust/Axum, port 19005) : gestion des documents, playbooks et rapports avec stockage local et intégration RAG.
2. **`mcp-billing`** (Rust, port 19002), **`mcp-analytics`** (Rust, port 19003), **`mcp-sequences`** (Rust, port 19004) : MCPs métier précédemment créés.
3. **`rag`** (Python/FastAPI, port 18500) : service d'indexation vectorielle et de recherche sémantique.

Trois décisions architecturales structurantes ont émergé :

1. **Transport MCP** : stdio (ADR-001) vs HTTP pour les MCPs à fort trafic
2. **Intégration RAG** : comment connecter les MCPs au service d'embeddings Qdrant
3. **Authentification inter-services** : sécurisation des appels internes

---

## Décisions

### 1. Migration mcp-filesystem vers transport HTTP

**Décision** : `mcp-filesystem` utilise un transport HTTP natif (Axum) plutôt que stdio.

**Justification** :
- Les opérations de fichiers impliquent des payloads larges (contenu de documents) incompatibles avec stdio
- Le proxy backend peut router via `POST /tools/call` sans processus enfant
- Permet le health check (`GET /health`) et la scalabilité horizontale

**Conséquence** : Le backend FastAPI expose `/api/v1/filesystem/call` et `/api/v1/filesystem/health` via son proxy MCP générique.

### 2. Pattern d'intégration RAG depuis les MCPs

**Décision** : `mcp-filesystem` appelle directement le service RAG (`http://localhost:18500`) via un `RagClient` Rust (reqwest).

**Justification** :
- Découplage : le MCP ne connaît pas Qdrant, uniquement l'API RAG (`/ingest`, `/search`)
- Async par design : l'ingestion est mise en file d'attente Redis (retour immédiat avec `job_id`)
- La recherche est synchrone et renvoie des chunks avec scores de similarité

**Interface** :
```
POST /ingest  → { namespace, document_id, content, ... } → { job_id, status: "queued" }
POST /search  → { namespace, query, top_k }              → { results: [{ content, score }] }
```

### 3. Authentification inter-services par header statique

**Décision** : Tous les appels internes (backend→MCP, MCP→RAG) utilisent le header `X-Internal-Api-Key` avec un secret partagé (`INTER_SERVICE_SECRET` / `INTERNAL_API_KEY`).

**Justification** :
- Simple à implémenter et auditer
- Suffisant pour un environnement de développement local
- Cohérent avec le pattern existant sur mcp-crm et le backend

**Limite** : En production, remplacer par mTLS ou tokens JWT à courte durée de vie.

### 4. Démarrage du service RAG avec `USE_TF=0 TRANSFORMERS_NO_TF=1`

**Décision** : Le service RAG démarre avec les variables d'environnement `USE_TF=0` et `TRANSFORMERS_NO_TF=1` pour forcer PyTorch et éviter les conflits Keras 3.

**Justification** :
- `sentence-transformers` utilise PyTorch nativement
- `transformers` tente d'importer TensorFlow si disponible, échoue avec Keras 3
- Solution: désactiver TF au niveau des env vars, sans modifier les dépendances

---

## Conséquences

### Positives
- Architecture cohérente : tous les MCPs en Rust (sauf mcp-crm en Python pour DB access)
- Service RAG découplé et réutilisable par tous les MCPs
- Pipeline E2E validé : `upload_report` → ingestion async → `search_documents` → résultats vectoriels
- 28 tests backend passent, 4 xfailed attendus (RLS user non-superuser)

### Négatives
- Le service RAG doit être démarré séparément (pas dans docker-compose.dev.yml à ce stade)
- `USE_TF=0` est un contournement — idéalement géré par un virtualenv dédié
- La recherche depuis `search_documents` cherche dans le namespace global du tenant, pas uniquement les documents uploadés via `upload_report`

### Neutres
- Qdrant tourne en Docker (`revops-dev-qdrant`, port 6333)
- Collections per-tenant : `tenant_{uuid}`
- Modèle d'embedding : `all-MiniLM-L6-v2` (384 dimensions, CPU)

---

## Alternatives écartées

| Alternative | Raison du rejet |
|---|---|
| MCP filesystem en Python | Cohérence avec l'écosystème Rust existant |
| Appel Qdrant direct depuis Rust | Couplage fort, duplique la logique d'embedding |
| Redis pub/sub pour l'ingestion | BLPOP sur liste Redis suffit pour le volume actuel |
| JWT pour inter-services | Surcharge opérationnelle inutile en dev |
