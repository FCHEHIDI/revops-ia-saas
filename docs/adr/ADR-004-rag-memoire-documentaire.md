# ADR-004 : RAG pour la mémoire documentaire long-terme

- **Date** : 2026-03-05
- **Statut** : Accepté
- **Décideurs** : Architecte Système

---

## Contexte

Les équipes RevOps travaillent avec de grandes quantités de documentation non structurée ou semi-structurée qui informent les décisions de l'IA :

- **Playbooks** commerciaux (qualification, closing, gestion des objections)
- **QBR** (Quarterly Business Reviews) et comptes-rendus de réunions
- **Emails et transcriptions d'appels** commerciaux
- **Notes de comptes** sur les clients
- **Rapports d'analyses** et forecasts historiques
- **Documentation produit** interne

Ces documents dépassent largement la fenêtre de contexte d'un LLM (typiquement 128k à 200k tokens). Il est impossible de les injecter en totalité dans chaque prompt. De plus, les réinjecter à chaque requête serait prohibitif en coût et en latence.

La solution classique est le **Retrieval Augmented Generation (RAG)** : indexer les documents en vecteurs, puis retrouver les extraits les plus pertinents à chaque requête et les injecter dans le contexte.

---

## Décision

**Une couche RAG dédiée est mise en place comme mémoire documentaire long-terme du système, avec isolation stricte par tenant.**

### Architecture de la couche RAG

**Ingestion des documents :**
1. Les documents sont soumis via le Backend API (ou via `mcp-filesystem`)
2. Ils sont découpés en chunks (stratégie sliding window avec overlap, taille adaptée au type de document)
3. Chaque chunk est embarqué via le modèle d'embedding `text-embedding-3-large` (OpenAI) ou équivalent open-source (`multilingual-e5-large` pour les documents en français)
4. Les vecteurs sont stockés avec les métadonnées (`tenant_id`, `document_id`, `source_type`, `created_at`)

**Récupération (retrieval) :**
1. La requête utilisateur est embarquée avec le même modèle
2. Une recherche de similarité cosinus est effectuée dans le namespace tenant
3. Les top-K chunks les plus similaires sont retournés (K = 5 à 10 selon le type de requête)
4. Un re-ranking optionnel (cross-encoder) améliore la précision pour les requêtes critiques
5. Les chunks sélectionnés sont injectés dans le contexte LLM

**Stratégie de stockage :**
- **Phase MVP** : `pgvector` (extension PostgreSQL) — même infrastructure que la base principale, opérations simplifiées
- **Phase scale** : migration vers **Qdrant** si les performances pgvector deviennent insuffisantes (>10M vecteurs par tenant ou latence p99 > 50ms)

**Isolation multi-tenant :**
- Chaque tenant a son propre **namespace/collection** dans le vector store
- La requête RAG inclut systématiquement un filtre `tenant_id` — impossible de récupérer des documents cross-tenant
- Les clés d'embedding ne sont jamais partagées entre tenants

### Choix du framework RAG

- **Technologie** : Python + LangChain ou LlamaIndex
- **Critères** : maturité, support pgvector et Qdrant, abstractions de retrieval, compatibilité avec les modèles d'embedding
- Le choix final entre LangChain et LlamaIndex sera fait lors de l'implémentation selon les benchmarks internes

---

## Alternatives considérées

### Tout injecter dans le contexte LLM (full context stuffing)
- **Description** : pour chaque requête, injecter tous les documents pertinents dans la fenêtre de contexte
- **Rejeté** :
  - Coût prohibitif : 1M tokens en contexte = ~$10 par requête avec GPT-4. À 10k utilisateurs actifs, le coût est non viable
  - Latence : les contextes longs augmentent le temps d'inférence linéairement
  - Limite technique : même avec 200k tokens de contexte, les playbooks complets d'une entreprise dépassent cette limite
  - Qualité : le LLM perd en précision sur les informations enfouies dans de très longs contextes ("lost in the middle" problem)

### Fine-tuning du modèle
- **Description** : entraîner le modèle sur les documents propres à chaque tenant pour qu'il "mémorise" l'information
- **Rejeté** :
  - Coût élevé : fine-tuning d'un modèle de base = milliers à dizaines de milliers de dollars
  - Rigidité : les documents évoluent constamment (nouveaux playbooks, nouveaux appels) — un modèle fine-tuné est figé
  - Isolation tenant impossible : un modèle partagé fine-tuné sur les données de plusieurs tenants est un risque de fuite
  - Hallucinations : le fine-tuning ne garantit pas la précision factuelle, contrairement au RAG qui cite ses sources

### Cache sémantique simple
- **Description** : mettre en cache les réponses à des requêtes similaires
- **Rejeté** : résout le problème de performance mais pas le problème d'accès à l'information documentaire. Complémentaire au RAG, pas une alternative.

### Base de données de graphes (Knowledge Graph)
- **Description** : structurer les documents en graphe d'entités et de relations
- **Rejeté pour le MVP** : complexité d'implémentation élevée, besoin d'extraction d'entités coûteuse. Peut être envisagé comme complément au RAG pour les cas d'usage avancés (relationnel entre comptes, deals, contacts).

---

## Conséquences

### Positives
- **Scalabilité de la mémoire** : le volume de documents indexés n'est limité que par le stockage, pas par la fenêtre de contexte
- **Fraîcheur de l'information** : les nouveaux documents sont disponibles dès leur indexation (pas de réentraînement nécessaire)
- **Pertinence** : seuls les extraits vraiment pertinents à la question sont injectés, réduisant le bruit dans le contexte LLM
- **Coût maîtrisé** : le coût d'embedding est beaucoup plus faible que le coût d'inférence LLM sur de longs contextes
- **Isolation tenant native** : les namespaces par tenant garantissent l'étanchéité documentaire
- **Traçabilité** : les sources RAG peuvent être retournées à l'utilisateur ("basé sur le playbook Q4 2025")

### Négatives / Risques
- **Qualité du chunking** : une mauvaise stratégie de découpage peut fragmenter des informations logiquement liées, dégradant la pertinence des résultats
- **Dérive sémantique** : les embeddings capturent la similarité sémantique mais pas toujours la précision factuelle (un chunk "similaire" peut ne pas être "correct")
- **Latence additionnelle** : la recherche vectorielle ajoute ~20 à 50ms par requête (acceptable)
- **Infrastructure supplémentaire** : pgvector en MVP puis Qdrant si besoin — composant à opérer
- **Synchronisation** : si un document est mis à jour, ses anciens chunks doivent être supprimés et réindexés — la gestion des versions est à implémenter

### Neutres
- La couche RAG est indépendante du modèle LLM — un changement de modèle (GPT-4 → Claude → Mistral) ne nécessite pas de réindexation si les embeddings restent les mêmes
- pgvector en MVP permet de démarrer sans infrastructure supplémentaire, avec une migration vers Qdrant possible de manière transparente pour les couches supérieures
