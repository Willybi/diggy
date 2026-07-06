# R1-ST5 — Vues individuelles responsive

Tu dois adapter chaque vue de Diggy pour le mobile (< 640px). C'est la derniere sous-tache de R1.

Lis `CLAUDE.md` a la racine pour les conventions du projet.
Le brief designer est dans `_design/handoff-mobile/BRIEF-mobile.md` (sections d et g).
La maquette de reference est dans `_design/handoff-mobile/Mobile (pilote).html`.

---

## Contexte

Les fondations sont en place (ST1-ST4) :
- Tokens responsive (`--bottom-nav-h`, `--page-px-mobile`, `--touch-min`)
- BottomNav visible sous 640px, sidebar masquee
- PlayerBar repositionne au-dessus de la BottomNav
- Modale plein ecran, hover-only → visible, table min-width 0, chips scroll

Il reste a adapter chaque vue individuellement. Utilise `@container app` pour tous les breakpoints (sauf si un composant est `position: fixed`).

---

## Vue 1 : CatalogView (priorite haute)

**Fichier** : `server/frontend/src/views/CatalogView.vue`

### Colonnes qui tombent (brief §d)

La table a des classes CSS sur les colonnes (verifier les noms exacts dans le fichier). Ajouter les container queries pour masquer les colonnes progressivement. L'ordre de chute du brief :

```css
@container app (max-width: 1160px) { .col-dur { display: none; } }
@container app (max-width: 1010px) { .col-rating { display: none; } }
@container app (max-width: 900px)  { .col-avis { display: none; } }
@container app (max-width: 760px)  { .col-radar { display: none; } }
@container app (max-width: 620px)  { .col-style { display: none; } }
@container app (max-width: 560px)  { .col-bpm { display: none; } }
```

**Attention** : certains de ces breakpoints existent peut-etre deja dans le code. Verifier avant d'ajouter pour ne pas dupliquer. Certaines colonnes sont conditionnelles (radar-only, catalog-only) — les masquages s'appliquent en plus.

### Layout mobile (< 640px)

```css
@container app (max-width: 640px) {
  .page-head {
    padding: 16px var(--page-px-mobile) 12px;
  }
  .page-head h1 {
    font-size: 23px;
  }
  .head-tools {
    width: 100%;
    margin-left: 0;
  }
  .table-wrap {
    padding: 4px var(--page-px-mobile) 22px;
  }
}
```

Sur 375px survivent : **Play · Track · Key · InLib**.

---

## Vue 2 : ArtistDetailView

**Fichier** : `server/frontend/src/views/ArtistDetailView.vue`

- Hero : `flex-direction: column` sous 640px (empiler avatar + body)
- Avatar centre, pleine largeur ou max 200px
- Mini-rows tracks : sous 500px, masquer BPM et Key (garder cover + titre + LibDot)
- Padding lateral : `var(--page-px-mobile)`
- Blocs relationnels : 1 colonne

Chercher les classes existantes et ajouter les container queries correspondantes.

---

## Vue 3 : SetDetailView

**Fichier** : `server/frontend/src/views/SetDetailView.vue`

- Tracklist : masquer Style et Time sous 640px, BPM sous 500px
- Survivent sur 375px : # · Play · Cover+Titre · Key · LibDot
- Anneau % : centre au-dessus de la tracklist
- Hero : empile si applicable
- Play buttons toujours visibles (deja gere par ST4)

---

## Vue 4 : SetsView

**Fichier** : `server/frontend/src/views/SetsView.vue`

Deja partiellement responsive (container queries a 1040/820/600px). Ajouter sous 640px :
- Formulaire d'ajout (`.addrow` ou equivalent) : `flex-direction: column`, CTA pleine largeur
- Padding : `var(--page-px-mobile)`

---

## Vue 5 : GenresView

**Fichier** : `server/frontend/src/views/GenresView.vue`

Deja responsive (720/640/520px). Verifier :
- Grille : `minmax(150px, 1fr)` sous 640px (cf. brief)
- Padding : `var(--page-px-mobile)`

---

## Vue 6 : GenreDetailView

**Fichier** : `server/frontend/src/views/GenreDetailView.vue`

- Shelves (artistes, sets, playlists) : scroll horizontal (`overflow-x: auto`)
- Tracks : GenreTrackRow masque deja `.dur` sous 640px — verifier
- Padding : `var(--page-px-mobile)`

---

## Vue 7 : HubView

**Fichier** : `server/frontend/src/views/HubView.vue`

Deja des container queries a 680/540px. Verifier :
- Search bar pleine largeur sous 640px
- Resultats empiles (pas cote a cote)
- Shelves : scroll horizontal
- Padding : `var(--page-px-mobile)`

---

## Vue 8 : TrackDetailView

**Fichier** : `server/frontend/src/views/TrackDetailView.vue`

- Hero (PageHero) : `flex-direction: column` sous 640px
- `.rel-cols` : 1 colonne (deja sous 720px — verifier)
- Padding : `var(--page-px-mobile)`

---

## Vue 9 : WatchlistView / PlaylistDetailView

**Fichiers** : `server/frontend/src/views/WatchlistView.vue`, `PlaylistDetailView.vue`

- Padding reduit : `var(--page-px-mobile)`
- Table playlists : verifier qu'aucune colonne ne deborde
- Badge source conserve

---

## Vues basse priorite

- **LoginView** : aucun changement attendu (formulaire centre)
- **AdminView** : verification minimale (pas de debordement horizontal). Ne pas investir de temps dessus.

---

## Regles generales

- Utiliser `@container app` pour tous les breakpoints (sauf elements fixed)
- Padding mobile : `var(--page-px-mobile)` (pas de `16px` en dur)
- Zero couleur hardcodee — tout via `var(--...)`
- Ne pas casser le desktop : tout est conditionne a max-width
- Les breakpoints existants dans les vues restent inchanges (ne pas supprimer)
- Si une vue a deja un breakpoint a 640px qui fait partiellement le job, l'etendre plutot que dupliquer

---

## Definition of Done

```bash
# Chrome DevTools → iPhone SE (375px) :
# - CatalogView : table lisible (Play + Track + Key + InLib), pas de scroll horizontal
# - ArtistDetailView : hero empile, mini-rows lisibles
# - SetDetailView : tracklist allegee, anneau centre
# - GenresView : grille 2 col ou 1 col
# - HubView : search pleine largeur, shelves scrollables
# - TrackDetailView : hero empile, blocs 1 colonne
# - Aucune vue ne deborde horizontalement
#
# Chrome DevTools → iPad (768px) :
# - Sidebar rail visible, pas de BottomNav
# - Vues avec plus de colonnes visibles qu'a 375px
#
# Desktop (1440px) :
# - Aucun changement sur aucune vue
#
# Lint :
cd server/frontend && npm run lint
```

## Commit

```
feat(frontend): responsive views for mobile (R1-ST5)
```

Ne pousse PAS sur master — je review avant.
