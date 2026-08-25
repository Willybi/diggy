# A4 — Audit Frontend (2026-08-24)

Périmètre : `server/frontend/src/`, priorité au delta depuis 2026-08-09 (AV5 TrackTable/AddModal/hub, D9 KeepAlive/prefetch, D8 voir-plus, C5 v2 collections, C7 AlbumView, C9.b « sonne comme », store audioPlayer « écoute active »). Lecture seule, aucun build lancé.

## Ce qui va bien

- **Discipline D9 exemplaire sur les 6 vues cachées** : les 6 vues de l'allowlist portent toutes leur `defineOptions({ name })` exact ; les gardes `route.path !== ownPath` sont présentes aux DEUX niveaux (composables `useUrlSync.js:80` / `useFilterState.js:161` ET watchers locaux `ExplorerView.vue:547`, `RadarView.vue:577`, `SetsView.vue:880`) ; `useVirtualWindow` détache/rattache scroll+resize `onDeactivated`/`onActivated` (l.156-160) ; WatchlistView snapshot ses polls via `crawlPoll.activeKeys()` et les reprend à l'activation (l.636-648) ; le pattern `firstActivate` + `scrollRestore.reapply()` est appliqué uniformément aux 6 vues.
- **Composables sanctionnés respectés partout** : le seul `setInterval` du src vit dans `useTaskPoll.js:72` (sanctionné) ; aucun fetch offset/hasMore artisanal dans les vues nouvelles (Collections/Album chargent des listes complètes non paginées, ce qui est le bon outil) ; `useOpinionOneShot` a bien remplacé les 3 copies (Artists/Sets/Watchlist).
- **Zéro couleur hex/rgb hardcodée** hors logo Google de LoginView (marque, légitime) ; les `@media` restants sont tous soit `prefers-reduced-motion`, soit l'exception documentée `position: fixed` (BottomNav, PlayerBar, modales, AddModal bottom-sheet), soit le `@media (hover:none)` sanctionné de `table.css`.
- **TrackTable.vue (AV5) est un très bon composant partagé** : présentational pur, divergences Explorer/Radar injectées par props/slots, paliers container-query variant-scopés, la règle `disliked` re-déclarée côté RadarView conformément au piège scoped+slots documenté ; `list-table.css` tient sa promesse « aucune grille figée ».
- **Prefetch D9.c propre** : `utils/prefetch.js` dédup + catch silencieux + libération de clé sur échec, map dérivée des routes lazy (pas de duplication d'imports), garde stale-chunk `router.onError` + `vite:preloadError` avec anti-boucle sessionStorage.
- **C9.b conforme** : le shelf « Sonne comme » est doublement gaté admin — rendu (`TrackDetailView.vue:184`) ET fetch (`loadContentNeighbors` l.540 : un non-admin ne déclenche aucun appel).
- **AlbumView respecte la consigne C7** : vue détail hors allowlist KeepAlive, container queries only, tokens partout, queue player `type:'list'` filtrée sur `has_preview`.
- **Store audioPlayer robuste** : garde anti-hijack `isCurrent(targetId)` sur chaque await, retry 503 borné, `deadPreviewStreak`/`NEXT_LOAD_MORE_MAX` bornent les queues mortes, `autoAdvance()` ne peut pas fuir de rejection, contrat source list/genre/artist + dislike=skip fidèle au brief.
- Pas de composant ni composable mort : chaque fichier de `components/`, `composables/`, `utils/` est référencé au moins une fois hors tests (balayage systématique).

---

### [A4-01] Injection HTML via `v-html` dans le highlight de recherche du Hub
- **Type** : sécu
- **Sévérité** : haute
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/frontend/src/components/hub/HubSearchResults.vue:59-60` — `<div class="rtitle" v-html="highlight(itemTitle(item))">` / `<div ... v-html="highlight(itemSub(item))">` ; `highlight()` (l.197-201) fait `text.replace(new RegExp(q,'gi'), '<mark>$1</mark>')` **sans échapper `text`** avant l'injection.
- **Constat** : les titres/artistes viennent du catalog partagé, alimenté par l'import Rekordbox XML de n'importe quel utilisateur et par les scrapes TrackID/Deezer. Un titre contenant du HTML (`<img src=x onerror=…>`, `<a href=…>`, balises de mise en page) est injecté BRUT dans le DOM de tous les utilisateurs qui le trouvent en recherche — stored XSS inter-utilisateurs. La CSP `script-src 'self'` bloque l'exécution de handlers inline (mitigation réelle), mais l'injection de markup reste possible (liens de phishing, images beacon, casse de layout). Code hérité du Hub d'origine (5bd257d) déplacé dans `hub/` à l'AV5 — jamais audité. Seul site `v-html` sur donnée serveur du repo (les `v-html` de `scopeIcons` sont des chaînes statiques internes, sûrs).
- **Recommandation** : échapper le texte avant la pose du `<mark>` — soit `escapeHtml(text)` puis replace sur le texte échappé, soit remplacer le `v-html` par un rendu en segments (`computed` retournant `[{text, hit}]` + `<mark v-if>` dans le template).
- **Dépendances** : aucune.
- **Tags** : QW-c

### [A4-02] Bouton « Ajouter à la bib » des résultats de recherche : aucun handler
- **Type** : bug
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/frontend/src/components/hub/HubSearchResults.vue:73-83` —
  ```html
  <button v-else class="r-add" title="Ajouter à la bib" aria-label="Ajouter à la bibliothèque">
  ```
  Aucun `@click` (comparer au `.play` de la même row, l.53, qui a `@click.stop`).
- **Constat** : le bouton « + » affiché sur chaque track hors bibliothèque est une affordance morte : le clic bulle vers `onRowClick` et ouvre la fiche track au lieu d'ajouter quoi que ce soit. Trompeur pour l'utilisateur (l'aria-label promet une action qui n'existe pas), et invisible aux tests unitaires. Présent depuis le Hub d'origine, reconduit tel quel au split AV5.
- **Recommandation** : trancher — soit câbler une vraie action (il n'existe pas d'endpoint « ajouter 1 track à la lib » aujourd'hui : probablement retirer), soit supprimer le bouton et garder seulement le badge « EN BIB ». Ne pas laisser un contrôle inerte avec aria-label.
- **Dépendances** : aucune.
- **Tags** : QW-c

### [A4-03] CollectionCard : « N tracks » faux depuis les items polymorphes C5 v2
- **Type** : bug
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/frontend/src/components/CollectionCard.vue:5-7` — `{{ coll.item_count }} track{{ coll.item_count !== 1 ? 's' : '' }}` alors que `item_count` compte désormais des items track/set/artist/genre/playlist. `CollectionDetailView.vue:10` dit correctement « élément(s) » pour le même compteur.
- **Constat** : reliquat de la sémantique tracks-only pré-C5 v2 : une collection de 3 artistes + 2 genres affiche « 5 tracks » sur sa carte, et « 5 éléments » une fois ouverte. Incohérence de copy visible.
- **Recommandation** : aligner sur `CollectionDetailView` — `pl(coll.item_count, 'élément', 'éléments')` (helper `pl` déjà dans `utils/format`).
- **Dépendances** : aucune.
- **Tags** : QW-c

### [A4-04] CollectionCard : suppression invisible au tactile (hover-only sans fallback)
- **Type** : bug
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : moyenne (comportement tactile — à vérifier au RENDU)
- **Preuve** : `server/frontend/src/components/CollectionCard.vue:135-141` — `.coll-del { opacity: 0; } .coll-card:hover .coll-del { opacity: 1; }`, et aucun bloc `@container`/`@media (hover:none)` ne le rétablit (le seul `@container` de la vue, `CollectionsView.vue:611`, ne touche que la grille). Contre-exemples conformes dans le même chantier : `CollectionDetailView.vue:514-519` (`.rart .play` et `.rm-btn` repassent `opacity: 1` à 640px) et `HubSearchResults.vue:677-682`.
- **Constat** : sur mobile/tactile, `:hover` ne s'applique pas : la corbeille de la carte reste invisible (mais cliquable — un tap « à l'aveugle » en haut à droite déclenche le confirm de suppression au lieu d'ouvrir la collection). L'utilisateur mobile n'a aucun moyen visible de supprimer une collection depuis la grille ; la convention repo (intention tactile via `@media (hover:none)` / palier container) n'est pas appliquée ici alors que les deux vues sœurs du même lot le font.
- **Recommandation** : ajouter le même fallback que CollectionDetailView (opacity 1 sous le palier 640px du container, ou `@media (hover:none)` comme table.css).
- **Dépendances** : aucune.
- **Tags** : QW-c

### [A4-05] AddToCollectionButton : dropdown sans fermeture extérieure ni gestion d'erreur de chargement
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/frontend/src/components/AddToCollectionButton.vue:82-93` — `toggleDropdown` fait `try { await api.get('/api/collections/') } finally {…}` **sans catch** ; aucun listener document/Escape n'est posé (comparer à la directive `vClickOutside` de `HubView.vue:250-260` et au keydown Escape d'`AddModal.vue:47-51`).
- **Constat** : (1) le dropdown ne se ferme qu'en re-cliquant le bouton — cliquer ailleurs sur la page le laisse ouvert, sur les 5 vues détail qui l'embarquent ; (2) un échec du GET remonte en unhandled rejection depuis le handler de clic et l'état affiché devient « Aucune collection » (faux) ; (3) pour un invité le GET répond 401 → l'intercepteur d'`utils/api.js:22-27` déclenche logout+redirect /login, comportement brutal pour un simple survol de bouton (le non-gating auth est une décision actée, mais l'effet de bord 401 ne l'est pas).
- **Recommandation** : ajouter un click-outside (réutiliser la directive du Hub ou un util partagé) + Escape ; catcher l'erreur du GET avec un état « Erreur de chargement » distinct de « Aucune collection » ; optionnellement court-circuiter en invité (toast « Connecte-toi » comme `HubSearchResults.onRowClick`).
- **Dépendances** : aucune.

### [A4-06] audioPlayer : un volume sauvegardé à 0 revient à 0.8 au reload
- **Type** : bug
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/frontend/src/stores/audioPlayer.js:30` — `const volume = ref(parseFloat(localStorage.getItem(VOLUME_KEY)) || 0.8)` ; le slider de `PlayerBar.vue` (l.121, `:value="player.muted ? 0 : player.volume"`) permet 0.
- **Constat** : `0 || 0.8` → un utilisateur qui a mis le volume à zéro retrouve 0.8 à la session suivante. Classique piège du falsy.
- **Recommandation** : `const saved = parseFloat(localStorage.getItem(VOLUME_KEY)); const volume = ref(Number.isFinite(saved) ? saved : 0.8)`.
- **Dépendances** : aucune.
- **Tags** : QW-c

### [A4-07] HubView : réponses de recherche non gardées contre l'arrivée dans le désordre
- **Type** : bug
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/frontend/src/views/HubView.vue:212-229` — `doSearch()` lit `query.value` au départ mais écrit `items/total/totals` sans vérifier au retour que `q` est toujours la requête courante ; le debounce 150 ms (l.209) ne protège pas d'un réseau qui ré-ordonne deux requêtes en vol. Le player (`audioPlayer.js:131`) montre le pattern correct (`if (!isCurrent(targetId)) return`).
- **Constat** : en tapant vite, une réponse lente pour « tech » peut écraser les résultats déjà affichés de « techno » (résultats et compteur incohérents avec la requête affichée). Au passage, le `catch` (l.223-225) ne remet pas `totals.value = {}`.
- **Recommandation** : capturer `const q` au départ et jeter la réponse si `q !== query.value.trim()` au retour (ou un compteur de génération) ; réinitialiser `totals` dans le catch.
- **Dépendances** : aucune.

### [A4-08] ExplorerView : listener `document click` du menu imports non détaché sous KeepAlive
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/frontend/src/views/ExplorerView.vue:750` (`document.addEventListener('click', onDocClick)` en `onMounted`) et l.763-765 (retrait en `onUnmounted` seulement) ; la convention D9 (CLAUDE.md, Known Pitfalls Frontend, point b) exige le détachement `onDeactivated` des listeners globaux d'une vue cachée.
- **Constat** : ExplorerView étant dans l'allowlist KeepAlive, `onUnmounted` ne fire pas au départ vers un détail : le listener document reste actif en arrière-plan. Impact pratique quasi nul (`onDocClick` court-circuite si `menuOpen` est false, et un menu resté ouvert se fermerait juste silencieusement), mais c'est la seule entorse à la règle D9 dans les 6 vues cachées — à corriger pour ne pas normaliser l'écart.
- **Recommandation** : déplacer l'attache/détache vers `onActivated`/`onDeactivated` (en gardant onMounted/onUnmounted), ou fermer `menuOpen` en `onDeactivated` et documenter l'exception.
- **Dépendances** : aucune.

### [A4-09] CollectionsView : vue liste hors allowlist KeepAlive (décision non documentée)
- **Type** : archi
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/frontend/src/App.vue:41-48` — `CACHED_VIEWS` fige 6 noms et `:max="6"` ; `CollectionsView.vue` (C5 v2, commit 664ff41, postérieur à D9 df310ff) est une vue liste (grille + arborescence dossiers) routée `/collections`, absente de l'allowlist et sans `defineOptions({ name })`.
- **Constat** : le principe D9 « les vues listes sont cachées, les détails jamais » n'a pas été re-arbitré à l'arrivée de la 7ᵉ vue liste : retour de `/collections/:id` vers `/collections` = remount + double fetch + scroll perdu. C'est peut-être le bon choix (vue légère, 2 requêtes, pas de restauration de scroll implémentée — la cacher exigerait d'ajouter les gardes D9), mais aujourd'hui rien ne le dit. À l'inverse, AlbumView (C7) respecte bien la règle « détail = jamais caché » — vérifié.
- **Recommandation** : documenter le choix (commentaire dans `CACHED_VIEWS`) ou intégrer CollectionsView à l'allowlist (nom + `:max` porté à 7 + refetch `onActivated` pour capter les ajouts faits depuis les vues détail).
- **Dépendances** : aucune.

### [A4-10] Littéraux `oklch()` hors système de tokens (dont un risque de divergence dark)
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : moyenne (l'aspect dark est visuel — à vérifier au RENDU)
- **Preuve** : `server/frontend/src/components/hub/HubSearchResults.vue:409` (`oklch(0.5 0.01 70 / 0.06)`, hachure placeholder) et surtout `:471` — `.rart.genre { background: oklch(0.94 0.055 var(--th)); }` : lightness/chroma en dur calibrées thème clair, sans variante dark, alors que le pattern conventionnel utilise des composantes tokens (`--tag-bg-l`/`--tag-dot-l`… qui basculent avec `[data-theme]`, cf. `GenreCard.vue:322`, `StyleTag.vue:54`). Résidus mineurs pré-existants du même genre : ombres `oklch(0 0 0 / α)` en dur dans `ToastNotification.vue:38`, `AdminGenres.vue:446`, `FamilyChips.vue:115`, `ArtistCard.vue:339`.
- **Constat** : la convention « zéro couleur hors tokens » est globalement tenue, mais la pastille genre des résultats de recherche pose un fond L=0.94 (pastel clair) qui, en thème sombre, tranchera avec les équivalents token-driven (`--accent-soft` dark ≈ L 0.338). `CollectionDetailView` a d'ailleurs choisi `var(--surface-3)` pour la même pastille.
- **Recommandation** : remplacer la ligne 471 par les composantes tokens (`oklch(var(--tag-bg-l) … var(--th))`) et vérifier le rendu dark ; migrer les ombres en dur vers `--shadow-*` à l'occasion (pré-existant, non bloquant).
- **Dépendances** : vérif visuelle CDP avant/après (pipeline `verif-visuelle-headless`).

### [A4-11] Duplication CollectionDetailView ↔ HubSearchResults (rows typées)
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** : `CollectionDetailView.vue:122-167` vs `HubSearchResults.vue:166-268` — `itemKey`/`itemTitle`/`typeLabel`/`typeIcon`/`initials`/`artworkUrl`/`artClass` quasi identiques (mêmes regex, mêmes maps de routes/labels, mêmes chemins `/storage/*-artworks/`), plus ~150 lignes de CSS row (`.rrow/.tbadge/.rart/.rtx/.rmeta` + paliers 640px) dupliquées à l'identique près.
- **Constat** : le « calqué HubSearchResults » de C5 v2 est une décision actée côté design, mais l'implémentation a copié-collé helpers ET CSS au lieu de partager. Troisième copie partielle des maps de labels : `ALBUM_TYPE_LABELS` existe aussi dans `AlbumView.vue:102-107`. Toute évolution (nouveau type d'item, nouveau bucket artwork) devra être portée à 2-3 endroits — exactement la dérive que `scopeIcons.js` avait été créé pour éviter.
- **Recommandation** : extraire un module `entityRow.js` (helpers artworkUrl/typeLabel/initials/routes par type) + éventuellement une feuille `entity-row.css` façon `list-table.css` (approche additive éprouvée AV5). Ne pas fusionner les composants eux-mêmes (états et interactions divergent réellement : lock invité, avis, remove).
- **Dépendances** : à faire avant d'ajouter un 6ᵉ type d'item ou une nouvelle surface de rows typées.

### [A4-12] AlbumView ne réagit pas à un changement de `route.params.id`
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `server/frontend/src/views/AlbumView.vue:180` — `onMounted(fetchDetail)` seul ; comparer `TrackDetailView.vue:575-581` qui double le `onMounted` d'un `watch(() => route.params.id, …)` précisément parce que Vue Router réutilise l'instance quand seul le param change.
- **Constat** : aujourd'hui aucun lien in-app ne navigue d'un album vers un autre album (la recherche vit sur le Hub, la tracklist renvoie vers `/catalog/:id`), donc pas de bug observable. Mais le jour où une navigation album→album apparaît (fiche artiste « discographie », lien album sur Track Detail — déjà évoqué comme différé C7), la vue affichera l'ancien album sans refetch. Piège silencieux.
- **Recommandation** : ajouter le même `watch(() => route.params.id, (id) => id && fetchDetail())` que TrackDetailView (3 lignes, immunise la vue).
- **Dépendances** : aucune.
