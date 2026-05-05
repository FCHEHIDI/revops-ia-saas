# Pré-déploiement — Checklist

## Objectif
Stabiliser le stack existant et valider les scénarios critiques avant mise en production.

## 1. RBAC et rôles
- Vérifier que le backend expose `roles` et `permissions` dans `/auth/me`.
- Vérifier que le frontend charge le profil utilisateur et filtre les éléments de menu selon le rôle.
- Tester que `admin`, `revops`, `sales` et `customer_success` ont des accès différents.
- Vérifier qu’un utilisateur sans permission ne peut pas appeler les endpoints protégés.

## 2. Seed mock utilisateurs
- Créer des comptes mock pour :
  - `admin@acme.io` (admin)
  - `sales@acme.io` (sales)
  - `ops@demo-health.io` (customer_success)
- Vérifier la connexion avec `acme1234`.
- Vérifier la présence de données CRM et comptes par tenant.

## 3. Vérifications services
- Backend health: `/healthz` ou equivalent.
- Orchestrateur health: endpoint de santé et port correctement mappé.
- Qdrant : healthcheck Docker stable.
- Frontend : routes principales accessibles après login.

## 4. Scénarios critiques à valider
- Connexion / authentification utilisateur.
- Lecture liste comptes CRM pour `sales` et `revops`.
- Création et modification de compte/contact depuis l’UI.
- Accès aux dashboards analytics pour `revops`.
- Blocage `billing` pour `sales` et affichage pour `admin`.
- Règles d’isolation tenant : un utilisateur d’un tenant ne voit pas les données d’un autre tenant.

## 5. Sécurité minimale
- Remplacer les secrets de demo avant préprod.
- Interdire le commit de `.env`.
- Activer `JWT_SECRET` fort et `INTERNAL_API_KEY` unique.
- Valider CORS et headers de sécurité du backend.

## 6. Documentation / audit
- Mettre à jour `docs/AUDIT-2026-05-01.md` si des points critiques changent.
- Ajouter un fichier de suivi des étapes coy.
- Documenter la procédure d’exécution de `backend/scripts/seed_predeployment.py`.
