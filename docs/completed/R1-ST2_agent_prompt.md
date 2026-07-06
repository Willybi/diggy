# R1-ST2 — Layout shell + BottomNav

Tu dois implementer la navigation mobile de Diggy : masquer la sidebar sous 640px et afficher une BottomNav fixe en bas.

Lis `CLAUDE.md` a la racine pour les conventions du projet.
Le brief designer complet est dans `_design/handoff-mobile/BRIEF-mobile.md` (sections a et b).
La maquette de reference est dans `_design/handoff-mobile/Mobile (pilote).html`.

---

## Contexte

Les tokens responsive ont deja ete ajoutes dans ST1 :
```css
--bottom-nav-h: 56px;
--page-px: 30px;
--page-px-mobile: 16px;
--touch-min: 44px;
```

Le layout actuel (`App.vue`) :
- Grid : `grid-template-columns: var(--sidebar-w) 1fr`
- Container query a 900px : sidebar → rail 66px
- Aucun breakpoint sous 640px

---

## Tache 1 : Modifier App.vue

**Fichier** : `server/frontend/src/App.vue`

### Template

Ajouter `<BottomNav v-if="auth.isAuthenticated" />` dans le template, apres le `<Transition>` du PlayerBar :

```html
<BottomNav v-if="auth.isAuthenticated" />
```

Importer le composant dans `<script setup>`.

### Styles scoped

Ajouter un breakpoint container a 640px :

```css
@container (max-width: 640px) {
  .app-container {
    --sidebar-w: 0px;
  }
  .app-shell {
    grid-template-columns: 1fr;
  }
  .app-sidebar {
    display: none;
  }
  .app-main {
    padding-bottom: calc(var(--bottom-nav-h) + env(safe-area-inset-bottom, 0px));
  }
  .app-main.has-player {
    padding-bottom: calc(var(--bottom-nav-h) + env(safe-area-inset-bottom, 0px) + 90px);
  }
}
```

Le breakpoint existant a 900px (rail 66px) reste inchange.

---

## Tache 2 : Creer BottomNav.vue

**Fichier** : `server/frontend/src/components/BottomNav.vue` (nouveau)

### Spec (cf. brief §a)

- `position: fixed; bottom: 0; left: 0; right: 0; z-index: 999`
- `height: var(--bottom-nav-h); padding-bottom: env(safe-area-inset-bottom, 0px)`
- `background: var(--surface); border-top: 1px solid var(--line)`
- `display: none` par defaut — visible via `@media (max-width: 640px)` (position fixed = hors flux container, donc @media obligatoire)

### Items

5 items permanents + 1 conditionnel (Admin si `auth.user?.is_admin`) :

| Item | Route | Icone |
|------|-------|-------|
| Hub | `/` | maison (reprendre SVG de SidebarNav.vue) |
| Catalog | `/catalog` | grille 2x2 |
| Artistes | `/artists` | personnes |
| Sets | `/sets` | disque |
| Genres | `/genres` | tag |
| Admin | `/admin` | etoile — `v-if="auth.user?.is_admin"` (non-rendu, pas masque CSS) |

### Anatomie par item

- `flex: 1` (repartition egale)
- Layout : `flex-direction: column; align-items: center; justify-content: center; gap: 4px`
- Icone SVG `22px`
- Label : `font: 500 10px/1 var(--font-mono)`
- Utiliser `<RouterLink :to="route" custom v-slot="{ isActive, navigate }">` pour le highlight actif
- Inactif : `color: var(--ink-3)` — Active : `color: var(--accent)`
- Highlight route active : barre 26x3px `--accent` collee en haut de l'item (pseudo-element `::before`)

### Badge count (radar new count)

- Sur l'item Hub (ou Catalog selon le plus pertinent), afficher un badge avec le nombre de nouvelles tracks radar
- Pastille : `background: var(--accent); color: var(--on-accent); font: 600 9px/1 var(--font-mono)`
- Position : `position: absolute; top: 5px; left: calc(50% + 9px)`
- Recuperer le count via l'API : `GET /api/radar/new-count` (renvoie `{ count: N }`)
- Ne pas afficher si count = 0
- Rafraichir au mount + quand la route change

### Icones SVG

Reprendre les SVG inline de `SidebarNav.vue` (lignes 74-83). Meme set d'icones, meme `viewBox="0 0 24 24"`, meme stroke-width.

---

## Points d'attention

- **@media, pas @container** : la BottomNav est `position: fixed`, elle est hors du flux container. Le show/hide doit etre via `@media (max-width: 640px)`.
- **Z-index** : BottomNav `999` (brief dit 50 mais en pratique le PlayerBar est a `1000` dans le code actuel — garder BottomNav en dessous du PlayerBar).
- **Safe area** : `padding-bottom: env(safe-area-inset-bottom, 0px)` pour les iPhones a encoche.
- **SidebarNav.vue** : ne pas modifier. Le masquage est gere par App.vue (`display: none` sur `.app-sidebar`).
- **router.js** : ne pas modifier. Les routes existent deja.

---

## Definition of Done

```bash
# Chrome DevTools → iPhone SE (375px) :
# - Sidebar invisible
# - BottomNav visible avec 5 items (6 si admin)
# - Navigation fonctionnelle (chaque item route correctement)
# - Route active mise en avant (accent + barre)
# - Badge count radar visible si > 0
#
# Chrome DevTools → iPad (768px) :
# - Sidebar rail visible
# - Pas de BottomNav
#
# Desktop (1440px) :
# - Aucun changement
#
# Lint :
cd server/frontend && npm run lint
```

## Commit

```
feat(frontend): add BottomNav + hide sidebar on mobile (R1-ST2)
```

Ne pousse PAS sur master — je review avant.
