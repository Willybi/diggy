# R1-ST3 — PlayerBar mobile

Tu dois repositionner le PlayerBar au-dessus de la BottomNav sur mobile.

Lis `CLAUDE.md` a la racine pour les conventions du projet.
Le brief designer est dans `_design/handoff-mobile/BRIEF-mobile.md` (section c).

---

## Contexte

ST2 a ajoute la BottomNav (56px + safe area, fixee en bas). Le PlayerBar est `position: fixed; bottom: 18px` et assume la sidebar toujours visible (`left: calc(var(--sidebar-w, 232px) + 24px)`).

Sur mobile (< 640px), la sidebar a disparu et la BottomNav est en bas. Le PlayerBar doit se repositionner au-dessus.

---

## Tache : Modifier PlayerBar.vue

**Fichier** : `server/frontend/src/components/PlayerBar.vue`

### CSS actuel (lignes 162-170)

```css
.player {
  position: fixed;
  bottom: 18px;
  left: calc(var(--sidebar-w, 232px) + 24px);
  right: 24px;
  max-width: 1200px;
  margin: 0 auto;
  z-index: 1000;
}
```

### Ajouter une media query mobile

Le PlayerBar est `position: fixed` → hors flux container → **`@media` obligatoire** (seule exception du projet avec la BottomNav).

```css
@media (max-width: 640px) {
  .player {
    left: 8px;
    right: 8px;
    bottom: calc(var(--bottom-nav-h) + env(safe-area-inset-bottom, 0px) + 8px);
  }
}
```

### Ce qui ne change PAS

- Les container queries internes existantes (lignes 440-459) restent inchangees :
  - `@container player (max-width: 720px)` : masque `.pl-stats` (BPM/Key)
  - `@container player (max-width: 560px)` : masque `.pl-elapsed`, `.pl-remain`
  - `@container player (max-width: 440px)` : masque `.pl-vol`, reduit gap/padding
- Sur 375px de large, le bandeau fait ~359px → seuls play/pause + equalizer + identite + scrub + close sont visibles. C'est le bon comportement.
- L'animation `prefers-reduced-motion` reste inchangee.

---

## Points d'attention

- `--bottom-nav-h` est defini dans `diggy-tokens.css` (ST1) : `56px`
- Le z-index du PlayerBar (`1000`) reste au-dessus de la BottomNav (`999`)
- Tester que le scrub tactile fonctionne (pointer events) — le code existant utilise `touch-action: none` sur `.pl-rail`, c'est correct

---

## Definition of Done

```bash
# Chrome DevTools → iPhone SE (375px) :
# - PlayerBar au-dessus de la BottomNav (pas de chevauchement)
# - Marges laterales 8px
# - Play/pause + identite + scrub + close visibles
# - Scrub tactile fonctionnel
#
# Desktop (1440px) :
# - Aucun changement
#
# Lint :
cd server/frontend && npm run lint
```

## Commit

```
fix(frontend): reposition PlayerBar above BottomNav on mobile (R1-ST3)
```

Ne pousse PAS sur master — je review avant.
