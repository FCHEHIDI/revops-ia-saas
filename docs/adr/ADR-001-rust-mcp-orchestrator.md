# ADR-001 : Choix de Rust pour les couches MCP et Orchestrateur

- **Date** : 2026-03-05
- **Statut** : Accepté
- **Décideurs** : Architecte Système

---

## Contexte

Le projet RevOps IA SaaS repose sur deux couches critiques à haute performance et haute concurrence :

1. **L'Orchestrateur LLM** : composant central qui reconstruit le contexte à chaque requête (session + RAG + MCP), sélectionne le modèle, gère le routing et les appels parallèles. Il doit traiter des milliers de requêtes concurrentes sans latence inacceptable.

2. **Les serveurs MCP** (`mcp-crm`, `mcp-billing`, `mcp-analytics`, `mcp-sequences`, `mcp-filesystem`) : microservices métier qui encapsulent l'accès aux données sensibles. Ils constituent la seule interface entre le LLM et les données réelles — toute faille ici est critique.

Les contraintes sont les suivantes :
- **Performance** : latence p99 < 200ms pour les opérations MCP, reconstruction de contexte < 100ms
- **Concurrence élevée** : 10 000 utilisateurs simultanés sans dégradation
- **Sécurité mémoire** : pas de buffer overflows, pas de use-after-free sur des données multi-tenant
- **Stateless** : aucun état partagé entre requêtes, pas de GC stop-the-world
- **Fiabilité** : comportement déterministe, panics limités, erreurs gérées explicitement

---

## Décision

**Rust (édition 2021) est retenu comme langage unique pour l'Orchestrateur LLM et tous les serveurs MCP.**

Éléments techniques retenus :
- **Runtime async** : Tokio pour la concurrence non-bloquante à haute densité
- **Framework MCP** : `rmcp` (Rust MCP SDK) pour l'implémentation du protocole MCP
- **Gestion d'erreurs** : `anyhow` + `thiserror` pour des erreurs typées et traçables
- **Sérialisation** : `serde` + `serde_json` pour JSON performant et sans allocation inutile
- **HTTP client** : `reqwest` (async) pour les appels vers LLM APIs et services internes
- **Observabilité** : `tracing` + `opentelemetry` pour les spans distribués

---

## Alternatives considérées

### Python
- **Avantages** : facilité de développement, richesse de l'écosystème ML, équipe souvent familière
- **Rejeté** : le GIL Python limite la vraie concurrence multi-thread. `asyncio` est adapté pour l'I/O mais insuffisant pour des traitements CPU-bound. Les performances brutes sont 10x à 100x inférieures à Rust pour la concurrence intensive. Le risque de fuite mémoire sur des workers long-lived est réel.

### Go
- **Avantages** : bonne concurrence (goroutines), compilation rapide, simple à apprendre
- **Rejeté** : l'écosystème MCP en Go est immature (pas de SDK officiel stable au moment de la décision). Le GC peut introduire des pauses non déterministes sous charge. La sécurité mémoire n'est pas garantie au niveau compilation.

### Node.js / TypeScript
- **Avantages** : partage de code possible avec le frontend, nombreux développeurs disponibles
- **Rejeté** : GC non déterministe, event loop single-threaded pour le CPU, performances insuffisantes pour l'orchestration à 10k req/s. Non adapté à un composant système critique.

### Java / JVM (Kotlin, Scala)
- **Avantages** : écosystème mature, bonnes performances après JIT warm-up
- **Rejeté** : empreinte mémoire élevée (JVM heap), latence au démarrage des workers, GC pauses. Complexité opérationnelle disproportionnée.

---

## Conséquences

### Positives
- **Sécurité mémoire garantie au compile-time** : le borrow checker Rust élimine les classes entières de bugs (use-after-free, data races)
- **Concurrence sans GC** : Tokio permet des centaines de milliers de tâches async sans pauses GC
- **Performance maximale** : latences prévisibles et faibles, même sous charge
- **Binaires statiques** : déploiement simplifié (pas de runtime à gérer), images Docker minimalistes
- **Typage fort** : erreurs détectées à la compilation, pas à l'exécution en production
- **Consommation mémoire réduite** : optimisé pour les environnements cloud où le coût mémoire est direct

### Négatives / Risques
- **Courbe d'apprentissage** : Rust est plus difficile à maîtriser que Python ou Go. Les concepts d'ownership, lifetime et borrow checker demandent un investissement initial important.
- **Temps de compilation** : les builds Rust sont significativement plus lents que Python ou Go, ce qui peut ralentir les cycles de développement.
- **Écosystème MCP** : `rmcp` est un SDK relativement récent. Il faudra contribuer ou adapter certaines fonctionnalités.
- **Recrutement** : le vivier de développeurs Rust senior est plus restreint que pour Python/Go.

### Neutres
- L'orchestrateur et les serveurs MCP étant des composants internes (pas exposés directement aux utilisateurs), la courbe d'apprentissage Rust n'impacte pas le time-to-market côté produit.
- Le backend API (Python/FastAPI) et le frontend (TypeScript/Next.js) utilisent des langages distincts — la séparation des couches garantit l'indépendance technologique.
- Des générateurs de code (Rust macros, `cargo generate`) permettent de bootstrapper rapidement de nouveaux serveurs MCP en suivant un template standard.
