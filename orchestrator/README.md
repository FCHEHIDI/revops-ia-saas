# orchestrator — LLM Orchestrator (Rust)

Orchestrateur LLM stateless du projet RevOps IA SaaS.

Reconstruit le contexte à chaque requête (session + RAG + MCP), sélectionne le modèle,
gère le routing, les appels parallèles MCP, et streame la réponse via SSE.

## Stack

- **Langage** : Rust 2021
- **Runtime async** : Tokio 1.x
- **Framework MCP** : rmcp (Rust MCP SDK)
- **HTTP** : reqwest (async), axum (server)
- **Sérialisation** : serde + serde_json
- **Observabilité** : tracing + tracing-opentelemetry
- **Erreurs** : anyhow + thiserror

## Structure

```
src/
├── main.rs             # Point d'entrée, démarrage du serveur axum
├── server.rs           # Routes HTTP : POST /process (SSE), GET /health
├── config.rs           # Configuration (env vars, URLs services)
├── errors.rs           # Types d'erreurs (OrchestratorError)
├── schemas.rs          # Types partagés (OrchestratorRequest, OrchestratorResponse)
├── context/            # Reconstruction du contexte à chaque requête
│   ├── mod.rs
│   ├── builder.rs      # ContextBuilder : assemble session + RAG + MCP
│   └── session.rs      # Récupération de l'historique de session
├── routing/            # Sélection du modèle LLM et routing
│   ├── mod.rs
│   └── router.rs       # ModelRouter : choisit le modèle selon la requête
├── mcp_client/         # Client pour appels aux serveurs MCP
│   ├── mod.rs
│   └── client.rs       # McpClient : appels parallèles aux tools MCP
├── rag_client/         # Client pour la couche RAG
│   ├── mod.rs
│   └── client.rs       # RagClient : retrieval des extraits pertinents
├── llm_client/         # Client pour les appels LLM (OpenAI / Anthropic)
│   ├── mod.rs
│   └── client.rs       # LlmClient : streaming de la réponse
└── queue/              # Production de jobs vers la queue Redis
    ├── mod.rs
    └── producer.rs     # QueueProducer : enqueue des jobs LLM
tests/
└── integration/        # Tests d'intégration de bout en bout
```

## Variables d'environnement

Copier `.env.example` → `.env` et renseigner les valeurs.

## Build

```bash
cargo build --release
```

## Relations avec les autres composants

- Reçoit les requêtes du **Backend API** via HTTP interne (authentifiées par secret inter-service)
- Appelle les **serveurs MCP** via le protocole rmcp
- Appelle la **couche RAG** via HTTP (FastAPI)
- Enqueué dans **Redis** pour le traitement par les workers LLM
- Streame la réponse au **Backend API** via SSE
