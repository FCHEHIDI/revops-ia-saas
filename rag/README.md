# rag — Couche RAG (Python / FastAPI)

Service de mémoire documentaire long-terme du projet RevOps IA SaaS.

Gère l'ingestion, l'indexation vectorielle et le retrieval des documents par tenant.

## Stack

- **Langage** : Python 3.12
- **Framework API** : FastAPI (ASGI / uvicorn)
- **RAG framework** : LangChain ou LlamaIndex (décision à l'implémentation)
- **Embeddings** : `text-embedding-3-large` (OpenAI) ou `multilingual-e5-large` (open-source)
- **Vector store MVP** : pgvector (extension PostgreSQL)
- **Vector store scale** : Qdrant
- **Queue consumer** : Redis (jobs d'ingestion soumis par mcp-filesystem)

## Structure

```
app/
├── main.py             # Point d'entrée FastAPI, inclusion des routers
├── config.py           # Settings (pydantic-settings, variables d'environnement)
├── dependencies.py     # Dépendances FastAPI (vector store, embedding model)
├── schemas.py          # Modèles Pydantic partagés (IndexRequest, RetrievalRequest)
├── __init__.py
├── indexing/           # Ingestion et indexation des documents
│   ├── chunker.py      # Découpage en chunks (sliding window avec overlap)
│   ├── embedder.py     # Génération des embeddings
│   └── indexer.py      # Router POST /index — stocke les vecteurs
├── retrieval/          # Récupération des extraits pertinents
│   ├── retriever.py    # Router POST /retrieve — recherche par similarité
│   └── reranker.py     # Re-ranking cross-encoder (optionnel)
├── vector_store/       # Abstractions du vector store
│   ├── pgvector.py     # Implémentation pgvector (MVP)
│   └── qdrant.py       # Implémentation Qdrant (scale)
└── queue/              # Consumer des jobs d'ingestion Redis
    └── consumer.py     # Worker Redis BullMQ — consomme les jobs de mcp-filesystem
tests/
└── ...                 # Tests unitaires et d'intégration
```

## Variables d'environnement

Copier `.env.example` → `.env` et renseigner les valeurs.

## Démarrage local

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8002
```

## Endpoints exposés

| Méthode | Route | Description |
|---------|-------|-------------|
| `POST` | `/index` | Indexe un document (chunking + embedding + stockage) |
| `POST` | `/retrieve` | Récupère les K chunks les plus pertinents pour une requête |
| `DELETE` | `/documents/{document_id}` | Supprime tous les chunks d'un document |
| `GET` | `/health` | Health check |

## Isolation multi-tenant

Chaque requête inclut un `tenant_id`. Les vecteurs sont stockés dans un namespace dédié
`tenant_{tenant_id}` — aucune recherche cross-tenant n'est possible.

## Relations avec les autres composants

- Reçoit les jobs d'indexation de **mcp-filesystem** via Redis
- Répond aux requêtes de retrieval de l'**orchestrateur** via HTTP
- Persiste les vecteurs dans **PostgreSQL + pgvector** (MVP)
