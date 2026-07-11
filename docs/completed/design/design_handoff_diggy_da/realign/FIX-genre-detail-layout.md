# FIX — Genre Detail : centrage, max-width & responsive

> Tweak layout post-implémentation (retour willi). 2 fichiers, 3 petites modifs. 100% tokens, rien de cassé ailleurs.

## Cause

1. `.detail-view` (dans `GenreDetailView.vue`) = `max-width: 900px` **sans `margin: auto`** → colonne étroite **calée à gauche**, gros vide à droite (la zone `.app-main` est `1fr`, bien plus large).
2. Les media queries de la vue utilisent `@container app (...)` mais le conteneur déclaré dans `App.vue` (`.app-container { container-type: inline-size }`) **n'est pas nommé `app`** → ces règles **ne s'appliquent jamais** (responsive de la page inopérant).

## Fix 1 — centrer + élargir la colonne (`views/GenreDetailView.vue`)

```css
.detail-view {
  max-width: 1080px;        /* ~ largeur de la maquette pilote (sidebar 232 + ~1088) */
  margin-inline: auto;      /* centre la colonne dans la zone main */
  padding: 26px 30px 56px;  /* un peu plus d'air que var(--pad) */
}
```

- `1080px` = compromis : assez large pour les shelves/mosaïque, assez serré pour que la tracklist reste lisible. Ajustable 1040–1160 selon ton goût.
- `margin-inline: auto` centre dans l'espace **après la sidebar** (comportement voulu).

## Fix 2 — nommer le conteneur pour réactiver le responsive (`App.vue`)

```css
.app-main {
  min-width: 0;
  overflow-y: auto;
  container: app / inline-size;   /* nomme le conteneur → les @container app (...) des vues fonctionnent */
}
```

- Mesure désormais la **largeur de la zone contenu** (post-sidebar), pas le viewport entier → breakpoints `820 / 640 / 560` corrects.
- N'affecte pas le `@container (max-width: 900px)` d'`App.vue` (qui collapse la sidebar) : il cible `.app-shell` via `.app-container`, hors de `.app-main`.

## Cohérence (optionnel, recommandé à terme)

Pour que **toutes** les pages partagent le même cadre, hisser `max-width` + `margin-inline:auto` sur un wrapper commun autour du `<RouterView>` dans `App.vue` (ex. `.app-page`) et retirer les `max-width` par vue. À faire seulement si les autres vues (Catalog, Genres, détails) ne sont pas déjà alignées sur la même largeur — à vérifier d'abord.
