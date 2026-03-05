# ADR-002 : Architecture LLM Stateless avec Queue de traitement

- **Date** : 2026-03-05
- **Statut** : Accepté
- **Décideurs** : Architecte Système

---

## Contexte

Le système doit supporter **10 000 utilisateurs concurrents** interagissant avec un LLM en temps réel. Les contraintes sont :

- **Coût GPU** : les inférences LLM sont coûteuses. Un GPU A100 peut traiter ~50 requêtes/seconde en inférence standard. À 10k utilisateurs actifs, sans batching, il faudrait ~200 GPU simultanément.
- **Isolation multi-tenant** : les contextes de deux tenants différents ne doivent jamais se mélanger.
- **Variabilité de charge** : les pics d'usage (morning standup, fin de trimestre pour les équipes RevOps) peuvent multiplier la charge par 5 à 10x.
- **Fiabilité** : si un worker LLM tombe, les requêtes en cours ne doivent pas être perdues.
- **Latence acceptable** : les utilisateurs tolèrent une attente de 1 à 3 secondes pour une réponse IA, mais pas 30 secondes.

Un LLM avec état interne (sessions maintenues en mémoire dans le modèle) est impossible à scaler horizontalement : chaque requête doit toujours aller vers le même worker, créant du couplage et des hot spots.

---

## Décision

**L'orchestrateur LLM est stateless. Tout le contexte est reconstruit à chaque requête. Une queue de traitement est interposée entre l'orchestrateur et le cluster LLM.**

### Fonctionnement détaillé

**Reconstruction du contexte à chaque requête :**
1. La requête utilisateur arrive via le Backend API avec un `session_id` et un `tenant_id`
2. L'orchestrateur récupère l'historique de session depuis la base de données (Backend API)
3. L'orchestrateur interroge le RAG Layer pour les extraits documentaires pertinents
4. L'orchestrateur appelle les serveurs MCP nécessaires pour les données métier en temps réel
5. Le contexte complet (historique + extraits RAG + données MCP + system prompt) est assemblé
6. Ce contexte est enqueué dans la queue LLM

**Queue de traitement :**
- **Technologie** : Redis + BullMQ (côté Backend/Node) ou Tokio channels (côté Orchestrateur Rust)
- **Priorités** : 3 niveaux — `HIGH` (requêtes utilisateur interactives), `NORMAL` (analyses background), `LOW` (batch reporting)
- **Batching GPU** : les workers LLM consomment des batches de N requêtes pour maximiser l'utilisation GPU
- **Retry** : 3 tentatives avec backoff exponentiel sur échec worker
- **Dead Letter Queue** : les requêtes échouées définitivement sont archivées et l'utilisateur notifié

**Cluster LLM :**
- N workers stateless, chacun consomme depuis la queue
- Scaling horizontal automatique basé sur la longueur de la queue
- Chaque worker traite un batch, retourne le résultat au Backend via callback ou polling

---

## Alternatives considérées

### LLM avec état interne (sessions en mémoire dans le modèle)
- **Description** : chaque session utilisateur est "fixée" à un worker LLM qui maintient le KV-cache de la conversation
- **Rejeté** : impossible à scaler horizontalement (affinité worker requise), impossible de recycler les workers, consommation mémoire GPU proportionnelle au nombre de sessions actives, pas d'isolation tenant fiable. Fonctionne pour des prototypes, pas pour 10k utilisateurs.

### Serverless LLM direct (AWS Lambda / Cloudflare Workers)
- **Description** : chaque requête déclenche un appel serverless direct vers l'API LLM
- **Rejeté** : pas de batching possible (chaque requête est indépendante), coût par token maximal sans optimisation GPU, cold starts problématiques, pas de contrôle sur la priorité des requêtes.

### WebSockets avec état maintenu côté orchestrateur
- **Description** : connexion persistante par utilisateur, état maintenu dans l'orchestrateur
- **Rejeté** : l'orchestrateur devient stateful, rendant impossible son scaling horizontal. Un crash perd toutes les sessions actives. Incompatible avec le principe stateless du projet.

### Queue unique sans priorités
- **Description** : toutes les requêtes dans une seule queue FIFO
- **Rejeté** : une analyse batch lourde peut bloquer des requêtes interactives urgentes. Le système de priorités est essentiel pour la qualité de service.

---

## Conséquences

### Positives
- **Scalabilité horizontale totale** : n'importe quel worker peut traiter n'importe quelle requête, scaling indépendant de chaque composant
- **Résilience** : si un worker tombe, ses requêtes sont reprises automatiquement par un autre worker
- **Optimisation GPU** : le batching réduit le coût d'inférence de 30 à 50% selon les benchmarks
- **Isolation tenant garantie** : le contexte est reconstruit de zéro à chaque requête, pas de risque de contamination cross-tenant
- **Observabilité** : la queue est un point central de monitoring (longueur, latence, erreurs)
- **Contrôle de charge** : en cas de pic, la queue absorbe la charge et protège le cluster LLM de l'overload

### Négatives / Risques
- **Latence légèrement augmentée** : la reconstruction du contexte (DB + RAG + MCP) ajoute ~50 à 150ms par requête. Acceptable pour une IA conversationnelle, mais à surveiller.
- **Coût de la reconstruction** : chaque requête implique des appels DB, RAG et MCP. Des stratégies de cache (TTL court sur les données MCP, cache du contexte session récent) seront nécessaires pour les cas d'usage intensifs.
- **Complexité opérationnelle** : la queue Redis est un composant supplémentaire à opérer, monitorer et scalabiliser.
- **Cohérence éventuelle** : dans des cas rares (données MCP mises à jour entre deux requêtes rapides), l'utilisateur peut voir des données légèrement décalées.

### Neutres
- La reconstruction du contexte permet naturellement de toujours travailler avec les données les plus récentes (pas de cache périmé de session)
- Le protocole entre l'orchestrateur et le cluster LLM est une interface contractuelle stable : les implémentations des deux côtés peuvent évoluer indépendamment
