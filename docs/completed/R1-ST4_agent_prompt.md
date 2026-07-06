# R1-ST4 — Composants partages (modales, cibles tactiles, filtres)

Tu dois adapter les composants partages pour le mobile : modale plein ecran, cibles tactiles 44px, hover-only → toujours visible, filtres en scroll horizontal.

Lis `CLAUDE.md` a la racine pour les conventions du projet.
Le brief designer est dans `_design/handoff-mobile/BRIEF-mobile.md` (sections e et f).

---

## Tache 1 : Modale import — plein ecran sur mobile

**Fichier** : `server/frontend/src/components/ImportRekordboxModal.vue`

La modale est actuellement `max-width: 480px; padding: 28px`. Sur mobile, elle doit devenir plein ecran.

La modale est `position: fixed` → **`@media` obligatoire**.

Ajouter a la fin du `<style scoped>` :

```css
@media (max-width: 640px) {
  .modal-overlay {
    padding: 0;
  }
  .modal-box {
    max-width: 100%;
    height: 100%;
    border-radius: 0;
    padding: 20px var(--page-px-mobile, 16px);
  }
}
```

---

## Tache 2 : Hover-only → toujours visible

**Fichier** : `server/frontend/src/assets/table.css`

Les boutons play (`.pbtn` dans les vues) et les boutons LikeDislike (`.act`) sont `opacity: 0` en desktop, reveles au hover. Sur mobile, pas de hover → les rendre toujours visibles.

Ajouter a la fin de `table.css` :

```css
@media (max-width: 640px) {
  table.dt .pbtn,
  table.dt .act {
    opacity: 1;
  }
}
```

Note : on utilise `@media` ici car c'est un comportement global (pas specifique a un container).

---

## Tache 3 : Chips/filtres en scroll horizontal

Les chips de filtre dans CatalogView (`.head-tools`) contiennent SearchBox + chips toggle + viewseg. Sur mobile ils debordent.

**Fichier** : `server/frontend/src/views/CatalogView.vue`

Chercher le style `.head-tools` dans le `<style scoped>`. Ajouter un container query pour le scroll horizontal :

```css
@container app (max-width: 640px) {
  .head-tools {
    overflow-x: auto;
    flex-wrap: nowrap;
    scrollbar-width: none;
    -webkit-overflow-scrolling: touch;
  }
  .head-tools::-webkit-scrollbar {
    display: none;
  }
}
```

Verifier aussi que les `.chip` dans CatalogView ont `flex: none` ou `white-space: nowrap` pour ne pas se comprimer (ils l'ont probablement deja — verifier avant d'ajouter).

---

## Tache 4 : Table min-width

**Fichier** : `server/frontend/src/assets/table.css`

La table `.dt` a `min-width: 720px` (ligne 9). Sur mobile, quand les colonnes sont masquees (ST5), cette min-width force un scroll horizontal inutile.

Ajouter :

```css
@media (max-width: 640px) {
  table.dt {
    min-width: 0;
  }
}
```

---

## Points d'attention

- Ne pas toucher aux styles desktop (tout est conditionne a max-width 640px)
- La modale et les tables utilisent `@media` (elements fixed ou comportement global)
- Les chips dans CatalogView utilisent `@container app` (coherent avec le reste des vues)
- Verifier que `--page-px-mobile` est bien defini dans les tokens (ST1 l'a ajoute)

---

## Definition of Done

```bash
# Chrome DevTools → iPhone SE (375px) :
# - Modale import = plein ecran
# - Boutons play visibles dans les tables (pas besoin de hover)
# - Chips de filtre scrollables horizontalement (pas de debordement)
# - Table sans scroll horizontal parasite (quand colonnes masquees)
#
# Desktop (1440px) :
# - Modale flottante 480px (inchangee)
# - Boutons play reveles au hover (inchanges)
# - Chips wrappent normalement
#
# Lint :
cd server/frontend && npm run lint
```

## Commit

```
feat(frontend): mobile modals, touch targets, scroll filters (R1-ST4)
```

Ne pousse PAS sur master — je review avant.
