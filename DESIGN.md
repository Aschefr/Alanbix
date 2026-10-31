---
name: Alanbix
description: L'alambic qui distille votre LAN — gestion de LAN party auto-hébergée
colors:
  alembic-blue: "#3b82f6"
  alembic-blue-light-theme: "#2563eb"
  distillate-violet: "#a855f7"
  night-slate: "#0f172a"
  panel-slate: "#1e293b"
  raised-slate: "#334155"
  frost-text: "#f8fafc"
  mist-text: "#94a3b8"
  daylight-bg: "#f1f5f9"
  daylight-panel: "#ffffff"
  daylight-border: "#cbd5e1"
  ink-text: "#0f172a"
  victory-green: "#22c55e"
  alert-red: "#ef4444"
  admin-amber: "#f59e0b"
typography:
  display:
    fontFamily: "Bricolage Grotesque, Segoe UI, system-ui, sans-serif"
    fontSize: "2rem"
    fontWeight: 700
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Bricolage Grotesque, Segoe UI, system-ui, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 700
  body:
    fontFamily: "Onest, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
  label:
    fontFamily: "Onest, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 600
    letterSpacing: "0.05em"
rounded:
  sm: "4px"
  md: "8px"
  lg: "12px"
  xl: "20px"
  modal: "16px"
spacing:
  xs: "0.5rem"
  sm: "0.75rem"
  md: "1rem"
  lg: "1.5rem"
components:
  button-primary:
    backgroundColor: "{colors.alembic-blue}"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
    padding: "0.75rem 1.5rem"
  button-success:
    backgroundColor: "{colors.victory-green}"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
    padding: "0.75rem 1.5rem"
  glass-panel:
    backgroundColor: "rgba(15, 23, 42, 0.65)"
    rounded: "{rounded.lg}"
  input:
    backgroundColor: "rgba(15, 23, 42, 0.5)"
    textColor: "{colors.frost-text}"
    rounded: "{rounded.md}"
---

# Design System: Alanbix

## Overview

**Creative North Star: "Le Labo de l'Alambic"**

Alanbix est un alambic : du verre, un liquide bleu qui distille l'information, des reflets nets. L'interface est un laboratoire nocturne, avec des panneaux de verre fumé posés sur un fond ardoise profond. Un halo bleu et violet très diffus flotte derrière eux, comme la lueur d'un liquide. La fiole penchée (logo `logo-alambic`, remplie de bleu) est la signature visuelle et réapparaît dans le chargement (bulles qui bouillonnent).

L'application est un outil (mode Operate) : la lisibilité dans une salle sombre, sur PC, téléphone et projecteur, passe avant l'effet. Le thème sombre est le thème par défaut. Le thème clair reprend exactement les mêmes teintes (ardoise + bleu) en version lumineuse : c'est le même labo, de jour.

**Key Characteristics:**
- Fond ardoise nuit, panneaux de verre fumé avec un liseré clair en haut (reflet).
- Un seul bleu d'action ; le violet est réservé à ce qui doit ressortir (mentions, mises en avant).
- Titres en Bricolage Grotesque, texte en Onest, polices embarquées localement (fonctionne hors internet).
- Emojis utilisés comme icônes de navigation et de statut (🏆 🔒 👑 🛡️ ⚔️).
- Mobile (≤ 900px) : version compacte et plus « géométrique » (coins presque droits).

## Colors

Palette froide ardoise + bleu, déclinée en deux luminosités qui partagent les mêmes teintes.

### Primary
- **Bleu Alambic** (#3b82f6 en sombre, #2563eb en clair) : boutons principaux, liens, étape active, liquide de la fiole, halo des boutons (`--accent-glow`).

### Secondary
- **Violet Distillat** (#a855f7) : mise en avant uniquement (messages qui te mentionnent, surlignage, boutons de chat d'équipe qui pulsent). Fond `--highlight-bg` translucide.

### Tertiary
- **Ambre Admin** (#f59e0b) : signale l'espace d'administration (lien « Administration ») et les avertissements ; aussi les coéquipiers sur le plan de salle.

### Neutral
- **Ardoise Nuit** (#0f172a) : fond de page sombre ; texte principal en clair.
- **Ardoise Panneau** (#1e293b) / **Ardoise Relief** (#334155) : surfaces secondaires et tertiaires.
- **Givre** (#f8fafc) : texte principal en sombre. **Brume** (#94a3b8) : texte secondaire en sombre (#475569 en clair).
- **Jour** (#f1f5f9) fond clair, panneaux blancs (#ffffff), bordures #cbd5e1.
- États : **Vert Victoire** (#22c55e / #16a34a), **Rouge Alerte** (#ef4444 / #dc2626).

### Named Rules
**La Règle du Liquide Unique.** Le bleu est la seule couleur d'action. Un bouton principal par zone ; le violet ne déclenche jamais d'action, il attire seulement l'œil.

**La Règle des Deux Luminosités.** Tout token existe en paire sombre/clair (`:root` puis `[data-theme="light"]`) avec la même teinte. Une couleur ajoutée sans son pendant clair est un bug.

## Typography

**Display Font:** Bricolage Grotesque (variable 200–800, avec Segoe UI, system-ui)
**Body Font:** Onest (variable 100–900, avec -apple-system, Segoe UI, Roboto)

**Character:** Bricolage Grotesque, expressive et un peu « bricolée » (en accord avec l'humour de la mascotte), porte les titres et le nom Alanbix ; Onest, neutre et très lisible en petit, porte tout le reste. Choisies le 2026-10-31 en remplacement d'Outfit et Inter (comparaison visuelle, option B).

### Hierarchy
Une seule échelle, en variables dans `app.css` ; chaque page s'y réfère au lieu de fixer ses propres tailles.
- **Titre de page** `--fs-page` (700, 1.625rem ; 1.375rem sur mobile) : un seul `h1` par page ; `title-premium` y ajoute le dégradé blanc → brume (sombre) ou encre → bleu (clair).
- **Titre de section** `--fs-section` (700, 1.0625rem) : en-têtes de blocs (« Mes matchs », « Appels à l'aide »).
- **Sous-section / onglets** `--fs-sub` (600–700, 0.875rem) : sous-titres en capitales espacées, onglets internes.
- **Menu latéral** `--fs-nav` (600, 0.9375rem) : la page active a un fond bleu léger et un trait bleu à gauche.
- **Body** (400, 1rem) : texte courant, champs.
- **Label** (600, 0.75rem, majuscules, espacement léger) : étiquettes de champs, badges.

## Layout

Bureau : barre latérale fixe à gauche (~200px, panneau de verre arrondi) avec logo, navigation emoji + libellé, lien Administration séparé, carte utilisateur et actions en bas ; contenu centré à droite. Bandeaux d'information pleine largeur en haut du contenu.

Mobile (≤ 900px) : barre du haut compacte (40px, logo + icônes d'action) et barre d'onglets en bas (44px : Accueil, Tournois, Messages, Assistant, Profil). Respect des zones sûres (`--safe-*`). Densité resserrée, coins presque droits.

Espacements : base 1rem, boutons 0.75rem × 1.5rem, conteneurs avec gap de 1rem.

## Elevation & Depth

Profondeur par **verre superposé** plutôt que par ombres fortes : surfaces translucides (`rgba(15,23,42,0.65)`), liseré supérieur plus clair qui simule un reflet, ombre ambiante douce et large. Les boutons d'action portent un halo coloré de leur propre teinte, qui s'intensifie au survol avec un léger soulèvement (-2px). Les fenêtres modales flottent au-dessus d'un voile flouté (blur 8px).

### Shadow Vocabulary
- **Verre** (`0 10px 40px -10px rgba(0,0,0,0.5)` sombre / `0 4px 16px -2px rgba(15,23,42,0.08)` clair) : panneaux `.glass`.
- **Halo d'action** (`0 4px 14px 0 var(--accent-glow)`, survol `0 6px 20px 0`) : boutons principaux et de succès.
- **Modale** (`0 30px 70px rgba(0,0,0,0.45)`) : fenêtres globales.

### Named Rules
**La Règle du Reflet.** Un panneau de verre a toujours son liseré supérieur plus clair ; c'est ce qui le distingue d'une simple boîte.

## Shapes

Coins doucement arrondis sur bureau (petit 4px, moyen 8px, panneau 12px, grand 20px, modale 16px), cercles pour les avatars (forme choisie par l'utilisateur : cercle, carré arrondi ou carré, propagée partout) et pastilles d'étapes. Sur mobile, les rayons tombent à 2/3/4px pour un rendu plat et géométrique. La fiole du logo a une forme propre (`50% 50% 50% 10%`, inclinée de -15°).

## Components

### Buttons
- **Shape:** coins moyens (8px).
- **Primary:** fond Bleu Alambic, texte blanc, 600, padding 0.75rem × 1.5rem, halo bleu.
- **Hover / Focus:** soulèvement de 2px, halo plus large, luminosité +10 % ; retour à plat à l'appui.
- **Success / Danger:** même forme en vert ou rouge ; variantes danger compactes, rondes et contour.
- **Secondary / Ghost:** fond translucide, texte discret (« Passer »).

### Cards / Containers
- **Corner Style:** 12px (4px mobile).
- **Background:** verre fumé en sombre, blanc en clair.
- **Shadow Strategy:** voir Verre.
- **Border:** 1px très discret + liseré supérieur clair.
- **Internal Padding:** ~1.5–3rem selon la carte.

### Inputs / Fields
- **Style:** fond ardoise translucide (blanc en clair), bordure discrète, coins 8px, étiquette en majuscules au-dessus.
- **Focus:** bordure bleue.

### Navigation
- **Bureau:** emoji + libellé Onest, élément actif mis en évidence ; Administration en ambre, séparée par un trait.
- **Mobile:** onglets du bas avec icônes au trait et libellé court ; actif en bleu.

### La Fiole (Signature)
Logo `logo-alambic` : contour bleu 2px, liquide bleu à 60 % d'opacité qui luit ; version chargement avec liquide qui bouillonne et bulles qui montent.

## Do's and Don'ts

### Do:
- **Do** utiliser les variables CSS (`--accent`, `--glass-bg`, `--text-dim`…) plutôt que des couleurs en dur, pour que les deux thèmes suivent.
- **Do** définir chaque nouveau token dans `:root` **et** dans `[data-theme="light"]`.
- **Do** garder un seul bouton bleu principal par zone.
- **Do** vérifier chaque écran en sombre, en clair, sur mobile et à distance (projecteur).

### Don't:
- **Don't** abandonner la fiole/alambic ni le thème sombre : ce sont des engagements d'identité.
- **Don't** utiliser le violet comme couleur d'action ; il reste réservé à la mise en avant.
- **Don't** introduire une police chargée depuis internet : l'appli doit fonctionner hors ligne.
