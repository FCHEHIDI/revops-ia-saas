# frontend — UI RevOps IA SaaS

Interface utilisateur Next.js 15 du projet RevOps IA SaaS.

## Stack

- **Framework** : Next.js 15 (App Router)
- **Langage** : TypeScript 5
- **Styling** : Tailwind CSS 3
- **State management** : Zustand
- **SSE / streaming** : EventSource natif (réponses LLM en temps réel)

## Structure

```
src/
├── app/
│   ├── (auth)/
│   │   └── login/          # Page de connexion
│   ├── (dashboard)/
│   │   ├── chat/           # Interface chat IA principale
│   │   ├── crm/            # Vue contacts, comptes, deals
│   │   ├── billing/        # Vue facturation et abonnements
│   │   ├── analytics/      # Dashboards et métriques
│   │   ├── sequences/      # Séquences d'outreach
│   │   └── documents/      # Gestion documentaire
│   ├── layout.tsx          # Layout racine (providers, fonts)
│   └── page.tsx            # Redirect vers /chat
├── components/
│   ├── chat/               # Composants interface conversationnelle
│   ├── crm/                # Composants CRM (tables, cards, forms)
│   ├── billing/            # Composants billing
│   ├── analytics/          # Charts, KPIs, dashboards
│   ├── sequences/          # Composants sequences
│   ├── documents/          # Upload, preview, liste documents
│   └── ui/                 # Composants UI génériques (Button, Input, Modal…)
├── hooks/                  # Custom React hooks (useSSE, useTenant, useAuth…)
├── lib/
│   ├── api.ts              # Client API backend (fetch wrappers)
│   └── sse.ts              # Client SSE pour le streaming LLM
└── types/                  # Types TypeScript partagés
```

## Variables d'environnement

Copier `.env.example` → `.env.local` et renseigner les valeurs.

## Démarrage local

```bash
npm install
npm run dev
```

## Relations avec les autres composants

- Appelle le **Backend API** (`/api/v1/...`) pour auth, sessions, et routing
- Consomme les réponses LLM en streaming via **SSE** (Server-Sent Events)
- Affiche les données métier issues des **serveurs MCP** via le backend
