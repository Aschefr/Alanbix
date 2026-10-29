# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Joueurs** d'une LAN party : ils utilisent Alanbix sur leur PC pendant l'événement (souvent entre deux parties, parfois en jeu) et sur téléphone pour une consultation rapide — scores, brackets, classement, chat, choix de leur place.
- **Organisateur / responsable IT** : crée et pilote les tournois, corrige les scores, gère le plan de salle, les fichiers, la base de connaissances de l'IA.
- **Le public de la salle** : voit le mode spectateur affiché au projecteur / TV, sans interaction.

## Product Purpose

Système auto-hébergé de gestion de LAN party : tournois multi-formats avec scores en direct, classements, plan de salle interactif, messagerie, et assistant IA local (Ollama + RAG) qui répond aux questions techniques des joueurs. Réussite = l'organisateur n'a plus besoin de tableau blanc ni de micro, et les joueurs trouvent seuls l'info (prochain match, place, règles).

## Positioning

Tout-en-un, local et léger (un conteneur, une base SQLite), avec un assistant IA qui tourne sur la machine de la LAN — pas de cloud, fonctionne hors internet.

## Operating Context

Salle de LAN, réseau local, éclairage souvent faible, joueurs concentrés sur leur jeu. Mises à jour temps réel par WebSocket. Mode spectateur en cycle automatique sur grand écran. Interface bilingue (i18n fr/en).

## Capabilities and Constraints

Tournois (élimination simple/double, round robin, FFA), points calculés côté serveur, verrouillage des scores, équipes et référents, classements individuels et par équipes, profils, page d'infos Markdown + fichiers, chat public / privé / équipe, avatars personnalisés, plan de salle drag & drop, mode spectateur. Frontend SvelteKit (Svelte 4, ssr=false), backend FastAPI. Migration Svelte 5 volontairement reportée.

## Brand Commitments

- Nom **Alanbix** (A-LAN-bix) : clin d'œil à Alambix (Astérix) et à l'alambic qui « distille » la connaissance. La silhouette de fiole Alanbix est un élément d'identité.
- **Thème sombre « gamer »** à conserver, **et un thème clair** sur les mêmes tons de couleurs (même palette, deux luminosités).

## Evidence on Hand

Captures dans `screenshots/` (dont `alanbix_dashboard.png`). Pas de témoignages ni de chiffres d'usage — ne pas en inventer.

## Product Principles

1. L'info utile en un coup d'œil : un joueur entre deux parties doit trouver son prochain match en quelques secondes.
2. Le serveur fait foi : scores et points jamais calculés côté client.
3. Lisible dans le noir et de loin (salle sombre, projecteur).
4. Léger et local : rien qui exige internet ou une infra lourde.

## Accessibility & Inclusion

Usage en faible luminosité et à distance (projecteur) : contrastes et tailles suffisants. Pas d'autre exigence formelle établie.
