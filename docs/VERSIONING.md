# Stratégie de Versioning Git — RevOps IA SaaS

> **Dernière mise à jour** : 2026-03-06
> **Décideurs** : Versioning & CI/CD, Architecte Système
> **ADR associé** : [ADR-007 — Structure Monorepo](./adr/ADR-007-monorepo-structure.md)

---

## Table des matières

1. [Modèle de branches](#1-modèle-de-branches)
2. [Conventions de commit](#2-conventions-de-commit)
3. [Règles de PR](#3-règles-de-pr)
4. [Règles de merge](#4-règles-de-merge)
5. [Stratégie de release](#5-stratégie-de-release)
6. [Tagging sémantique](#6-tagging-sémantique)
7. [CODEOWNERS et responsabilités](#7-codeowners-et-responsabilités)

---

## 1. Modèle de branches

### 1.1 Stratégie adoptée : Trunk-Based Development adapté

Le projet adopte un modèle **trunk-based development adapté** avec `main` comme branche de vérité unique. Les branches de feature ont une durée de vie courte (≤ 5 jours). Ce modèle évite la complexité de GitFlow tout en maintenant une discipline de review stricte.

```
main (branche protégée, toujours déployable)
  ├── feat/backend-auth-jwt-refresh
  ├── fix/orchestrator-context-timeout
  ├── chore/update-cargo-dependencies
  ├── docs/adr-008-caching-strategy
  └── release/v1.2.0
```

### 1.2 Types de branches

| Type | Pattern | Usage | Durée de vie |
|------|---------|-------|--------------|
| `feat/` | `feat/scope-description` | Nouvelle fonctionnalité | ≤ 5 jours |
| `fix/` | `fix/scope-description` | Correction de bug | ≤ 3 jours |
| `hotfix/` | `hotfix/scope-description` | Correctif urgent en production | ≤ 24 heures |
| `chore/` | `chore/scope-description` | Maintenance (deps, config, outillage) | ≤ 3 jours |
| `docs/` | `docs/scope-description` | Documentation uniquement | ≤ 2 jours |
| `refactor/` | `refactor/scope-description` | Refactoring sans changement de comportement | ≤ 5 jours |
| `ci/` | `ci/scope-description` | Modifications CI/CD uniquement | ≤ 2 jours |
| `release/` | `release/vX.Y.Z` | Branche de préparation de release | ≤ 48 heures |

### 1.3 Scopes par composant

Les scopes standardisent le périmètre d'un changement :

| Scope | Composant |
|-------|-----------|
| `backend` | `backend/` — FastAPI multi-tenant |
| `frontend` | `frontend/` — Next.js |
| `orchestrator` | `orchestrator/` — LLM Orchestrator Rust |
| `mcp-crm` | `mcp/mcp-crm/` |
| `mcp-billing` | `mcp/mcp-billing/` |
| `mcp-analytics` | `mcp/mcp-analytics/` |
| `mcp-sequences` | `mcp/mcp-sequences/` |
| `mcp-filesystem` | `mcp/mcp-filesystem/` |
| `rag` | `rag/` — RAG Layer |
| `infra` | `infra/` — Docker, K8s, Terraform |
| `ci` | `.github/workflows/` |
| `docs` | `docs/` |
| `deps` | Mises à jour de dépendances (multi-composants) |

Exemples de noms de branches valides :
```
feat/backend-multi-tenant-rls
fix/mcp-crm-tenant-validation
chore/deps-update-axum-0.8
docs/adr-008-redis-cache
refactor/orchestrator-context-builder
ci/add-trivy-scan-mcp
hotfix/backend-jwt-expiry-bypass
release/v1.3.0
```

### 1.4 Branches protégées

La branche `main` est protégée avec les règles suivantes (à configurer dans GitHub → Settings → Branches) :

- **Require pull request before merging** : activé
- **Require approvals** : 1 reviewer minimum
- **Dismiss stale pull request approvals when new commits are pushed** : activé
- **Require status checks to pass** : tous les jobs CI du composant modifié doivent être verts
- **Require conversation resolution before merging** : activé
- **Require linear history** : activé (enforce squash merge)
- **Do not allow bypassing the above settings** : activé (incluant les admins)
- **Restrict who can push to matching branches** : uniquement via PR

---

## 2. Conventions de commit

Le projet suit le standard **[Conventional Commits 1.0.0](https://www.conventionalcommits.org/)**.

### 2.1 Format

```
type(scope): description courte

[corps optionnel]

[footer(s) optionnel(s)]
```

### 2.2 Types autorisés

| Type | Usage | Déclencheur semver |
|------|-------|-------------------|
| `feat` | Nouvelle fonctionnalité | MINOR |
| `fix` | Correction de bug | PATCH |
| `docs` | Documentation uniquement | — |
| `chore` | Maintenance, tooling, dépendances | — |
| `refactor` | Refactoring sans changement de comportement | — |
| `test` | Ajout/modification de tests | — |
| `ci` | Modifications CI/CD | — |
| `perf` | Amélioration de performance | PATCH |
| `build` | Modifications du système de build | — |
| `revert` | Annulation d'un commit précédent | PATCH |
| `style` | Formatage pur (sans changement de logique) | — |

Un `!` après le type ou un footer `BREAKING CHANGE:` déclenche une montée de version MAJOR :
```
feat(backend)!: remove /api/v1/users endpoint in favor of /api/v2/users
```

### 2.3 Règles de message

- **Longueur** : ligne de sujet ≤ 72 caractères
- **Ton** : impératif présent ("add", "fix", "update" — jamais "added", "fixed")
- **Casse** : minuscule pour la description (après le `:`)
- **Pas de point final** sur la ligne de sujet
- **Corps** : expliquer le *pourquoi*, pas le *comment* ; séparé du sujet par une ligne vide
- **Footer** : références aux issues (`Closes #123`, `Refs #456`), breaking changes

### 2.4 Exemples valides

```
feat(backend): add JWT refresh token rotation endpoint

Implements RFC-style token rotation to invalidate the previous refresh
token on each use, preventing token reuse attacks.

Closes #142

---

fix(mcp-crm): enforce tenant_id validation on update_deal_stage tool

The tool was accepting calls without tenant_id when the RLS policy
was not yet active on the connection. Added explicit check before
any write operation.

Refs #178

---

chore(deps): update axum from 0.7 to 0.8 in orchestrator and mcp servers

Breaking change in axum 0.8 requires updating router configuration.
All MCP servers and the orchestrator updated simultaneously.

---

ci(backend): add bandit SAST scan to CI pipeline

---

docs(adr): add ADR-008 for Redis caching strategy
```

### 2.5 Commitlint (hook pre-commit)

La configuration commitlint est dans `.commitlintrc.json` à la racine du repo.

Pour activer le hook localement :
```bash
npm install --save-dev @commitlint/cli @commitlint/config-conventional husky
npx husky init
echo "npx --no -- commitlint --edit \$1" > .husky/commit-msg
```

---

## 3. Règles de PR

### 3.1 Titre

Le titre d'une PR doit suivre le format Conventional Commits :
```
type(scope): description courte
```
Exemples :
```
feat(frontend): add SSE streaming for chat messages
fix(orchestrator): handle Redis connection timeout on startup
```

### 3.2 Template de PR

Le fichier `.github/PULL_REQUEST_TEMPLATE.md` fournit une checklist structurée à compléter pour chaque PR.

### 3.3 Reviews obligatoires

| Cas | Reviewers requis |
|-----|-----------------|
| Changements dans `backend/` | 1 reviewer (CODEOWNERS: `@team-backend`) |
| Changements dans `frontend/` | 1 reviewer (CODEOWNERS: `@team-frontend`) |
| Changements dans `orchestrator/` | 1 reviewer (CODEOWNERS: `@team-rust`) |
| Changements dans `mcp/` | 1 reviewer (CODEOWNERS: `@team-rust`) |
| Changements dans `rag/` | 1 reviewer (CODEOWNERS: `@team-backend`) |
| Changements dans `infra/` | 1 reviewer (CODEOWNERS: `@team-devops`) |
| Changements dans `.github/workflows/` | 1 reviewer (CODEOWNERS: `@team-devops`) |
| Changements dans `docs/adr/` | 1 reviewer (CODEOWNERS: `@team-architect`) |

### 3.4 Checks bloquants

Tous ces checks doivent être verts pour merger :

- **CI** : le workflow correspondant au composant modifié doit passer (lint + tests + build)
- **Coverage** : le seuil de coverage ne doit pas régresser (seuil : 80% pour Python, 70% pour Rust)
- **Lint** : aucune erreur de lint (ruff/mypy pour Python, clippy pour Rust, ESLint pour TypeScript)
- **Security** : aucune vulnérabilité critique détectée par les scans de sécurité
- **Conversations** : toutes les conversations de review doivent être résolues

### 3.5 Taille recommandée des PR

- **Idéal** : ≤ 400 lignes modifiées (hors fichiers générés, lock files, etc.)
- **Maximum** : ≤ 800 lignes (au-delà, splitter en plusieurs PR logiques)
- **Exception** : migrations de base de données et mises à jour de lock files ne sont pas comptées

---

## 4. Règles de merge

### 4.1 Stratégie par type de branche

| Branche source | Branche cible | Stratégie | Raison |
|----------------|---------------|-----------|--------|
| `feat/*`, `fix/*`, `chore/*`, `refactor/*`, `docs/*`, `ci/*` | `main` | **Squash merge** | Historique `main` propre, 1 commit = 1 PR |
| `hotfix/*` | `main` | **Squash merge** | Idem |
| `release/vX.Y.Z` | `main` | **Merge commit** | Préserver le commit de release avec le tag |

Le message du squash commit doit reprendre le titre de la PR (format Conventional Commits).

### 4.2 Conditions de merge

1. Au moins **1 review approuvée** par un CODEOWNER du périmètre modifié
2. **Tous les status checks CI sont verts** (pas de bypass autorisé)
3. **Aucun conflit** avec la branche cible
4. **Toutes les conversations résolues**
5. La branche est **à jour avec `main`** (rebase avant merge si nécessaire)

### 4.3 Suppression automatique des branches

GitHub doit être configuré pour **supprimer automatiquement les branches** après merge (Settings → General → Automatically delete head branches).

Les branches `release/vX.Y.Z` sont supprimées manuellement après que le tag de release a été créé et poussé.

---

## 5. Stratégie de release

### 5.1 Versioning sémantique

Le projet utilise **[Semantic Versioning 2.0.0](https://semver.org/)** (MAJOR.MINOR.PATCH) :

| Incrément | Déclencheur |
|-----------|-------------|
| `MAJOR` | Breaking change (`feat!`, `fix!`, ou footer `BREAKING CHANGE:`) |
| `MINOR` | Nouvelle fonctionnalité rétro-compatible (`feat`) |
| `PATCH` | Correction de bug ou amélioration de performance (`fix`, `perf`) |

### 5.2 Process de release standard

```
1. Accumuler des commits sur main (feat, fix, chore...)
2. Créer une branche release/vX.Y.Z depuis main
3. Finaliser le CHANGELOG (généré automatiquement par Release Please)
4. Ouvrir une PR release/vX.Y.Z → main
5. Review et validation de la PR de release
6. Merger avec merge commit (pas squash)
7. Créer le tag vX.Y.Z sur le commit de merge
8. GitHub Release automatiquement créée par le workflow release.yml
9. Déploiement automatique en production déclenché par le tag
```

### 5.3 Release automatisée via Release Please

Le workflow `.github/workflows/release.yml` utilise **[Release Please](https://github.com/googleapis/release-please)** pour :
- Analyser les commits Conventional Commits depuis la dernière release
- Générer automatiquement le `CHANGELOG.md`
- Proposer une PR "Release Please" avec la version calculée
- Créer le tag et la GitHub Release après merge de la PR

### 5.4 Environnements de déploiement

| Environnement | Déclencheur | Approbation |
|---------------|-------------|-------------|
| **dev** | Push sur `main` (staging auto) | Aucune |
| **staging** | Push sur `main` | Aucune (auto) |
| **production** | Push du tag `vX.Y.Z` | Review manuelle requise (GitHub Environments) |

### 5.5 Hotfix process

Un hotfix est une correction urgente d'un bug en production sans passer par le cycle de release normal :

```
1. Créer une branche hotfix/scope-description depuis le tag de production courant
2. Appliquer le fix avec un commit fix(scope): description
3. Ouvrir une PR hotfix/... → main
4. Review accélérée (1 reviewer, délai ≤ 2h)
5. Squash merge dans main
6. Créer immédiatement un tag vX.Y.(Z+1) pour déclencher le déploiement prod
```

---

## 6. Tagging sémantique

### 6.1 Format des tags

Le projet utilise un seul tag global par release (pas de tags par composant), cohérent avec la stratégie monorepo :

```
vMAJOR.MINOR.PATCH         → Release standard (ex: v1.3.0)
vMAJOR.MINOR.PATCH-rc.N    → Release candidate (ex: v1.3.0-rc.1)
vMAJOR.MINOR.PATCH-beta.N  → Beta (ex: v1.3.0-beta.1)
```

> **Note** : Si des composants devaient évoluer vers des cycles de release indépendants à l'avenir, le format `vX.Y.Z-componentname` (ex: `v1.3.0-backend`) sera adopté. Un ADR devra être créé avant ce changement.

### 6.2 Création des tags

Les tags sont créés **automatiquement par le workflow `release.yml`** après merge de la PR Release Please. Ils ne doivent jamais être créés manuellement sauf en cas d'urgence (hotfix hors Release Please).

Création manuelle d'urgence :
```bash
git tag -a v1.2.1 -m "hotfix(backend): fix JWT expiry bypass"
git push origin v1.2.1
```

### 6.3 Tags annotés

Tous les tags de release sont des **tags annotés** (pas des tags légers) pour conserver les métadonnées (auteur, date, message). Release Please crée des tags annotés par défaut.

### 6.4 Protection des tags

Configurer dans GitHub → Settings → Tags → Protected tags rules :
- Pattern `v*` : seul le workflow CI (bot GitHub Actions) peut créer ces tags

---

## 7. CODEOWNERS et responsabilités

Le fichier `.github/CODEOWNERS` définit les reviewers obligatoires par répertoire. Il est géré dans ce repo et mis à jour lors de tout changement d'équipe.

Voir `.github/CODEOWNERS` pour la configuration complète.

---

*Ce document est vivant. Toute modification structurelle doit faire l'objet d'une PR avec review de l'Architecte Système et du lead DevOps.*
