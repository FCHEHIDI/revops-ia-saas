# RevOps IA — Style Guide v1.0

> Document de référence design. Produit lors de l'AXE D (atelier UX, 2026-04-26).  
> Implémentation : AXE E.

---

## Décisions Design — Tableau de bord

| # | Question | Décision retenue |
|---|----------|-----------------|
| 1 | Thème | **Dark only** — identité Palazzo assumée |
| 2 | Palette | **Rouge Ducal `#C00000`** — conserver, identité forte |
| 3 | Densité | **Aéré** — style Notion / Linear nouvelle génération |
| 4 | Chat layout | **Conserver layout actuel** — sans sidebar conversations |
| 5 | CRM layout | **Table + filtres** (contacts/accounts) • **Kanban** (deals) • **Sheet drawer** (détail) |
| 6 | Ton IA | **Français par défaut**, bascule FR/EN future • tutoiement professionnel |
| 7 | Branding | **"RevOps IA"** final • logo ⚡ conservé pour le MVP |
| 8 | Onboarding | **Invite-only** (B2B contrôlé — pas de /register public) |
| 9 | Empty states | **Illustrations SVG** thématiques Venetian + CTA contextuel |

---

## 1. Thème

- **Mode unique : Dark** — aucun light mode, jamais de toggle.
- La classe `dark` est active en permanence sur `<html>`.
- Tailwind : `darkMode: "class"` conservé, la classe `light` n'est jamais utilisée.
- Fond de page : `#050505` — _pierre noire_, le plus profond de la hiérarchie.

---

## 2. Palette — Rouge Ducal

Le **Rouge Ducal** (`#C00000`) est l'accent primaire. Il porte l'identité visuelle Venetian.  
Le bleu (`#2979FF`) reste présent uniquement pour les actions système (info, analytics, liens externes).

### 2.1 Backgrounds — hiérarchie de profondeur

| Token CSS | Valeur | Utilisation |
|-----------|--------|-------------|
| `--bg-abyss` | `#050505` | Fond de page global |
| `--bg-base` | `#0a0a0a` | Layout wrapper |
| `--bg-surface` | `#111111` | Cards, panneaux, drawers |
| `--bg-elevated` | `#1a1a1a` | Hover rows, dropdowns, modals |
| `--bg-overlay` | `#222222` | Tooltips, popovers |
| `--bg-sidebar` | `#0d001a` | Sidebar gauche (teinte indigo-nuit) |

### 2.2 Rouge Ducal — teintes

| Token CSS | Valeur | Utilisation |
|-----------|--------|-------------|
| `--red-doge` | `#C00000` | Accent principal, CTA primaire, hover |
| `--red-glow` | `#FF1A1A` | Glows, focus rings visibles |
| `--red-dark` | `#8A0000` | Bordures actives, underlines |
| `--red-deep` | `#220000` | Backgrounds tintés (messages user) |
| `--red-dim` | `rgba(192,0,0,0.12)` | Hover subtil sur fond sombre |

### 2.3 Texte

| Token CSS | Valeur | Utilisation |
|-----------|--------|-------------|
| `--text-primary` | `#F2F2F2` | Corps principal |
| `--text-secondary` | `#999999` | Labels, metadata, sous-titres |
| `--text-muted` | `#555555` | Placeholders, états désactivés |
| `--text-accent` | `#C00000` | Liens, actions textuelles |

### 2.4 Bordures

| Token CSS | Valeur | Utilisation |
|-----------|--------|-------------|
| `--border-subtle` | `#1a1a1a` | Séparateurs discrets |
| `--border-default` | `#2a2a2a` | Bordures cards, inputs au repos |
| `--border-strong` | `#3a3a3a` | Cards hover, éléments actifs |
| `--border-accent` | `#8A0000` | Focus, sélection |

### 2.5 Services MCP (inchangés)

| Token CSS | Valeur | Service |
|-----------|--------|---------|
| `--mcp-crm` | `#C00000` | CRM |
| `--mcp-analytics` | `#2979FF` | Analytics |
| `--mcp-billing` | `#00C853` | Billing |
| `--mcp-sequences` | `#7B1FA2` | Sequences |
| `--mcp-default` | `#999999` | Fallback |

### 2.6 Sémantiques

| Token CSS | Valeur | Usage |
|-----------|--------|-------|
| `--success` | `#4dff91` | Confirmations, statuts gagnés |
| `--warning` | `#FF9900` | Alertes, attention |
| `--error` | `#FF1A1A` | Erreurs, statuts perdus |
| `--info` | `#2979FF` | Informations neutres |

---

## 3. Typographie

| Famille | Token Tailwind | Usage |
|---------|---------------|-------|
| **Cinzel** | `font-cinzel` | Titres hero, badges de salle, branding |
| **Space Grotesk** | `font-sans` | Corps, boutons, labels, metadata |
| **JetBrains Mono** | `font-mono` | Code, JSON, résultats d'outils |

### Échelle typographique

| Classe utilitaire | Taille | Poids | Police | Usage |
|-------------------|--------|-------|--------|-------|
| `text-hero` | `40px` | 700 | Cinzel | Titres hero (banners de salle) |
| `text-h1` | `28px` | 600 | Space Grotesk | Titres de page |
| `text-h2` | `20px` | 600 | Space Grotesk | Sous-titres, section headers |
| `text-h3` | `16px` | 600 | Space Grotesk | Headers de card |
| `text-body` | `14px` | 400 | Space Grotesk | Corps principal |
| `text-sm` | `12px` | 400 | Space Grotesk | Labels, metadata |
| `text-xs` | `11px` | 400 | Space Grotesk | Badges, timestamps, uppercase |

---

## 4. Densité — Style Notion / Linear aéré

**Grille de base : 8px** — tous les espacements sont des multiples de 8.

### Espacements canoniques

| Nom | Valeur | Usage type |
|-----|--------|-----------|
| `4px` | micro | Gaps internes (icône ↔ texte) |
| `8px` | sm | Gaps entre items de liste |
| `16px` | md | Padding card interne, gaps grille |
| `24px` | lg | Padding section, padding drawer |
| `32px` | xl | Séparations de blocs |
| `48px` | 2xl | Marges de page, hero padding |
| `64px` | 3xl | Sections majeures |

### Règles spécifiques "aéré"

- **Padding card** : `24px` minimum (jamais `12px`)
- **Row height table** : `52px`
- **Line-height corps** : `1.6`
- **Padding input** : `12px 16px`
- **Gap entre cards** : `16px`
- **Marge latérale page** : `32px` desktop, `16px` mobile

---

## 5. Composants

### 5.1 Bouton

```
Variante PRIMARY (CTA rouge)
  bg: #C00000 (--red-doge)
  text: #F2F2F2
  border: none
  border-radius: 12px
  padding: 10px 20px
  font: Space Grotesk 14px semibold
  hover: bg #A00000, box-shadow: 0 0 0 1px rgba(192,0,0,0.4)
  active: scale(0.98)
  disabled: opacity 0.4, cursor not-allowed

Variante SECONDARY
  bg: transparent
  border: 1px solid #2a2a2a (--border-default)
  text: #F2F2F2
  hover: border #3a3a3a, bg #1a1a1a
  border-radius: 12px

Variante GHOST
  bg: transparent
  text: #999999 (--text-secondary)
  hover: text #F2F2F2, bg #1a1a1a
  border: none

Variante DANGER
  bg: #500000
  border: 1px solid #8A0000 (--red-dark)
  text: #FF1A1A (--red-glow)
  hover: bg #700000
```

### 5.2 Input / Textarea

```
bg: #111111 (--bg-surface)
border: 1px solid #2a2a2a (--border-default)
border-radius: 8px
padding: 12px 16px
font: Space Grotesk 14px
color: #F2F2F2

Focus:
  border-color: #8A0000 (--red-dark)
  outline: none
  box-shadow: 0 0 0 3px rgba(192,0,0,0.15)

Placeholder: #555555 (--text-muted)
Error: border-color #FF1A1A, box-shadow glow rouge
```

### 5.3 Card (tablette-marbre)

```
bg: #111111 (--bg-surface)
border: 1px solid #2a2a2a (--border-default)
border-radius: 12px
padding: 24px
box-shadow: card (existant)

Hover:
  border-color: #8A0000 (--border-accent)
  transition: 200ms ease
```

### 5.4 Badge — Pill

```
border-radius: 9999px
padding: 3px 10px
font: Space Grotesk 11px uppercase letter-spacing 0.05em

Variantes (bg à 10% d'opacité) :
  default:  bg rgba(85,85,85,0.15)   text #999
  success:  bg rgba(77,255,145,0.12) text #4dff91
  warning:  bg rgba(255,153,0,0.12)  text #FF9900
  error:    bg rgba(255,26,26,0.12)  text #FF1A1A
  info:     bg rgba(41,121,255,0.12) text #2979FF
  accent:   bg rgba(192,0,0,0.12)    text #C00000
```

### 5.5 Table

```
Header row:
  bg: #0a0a0a (--bg-base)
  text: #999999 uppercase 11px letter-spacing 0.08em
  border-bottom: 1px solid #2a2a2a
  padding: 0 16px, height: 40px

Data row:
  height: 52px
  padding: 0 16px
  border-bottom: 1px solid #1a1a1a (--border-subtle)
  hover: bg #1a1a1a, cursor pointer

Row selected:
  bg: rgba(192,0,0,0.06)
  border-left: 2px solid #8A0000
```

### 5.6 Sheet Drawer (CRM détail)

```
Position: fixed right-0, top-0, height 100vh
Largeur: 560px (desktop) | 100% (mobile < 640px)
bg: #111111 (--bg-surface)
border-left: 1px solid #2a2a2a
padding: 32px
z-index: 50

Overlay: rgba(0,0,0,0.7), backdrop-filter blur(4px)
Animation: transform translateX(100% → 0), 300ms cubic-bezier(0.4,0,0.2,1)

Header du drawer:
  Nom + statut badge
  Bouton Fermer (X) top-right
  border-bottom: 1px solid #2a2a2a
  padding-bottom: 24px mb-24px

Sections internes:
  padding: 24px 0
  border-bottom: 1px solid #1a1a1a
```

### 5.7 Kanban Deals

```
Layout: grille de colonnes flex, overflow-x scroll
Largeur colonne: 260px (fixe)
Gap entre colonnes: 16px
Padding grille: 24px

Header colonne:
  font: 12px uppercase semibold, #999999
  badge count: pills blanche/muted
  border-bottom: 2px solid [stage-color]
  margin-bottom: 16px

Card deal (dans colonne):
  bg: #111111
  border: 1px solid #2a2a2a
  border-radius: 8px
  padding: 16px
  margin-bottom: 8px
  hover: border #3a3a3a, shadow card
  cursor: pointer → ouvre Sheet Drawer

Couleurs par stage (border-top 3px):
  Prospecting:  #555555
  Qualified:    #2979FF
  Proposal:     #FF9900
  Negotiation:  #7B1FA2
  Won:          #00C853
  Lost:         #C00000
```

---

## 6. Chat UI

### Layout (conservé — décision #4)

- Plein-écran sans sidebar de conversations
- Hero banner en haut (220px, photo palazzo + overlays)
- Fil de messages scrollable au centre
- Input fixe en bas
- Tool cards inline dans le fil (ToolInvocationCard actuelle)

### Messages

```
Message utilisateur:
  bg: #220000 (--red-deep)
  border: 1px solid #8A0000 (--red-dark)
  border-radius: 12px 12px 2px 12px
  max-width: 70%
  align: flex-end (droite)
  padding: 12px 16px

Message assistant:
  bg: #111111 (--bg-surface)
  border: 1px solid #2a2a2a (--border-default)
  border-radius: 12px 12px 12px 2px
  max-width: 85%
  align: flex-start (gauche)
  padding: 12px 16px
```

### Tool cards (ajustement densité aérée)

- Padding : `16px` → `24px`
- Couleurs services MCP : inchangées
- Expandable JSON : conserver
- Titre service : 11px uppercase, couleur du service

---

## 7. Ton IA

- **Langue** : Français par défaut. Bascule FR/EN à implémenter en AXE futur (i18n).
- **Registre** : Tutoiement professionnel — ni trop formel, ni familier.
- **Ton** : Concis, factuel, orienté action.
  - ✅ *"3 deals à relancer cette semaine."*
  - ❌ *"Il semblerait que vous ayez plusieurs opportunités qui pourraient nécessiter..."*
- **Format réponses** : Résumé court d'abord, détail expandable si nécessaire.
- **Erreurs** : Direct et utile. *"Je n'ai pas trouvé ce contact. Essaie avec le nom de l'entreprise."*

---

## 8. Branding

- **Nom produit** : `RevOps IA` — définitif.
- **Logo** : `⚡` (Zap) — conservé pour le MVP.
- **Tagline** : *"Intelligence pour vos RevOps"*

### Noms des Salles (hero banners)

Chaque section a un nom thématique Palazzo vénitien affiché dans le hero :

| Section | Nom de salle |
|---------|-------------|
| Dashboard | *Salle du Doge* |
| Chat IA | *Salle du Guide* |
| CRM | *Salle des Contacts* |
| Billing | *Chambre des Comptes* |
| Analytics | *Observatoire* |
| Sequences | *Scriptorium* |
| Documents | *Bibliothèque* |
| Paramètres | *Chancellerie* |

---

## 9. Onboarding — Invite-Only

- **Pas de formulaire d'inscription public** — `/register` n'existe pas côté frontend.
- **Flow** : email d'invitation → lien tokenisé unique → page de création de compte.
- **Page `/login`** : reste accessible (membres déjà invités).
- **Backend** : endpoint `POST /api/v1/auth/invite` à implémenter en AXE futur.
- **UI** : page de login sobre avec champ email + password. Lien *"Contacter l'équipe"* pour accès.

---

## 10. Empty States

> **C'est quoi un "empty state" ?** C'est l'écran qu'on voit quand une liste est vide : par exemple, quand il n'y a encore aucun contact, aucun deal, ou aucun document. Plutôt que d'afficher un tableau vide et déconcertant, on affiche une illustration + un message + un bouton d'action.

### Structure standard

```
┌─────────────────────────────────────────────┐
│                                             │
│         [Illustration SVG 120×120]          │
│                                             │
│         Aucun contact pour l'instant        │  ← 16px semibold, text-primary
│                                             │
│   Commence par ajouter ton premier client   │  ← 14px, text-secondary
│                                             │
│         [ + Ajouter un contact ]            │  ← Bouton PRIMARY
│                                             │
└─────────────────────────────────────────────┘
```

### Par page

| Page | Illustration | Titre | CTA |
|------|-------------|-------|-----|
| Contacts | Carnet vénitien | *"Aucun contact pour l'instant"* | + Ajouter un contact |
| Accounts | Portail palazzo | *"Aucun compte client"* | + Ajouter un compte |
| Deals | Contrat avec sceau ducal | *"Pas encore de deal"* | + Créer un deal |
| Chat | Flambeau allumé | *"Pose ta première question"* | — |
| Séquences | Parchemin déroulé | *"Aucune séquence active"* | + Créer une séquence |
| Documents | Bibliothèque vide | *"Aucun document indexé"* | + Uploader |
| Activités | Horloge vénitienne | *"Aucune activité récente"* | — |

> **Fichiers SVG** : à placer dans `frontend/public/empty/` (ex: `contacts.svg`, `deals.svg`, etc.)  
> Les SVGs doivent utiliser `currentColor` pour s'adapter au thème dark.

---

## 11. Référence AXE E — Implémentation

### Fichiers à modifier / créer

| Priorité | Fichier | Action |
|----------|---------|--------|
| 1 | `frontend/tailwind.config.ts` | Synchroniser tokens (rouge `#C00000` uniformisé, supprimer `#ff0000`) |
| 1 | `frontend/src/app/globals.css` | Consolider palette, ajouter tokens manquants (`--bg-abyss`, etc.) |
| 2 | `frontend/src/components/ui/button.tsx` | Variantes primary / secondary / ghost / danger |
| 2 | `frontend/src/components/ui/input.tsx` | Focus rouge ducal |
| 2 | `frontend/src/components/ui/badge.tsx` | Pills avec variantes sémantiques |
| 3 | `frontend/src/components/ui/empty.tsx` | Nouveau composant `EmptyState` |
| 3 | `frontend/src/components/ui/skeleton.tsx` | Loading skeleton thématique |
| 4 | `frontend/src/components/crm/data-table.tsx` | Table avec row hover + selection |
| 4 | `frontend/src/components/crm/sheet-drawer.tsx` | Drawer slide-in détail fiche |
| 4 | `frontend/src/components/crm/kanban-board.tsx` | Kanban deals |
| 5 | Pages Billing, Sequences, Documents | Mise à jour visuelle avec nouveaux composants |

### Ordre recommandé

1. **Tokens** (`tailwind.config.ts` + `globals.css`) — tout le reste en dépend
2. **Primitives** (`button`, `input`, `badge`) — utilisées partout
3. **EmptyState** + SVGs — visibilité rapide
4. **Skeleton** — perçu comme polish
5. **CRM** (table → drawer → kanban) — cœur fonctionnel
6. **Autres pages** (Billing, Sequences, Documents)

---

*Dernière mise à jour : 2026-04-26 — AXE D complété*
