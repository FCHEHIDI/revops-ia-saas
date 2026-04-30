# ADR-009 : Mode LLM Mock pour les tests E2E sans clé API

- **Date** : 2026-04-30
- **Statut** : Accepté
- **Décideurs** : Architecte Système

---

## Contexte

Le pipeline de traitement conversationnel de l'orchestrateur implique, à chaque requête, une chaîne complète :

1. Reconstruction du contexte (historique Backend + chunks RAG)
2. Appel LLM (Groq / OpenAI) → décision `tool_call` ou réponse directe
3. Exécution parallèle des outils MCP concernés
4. Second appel LLM avec les résultats des outils → réponse finale
5. Stream SSE vers le Frontend (`token`, `tool_call`, `done`)

Pour valider ce pipeline de bout en bout, deux approches coexistaient :

- **Clé API réelle** (Groq `llama-3.3-70b-versatile`) : consomme du quota, soumise aux rate limits (429 Too Many Requests observé à 12 000 TPM), non reproductible de façon déterministe, impossible dans des environnements CI sans secrets injectés.
- **Tests unitaires isolés** : ne valident pas l'intégration entre l'orchestrateur, les serveurs MCP et le frontend.

Le besoin est un **mode déterministe, sans quota, activable via variable d'environnement**, qui valide le pipeline SSE complet y compris les vrais appels MCP vers la base de données.

---

## Décision

**Introduction d'un `MockProvider` Rust activable via `LLM_MOCK=true`, implémentant le trait `LlmProvider` avec un comportement déterministe à deux tours.**

### Implémentation

**Fichiers modifiés / créés :**

| Fichier | Rôle |
|---|---|
| `orchestrator/src/llm_client/mock.rs` | Implémentation de `MockProvider` |
| `orchestrator/src/llm_client/mod.rs` | Short-circuit dans `create_llm_provider()` |
| `orchestrator/src/config.rs` | Champ `llm_mock: bool` parsé depuis `LLM_MOCK` |

**Trait commun :**

```rust
#[async_trait]
pub trait LlmProvider: Send + Sync {
    async fn complete(&self, messages: &[Message], tools: &[Tool]) -> Result<LlmResponse>;
}
```

Le `MockProvider` implémente ce même trait — aucune modification dans la boucle agentique.

**Logique à deux tours :**

```
Tour 1 (aucun tool_call_id dans messages)
  → FinishReason::ToolCalls
  → tool_call: mcp_crm__search_contacts { tenant_id, limit: 5 }

Tour 2 (tool_call_id présent dans messages)
  → FinishReason::Stop
  → content: texte de synthèse canned
```

**Activation :**

```bash
LLM_MOCK=true ./target/release/orchestrator.exe
```

**Short-circuit dans `create_llm_provider()` :**

```rust
if config.llm_mock {
    tracing::warn!(
        "LLM_MOCK=true — using deterministic MockProvider, no API call will be made"
    );
    return Ok(Arc::new(mock::MockProvider));
}
```

### Comportement observé lors de la validation E2E (2026-04-29)

```
POST /process → agentic loop (iteration 0)
  MockProvider turn 1 → tool_call: mcp_crm__search_contacts
  MCP CRM → Postgres → 80 contacts réels retournés (616 ms)
  MockProvider turn 2 → réponse textuelle

SSE stream :
  data: {"type":"tool_call","tool":"mcp_crm__search_contacts","result":{"items":[...],"total":80}}
  data: {"type":"token","content":"Voici les contacts récupérés depuis le CRM..."}
  data: {"type":"done","usage":{"prompt_tokens":120,"completion_tokens":32,"total_tokens":152}}
```

Le frontend a rendu la `ToolInvocationCard` avec le JSON des contacts CRM, confirmant l'intégration SSE complète.

---

## Alternatives considérées

### Wiremock / Testcontainers stub HTTP
- **Description** : démarrer un serveur HTTP stub qui simule les réponses de l'API Groq
- **Rejeté** : ajoute une dépendance externe (Java/Node), complexifie le setup CI, ne valide pas les vrais appels MCP ni le stream SSE en conditions réelles.

### Feature flag par fichier de config (TOML/YAML)
- **Description** : activer le mock via un fichier de configuration dédié
- **Rejeté** : moins ergonomique qu'une variable d'environnement pour CI/CD. Alourdit le bootstrap. Les variables d'environnement sont le standard pour les configurations d'exécution dans les conteneurs.

### Trait `LlmProvider` mockable par injection de dépendance uniquement (pattern DI)
- **Description** : injecter le provider via constructeur ou conteneur IoC, sans variable d'environnement
- **Non retenu pour l'instant** : l'injection via `Arc<dyn LlmProvider>` est déjà présente — `create_llm_provider()` retourne un `Arc<dyn LlmProvider>`. Le `MockProvider` réutilise cette interface sans modifier la boucle agentique. Une injection DI explicite pourrait venir compléter pour les tests unitaires.

### Tests d'intégration Rust (`#[tokio::test]`) avec mocks in-process
- **Description** : écrire des tests Rust qui instancient directement `MockProvider` sans HTTP
- **Complémentaire, pas exclusif** : cette approche couvre les tests unitaires Rust. Le `LLM_MOCK=true` mode couvre les tests d'intégration E2E cross-services (orchestrateur + MCP + frontend), qui ne peuvent pas être faits in-process.

---

## Conséquences

### Positives
- **Tests E2E reproductibles** : le pipeline complet (orchestrateur → MCP → Postgres → SSE → Frontend) peut être validé sans clé API ni quota, à n'importe quel moment.
- **CI/CD ready** : `LLM_MOCK=true` peut être injecté dans un pipeline GitHub Actions sans secret LLM, permettant des smoke tests à chaque push.
- **Zéro modification de la boucle agentique** : le `MockProvider` respecte le contrat `LlmProvider`. L'agentic loop dans `api/process.rs` ne sait pas s'il parle à Groq ou au mock.
- **Vrais appels MCP préservés** : contrairement à un stub complet, le mock LLM laisse passer les appels vers les serveurs MCP réels. On valide ainsi l'intégration MCP + Postgres en même temps que le pipeline SSE.
- **Débogage accéléré** : en développement, activer le mock évite les 2-5 secondes d'inférence LLM et les rate limits pour tester des modifications de routing ou de streaming.

### Négatives / Risques
- **Le mock ne valide pas la qualité des prompts** : les `tool_call` générés par le `MockProvider` sont codés en dur. Un bug dans le system prompt ou dans le formatage des messages ne sera pas détecté par le mock.
- **Découplage de la réalité LLM** : le mock simule un LLM parfait (appel d'outil toujours au bon format, arguments valides). Des erreurs de parsing de réponse LLM réelle ne sont pas couvertes.
- **`tenant_id` hardcodé dans le fallback** : si le mock ne trouve pas le `tenant_id` dans les messages système, il utilise `00000000-0000-0000-0000-000000000001` comme valeur par défaut. Acceptable en développement local, à corriger avant usage en CI multi-tenant.

### Neutres
- Le `MockProvider` peut être étendu pour simuler d'autres outils MCP (`mcp_billing__get_invoices`, `mcp_analytics__get_metrics`, etc.) en ajoutant des branches dans la logique de tour 1, sans impact sur le reste du code.
- La variable `LLM_MOCK` peut être combinée avec `LLM_MODEL` pour tester différents providers réels ; les deux sont orthogonaux.
