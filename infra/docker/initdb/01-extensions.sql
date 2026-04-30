-- ═══════════════════════════════════════════════════════════════════════════════
-- Script d'initialisation Postgres pour le projet RevOps IA SaaS
-- ═══════════════════════════════════════════════════════════════════════════════
-- Ce script est exécuté automatiquement au premier démarrage du container Postgres
-- via /docker-entrypoint-initdb.d
-- ADR-005 : Isolation multi-tenant via RLS (app.current_tenant_id)
-- ADR-004 : Vector store pgvector pour la mémoire documentaire RAG
-- ═══════════════════════════════════════════════════════════════════════════════

-- Extension uuid-ossp : génération d'UUID v4 pour les clés primaires
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Extension pgcrypto : fonctions de hashing pour les mots de passe (bcrypt, etc.)
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Extension vector (pgvector) : stockage et recherche de vecteurs d'embeddings
-- https://github.com/pgvector/pgvector
-- NOTE: Cette extension nécessite que le container Postgres ait pgvector préinstallé
-- Pour postgres:16-alpine standard, pgvector n'est pas inclus par défaut.
-- Si l'extension n'est pas disponible, commenter la ligne ci-dessous
-- et utiliser une image postgres:16 avec pgvector (timescale/timescaledb-ha:pg16, etc.)
CREATE EXTENSION IF NOT EXISTS "vector";

-- Confirmation dans les logs
DO $$ 
BEGIN
  RAISE NOTICE 'Extensions PostgreSQL installées avec succès : uuid-ossp, pgcrypto, vector';
END $$;
