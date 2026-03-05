# Architecture Decision Records (ADR)

Ce répertoire contient l'ensemble des décisions architecturales structurantes du projet **RevOps IA SaaS**.

Chaque ADR documente une décision technique majeure : son contexte, la décision retenue, les alternatives rejetées et les conséquences prévisibles.

---

## Index des ADRs

| N° | Titre | Statut | Date |
|----|-------|--------|------|
| [ADR-001](./ADR-001-rust-mcp-orchestrator.md) | Choix de Rust pour les couches MCP et Orchestrateur | ✅ Accepté | 2026-03-05 |
| [ADR-002](./ADR-002-llm-stateless-queue.md) | Architecture LLM Stateless avec Queue de traitement | ✅ Accepté | 2026-03-05 |
| [ADR-003](./ADR-003-mcp-couche-metier.md) | MCP comme unique couche d'accès métier pour le LLM | ✅ Accepté | 2026-03-05 |
| [ADR-004](./ADR-004-rag-memoire-documentaire.md) | RAG pour la mémoire documentaire long-terme | ✅ Accepté | 2026-03-05 |
| [ADR-005](./ADR-005-backend-multitenant.md) | Isolation multi-tenant stricte dans le Backend | ✅ Accepté | 2026-03-05 |
| [ADR-006](./ADR-006-stack-technologique.md) | Stack technologique globale du projet | ✅ Accepté | 2026-03-05 |

---

## Statuts possibles

| Statut | Signification |
|--------|---------------|
| 🟡 Proposé | En cours de discussion, pas encore validé |
| ✅ Accepté | Décision validée et en vigueur |
| ⛔ Rejeté | Décision non retenue (conservée pour historique) |
| 🔄 Supersédé | Remplacé par un ADR plus récent |
| 🗄️ Déprécié | Plus applicable, remplacé par l'évolution du système |

---

## Convention de nommage

```
ADR-XXX-[slug-descriptif].md
```

- `XXX` : numéro séquentiel à 3 chiffres (001, 002, ...)
- `slug-descriptif` : mots-clés séparés par des tirets, en minuscules

---

## Référence

- Document d'architecture global : [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md)
- Charte du projet : [`docs/PROJECT_MANAGER_CHARTER.md`](../PROJECT_MANAGER_CHARTER.md)
