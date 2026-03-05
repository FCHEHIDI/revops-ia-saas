# ADR-003 : MCP comme unique couche d'accès métier pour le LLM

- **Date** : 2026-03-05
- **Statut** : Accepté
- **Décideurs** : Architecte Système

---

## Contexte

Dans un système IA-native, le LLM a besoin d'accéder à des données métier en temps réel pour accomplir ses tâches : lire les contacts CRM, vérifier une facture, déclencher une séquence d'emails, analyser les métriques de pipeline. Plusieurs approches sont possibles pour donner cet accès, avec des implications très différentes en matière de :

- **Sécurité** : un LLM qui exécute des requêtes SQL directes est un vecteur d'injection et d'exfiltration de données
- **Multi-tenant** : les données d'un tenant ne doivent jamais être accessibles à un autre, même via le LLM
- **Auditabilité** : chaque action du LLM doit être traçable, réversible et compréhensible
- **Évolutivité** : les capacités métier du LLM doivent pouvoir évoluer sans modifier l'orchestrateur

Le protocole **Model Context Protocol (MCP)** d'Anthropic est un standard émergent pour exposer des capacités structurées à un LLM via des "tools" bien définis. Il offre un contrat clair entre le LLM et les services métier.

---

## Décision

**Le LLM ne touche jamais les données brutes. Toutes les interactions métier passent exclusivement par des serveurs MCP dédiés.**

### Serveurs MCP du projet

| Serveur | Domaine | Exemples de tools |
|---------|---------|-------------------|
| `mcp-crm` | CRM (contacts, comptes, deals) | `get_contact`, `update_deal_stage`, `search_accounts` |
| `mcp-billing` | Facturation et abonnements | `get_invoice`, `check_subscription_status`, `list_overdue_payments` |
| `mcp-analytics` | Métriques et reporting | `get_pipeline_metrics`, `compute_churn_rate`, `get_deal_velocity` |
| `mcp-sequences` | Séquences d'outreach et emails | `create_sequence`, `enroll_contact`, `get_sequence_performance` |
| `mcp-filesystem` | Documents, fichiers, playbooks | `read_document`, `list_playbooks`, `upload_report` |

### Principe de fonctionnement

1. L'orchestrateur LLM reçoit une requête utilisateur
2. Il détermine quels tools MCP sont nécessaires (via le raisonnement du modèle)
3. Il appelle les tools MCP en passant le `tenant_id` issu du JWT
4. Chaque serveur MCP valide le `tenant_id`, applique ses règles d'autorisation, et retourne uniquement les données autorisées
5. Le LLM reçoit les données structurées et formule sa réponse

### Garanties imposées par les serveurs MCP

- **Validation du `tenant_id`** à chaque appel — aucune requête sans tenant identifié
- **Autorisation granulaire** par action (read vs write vs delete)
- **Audit log** de chaque appel (qui, quoi, quand, résultat)
- **Rate limiting** par tenant pour éviter l'abus via le LLM
- **Schémas validés** en entrée et sortie (pas d'injection de prompt via les données)

---

## Alternatives considérées

### Accès direct à la base de données (SQL/ORM)
- **Description** : l'orchestrateur ou le LLM génère et exécute des requêtes SQL directement
- **Rejeté** :
  - Risque d'injection SQL via les prompts utilisateur
  - Pas d'isolation tenant au niveau applicatif (RLS seul insuffisant si mal configuré)
  - Impossibilité d'auditer les actions à un niveau sémantique ("a mis à jour le deal X" vs "UPDATE deals SET stage=...")
  - Couplage fort entre le LLM et le schéma de la base de données — toute migration casse l'orchestrateur
  - Aucun contrôle de ce que le LLM peut faire (il pourrait théoriquement effectuer un DELETE*)

### API REST interne (endpoints dédiés au LLM)
- **Description** : créer des endpoints REST spécifiques que l'orchestrateur appelle
- **Rejeté** :
  - Pas de standard pour la découverte des capacités (le LLM ne sait pas quels endpoints existent)
  - Pas de schéma formel des paramètres et retours, rendant difficile la génération correcte d'appels par le LLM
  - Pas de convention d'erreur uniforme
  - Duplication potentielle avec l'API publique — confusion sur ce qui est exposé où
  - MCP résout exactement ce problème avec un protocole standardisé

### Function calling OpenAI / Anthropic sans MCP
- **Description** : définir des tools directement dans le prompt système, sans serveur MCP dédié
- **Rejeté** :
  - Les tools sont définis dans le code de l'orchestrateur — couplage fort
  - Pas de séparation des responsabilités (logique métier dans l'orchestrateur)
  - Pas d'isolation du déploiement (impossible de mettre à jour un tool sans redéployer l'orchestrateur)
  - MCP est la standardisation de ce pattern avec une séparation propre

---

## Conséquences

### Positives
- **Surface d'attaque drastiquement réduite** : le LLM ne peut que ce que les serveurs MCP lui permettent — aucun accès direct aux données brutes
- **Auditabilité complète** : chaque action LLM est loggée avec son contexte métier sémantique
- **Découplage fort** : les serveurs MCP peuvent évoluer, être versionés ou remplacés sans impacter l'orchestrateur
- **Multi-tenant natif** : l'isolation tenant est appliquée dans chaque serveur MCP, pas laissée à la discrétion du LLM
- **Testabilité** : les serveurs MCP sont testés indépendamment de l'orchestrateur, avec des mocks faciles
- **Évolutivité fonctionnelle** : ajouter une nouvelle capacité métier = ajouter un tool dans un serveur MCP existant ou créer un nouveau serveur

### Négatives / Risques
- **Latence additionnelle** : chaque appel MCP est un saut réseau supplémentaire (~5 à 20ms selon le déploiement). Les workflows complexes avec de nombreux appels MCP en séquence s'accumulent.
- **Complexité d'infrastructure** : 5 serveurs MCP à déployer, monitorer et maintenir en plus de l'orchestrateur
- **Dépendance au protocole MCP** : si le protocole évolue de manière non rétro-compatible, une mise à jour coordonnée est nécessaire
- **Overhead de sérialisation** : les données MCP sont sérialisées/désérialisées en JSON à chaque passage, avec un coût mineur mais non nul

### Neutres
- Les appels MCP indépendants peuvent être parallélisés par l'orchestrateur (ex: appel simultané à `mcp-crm` et `mcp-analytics`) pour neutraliser la latence additionnelle
- La structure en serveurs MCP séparés favorise la spécialisation des équipes de développement par domaine métier
