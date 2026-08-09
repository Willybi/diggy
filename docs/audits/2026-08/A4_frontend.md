# A4 — Audit Frontend (`server/frontend/src/`)

> Audit READ-ONLY — 2026-08, HEAD `9b305d6`. Audit précédent : `docs/audit_2026-07/A4_frontend.md` (12 findings, fixes livrés via AU6).
> Delta audité : 164 commits — refonte UI intégrale (D4 details + Admin, D6 listes + Genre Detail), X2 scroll+filtres URL, file de lecture audioPlayer, Prettier repo-wide.
> Périmètre : 18 vues, 57 composants (33 racine + 12 filters + 3 charts + 9 admin), 10 composables, 4 stores Pinia, styles.
> Méthode : greps mécaniques exhaustifs (références croisées composant par composant, couleurs, `setInterval`/timers, `@media`, handlers inline, stubs de tests), lecture intégrale des composables récents (`usePaginatedList`, `useWindowedList`, `useScrollRestore`, `useUrlSync`, `useFilterState`, `useInfiniteScroll`) et du store `audioPlayer`, mesure outillée de la duplication inter-vues (diff + comm après normalisation des préfixes de classes), build de production (`npm run build`) pour l'évidence bundle.

## Ce qui va bien

- **11 des 12 findings 2026-07 sont réellement corrigés et vérifiés** : A4-01 (BottomNav.vue:56-61 : `/api/radar/new-count` avec préfixe `/api` ET gate `auth.isAuthenticated`), A4-02 (TrackDetailView.vue:453-457 : avis persisté via le canonique `PATCH /api/catalog/{id}/avis`), A4-03/04 (AppearRow.vue et TagsView.vue supprimés — absents de l'arborescence), A4-05 (`usePaginatedList` créé et adopté), A4-06/07 (`useTaskPoll` créé, plus aucun `setInterval` hors de lui), A4-08 (`useInfiniteScroll` ne retourne plus de `loading` mort), A4-10 (plus aucun appel `/api/genres/` avec slash), A4-11 (AdminGenres.vue:197-214 : `fetchMappingStats` a un try/catch et un hint `known` qui évite les appels redondants), A4-12 (`.state` + `@keyframes spin` globaux dans `assets/page.css:13-24`). Seul A4-09 récidive (cf. [A4-06] ci-dessous).
- **Les patterns paginés sanctionnés sont réellement adoptés, pas juste documentés** : `usePaginatedList` porte ArtistsView, GenresView, SetsView, WatchlistView et la tracklist bornée de GenreDetailView ; `useWindowedList` + `useVirtualWindow` portent Explorer et Radar ; le poll de crawl de WatchlistView (WatchlistView.vue:484-505) est un `useTaskPoll` keyé exemplaire. Le SEUL `setInterval` de tout src/ est celui de `useTaskPoll.js:65`.
- **Zéro couleur hardcodée tenu** : le grep hex/rgb/hsl ne remonte que les 4 hex du logo Google (LoginView.vue:16-28, marque, résiduel accepté 2026-07) et des faux positifs d'entités HTML (`&#8239;`).
- **Zéro handler inline multi-statements** (grep `@click="…;…"` → 0), **un seul point d'entrée axios** (`utils/api.js`), **un seul `new Audio()`** (le singleton du store).
- **Discipline `@media` tenue** : hors `prefers-reduced-motion`, les `@media` restants couvrent des éléments `position: fixed` (BottomNav, PlayerBar, modales overlay) et WatchlistView.vue:1330 documente explicitement son exception. Une seule déviation mineure (cf. [A4-10]).
- **DesignSystemView correctement gardée** : routée uniquement sous `import.meta.env.DEV` (router.js:54-63), et le build de prod n'émet AUCUN chunk DesignSystemView (tree-shaking confirmé par la sortie de `vite build`) — la vitrine de 1253 LOC ne coûte rien en prod.
- **Récupération des chunks périmés post-déploiement** (router.js:76-104) : détection `ChunkLoadError` + `vite:preloadError`, un seul rechargement avec garde anti-boucle sessionStorage — un piège de déploiement statique réellement traité.
- **Store audioPlayer (file de lecture 9e1abdd) bien conçu** : capture de cible anti-course (`targetId` + `isCurrent` à chaque await, audioPlayer.js:101-129), chasse au « next jouable » bornée (`NEXT_LOAD_MORE_MAX = 5`, :210-220), avis optimiste avec rollback + sync bidirectionnelle listing↔barre (:232-251), retry 503 unique avec backoff. Pas de listeners `window` fuités.
- **`useWindowedList` et `useScrollRestore` sont d'une qualité rare** : token monotone anti-course (useWindowedList.js:51-59), distinction erreur-réseau vs résultat-vide (:64-73), snapshot scroll dans `history.state` attaché à l'entrée d'historique (useScrollRestore.js:39-49) — et chaque subtilité est commentée avec sa raison.
- **Tests** : 59 fichiers, les 7 composables récents sont TOUS testés (useFilterState, usePaginatedList, useScrollRestore, useTaskPoll, useUrlSync, useVirtualWindow, useWindowedList) ; `RouterLinkStub` est systématiquement enregistré via `global.components` (le pitfall CLAUDE.md est respecté partout, ex. ArtistCard.test.js:37).
- **Code-splitting sain hors Hub** : 17 vues lazy en chunks séparés, AdminView (65 kB) et ses 9 composants isolés du bundle visiteur.

---

## Findings

### [A4-01] ExplorerView ↔ RadarView : vues jumelles dupliquées à ~80 %
- **Type** : dette
- **Sévérité** : haute
- **Effort estimé** : L
- **Confiance** : haute
- **Preuve** : après normalisation des préfixes de classes (`xp-` / `rd-` → `PFX-`) :
  - `diff` ne compte que **555 lignes changées sur 2935** au total (ExplorerView 1440 LOC, RadarView 1495 LOC) ;
  - `comm -12` sur les lignes triées : **1238 lignes strictement identiques** ;
  - mêmes constantes (`PAGE_SIZE = 100`, ExplorerView.vue:467 / RadarView.vue:450), même bloc `buildSearchParams` (:670-681 / :661-667), même orchestration windowing (`useWindowedList` + `useVirtualWindow`, :800 / :795), même bloc scroll-restore (:834-945 / :829-904), CSS quasi octet-identique au préfixe près.
- **Constat** : RadarView a été créée en copiant ExplorerView (le commentaire RadarView.vue:11 « reused from Explorer » ne vaut que pour la famille `filters/` et les composables, qui sont bien partagés — le reste, template de table responsive + orchestration + ~500 lignes de CSS, est un copier-coller). Toute évolution de la table Explorer (colonne, palier responsive, a11y, comportement de la file de lecture) doit désormais être répliquée à la main dans Radar, et la première divergence non intentionnelle sera invisible (c'est le mode de pourrissement classique : les deux fichiers dérivent silencieusement).
- **Recommandation** : extraire la table virtualisée partagée (thead trié + rows + paliers container-query + wiring windowing/scroll-restore) en composant(s) `components/` paramétrés par colonnes/slots — Radar n'ajoute que ses 2 ScoreRing et son tri défaut. À défaut (si le composant-table généralisé est jugé trop risqué), extraire au minimum le CSS commun en feuille partagée et le tronc script en composable. Vérification RENDU obligatoire (pipeline CDP) sur les deux pages après extraction.
- **Dépendances** : [A4-04] (même chantier d'extraction, deuxième paire) ; à faire AVANT toute évolution fonctionnelle de l'une des deux tables.
- **Tags** : —

### [A4-02] `fetchUpTo` : salve de 12 requêtes parallèles sur `/api/radar/feed` — le durcissement code de l'incident OOM n'est pas fait
- **Type** : perf
- **Sévérité** : haute
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** :
  - `useWindowedList.js:90-100` : `RESTORE_MAX_PAGES = 12` puis `Promise.all(Array.from({ length: nPages }, (_, i) => api.get(endpoint, …)))` — jusqu'à 12 requêtes simultanées, sans limitation de concurrence ;
  - RadarView.vue:450 + :707-710 : `PAGE_SIZE = 100`, endpoint `/api/radar/feed` — l'endpoint documenté comme pesant **~550 Mo de RSS par requête** côté API (incident 2026-08 : OOM-kill du conteneur api → 502 global ; mémoire projet `api-oom-radar-feed`) ;
  - même mécanique dans `usePaginatedList.js:97-106` (grilles de cartes — endpoints légers, risque moindre) ;
  - le suivi d'incident acte que le cap mémoire a été relevé 1G→3G le 2026-08-01 et que « adoucir les salves parallèles fetchUpTo côté code » reste À FAIRE.
- **Constat** : un retour arrière sur /radar après un scroll profond déclenche jusqu'à 12 GET `/api/radar/feed?limit=100` d'un coup. Le cap 3G + les 2 workers uvicorn absorbent UNE salve aujourd'hui, mais deux restaurations concurrentes (deux onglets, deux utilisateurs) recréent les conditions de l'incident. Le composable est générique : tout futur consommateur d'un endpoint lourd hérite du même comportement.
- **Recommandation** : limiter la concurrence de `fetchUpTo` (lots séquentiels de 2-3 `Promise.all`, ou une seule requête `limit = count` si l'endpoint accepte un limit élevé — à trancher côté API). Appliquer aux deux composables (`useWindowedList`, `usePaginatedList`) pour fermer le pattern.
- **Dépendances** : croise le suivi actif `api-oom-radar-feed` (dimension backend : coût mémoire de `/radar/feed` lui-même, hors périmètre A4).
- **Tags** : QW-c

### [A4-03] GenresView : la facette liked/disliked ne voit que la première page (24 genres)
- **Type** : bug
- **Sévérité** : moyenne
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** :
  - GenresView.vue:186 : liked/disliked sont mappés sur le tri serveur `tracks` (`pageSize: 24`, :185) ;
  - :213-221 : `displayItems` filtre CLIENT les items **chargés** (`items.value.filter((g) => opinions.get('genre', g.name) === …)`) ;
  - :131 : le sentinel d'infinite scroll est explicitement désactivé sur ces facettes (`:class="{ on: hasMore && sortBy !== 'liked' && sortBy !== 'disliked' }"`) ;
  - :255 : `watch(sortBy, () => fetch(true))` — le passage sur la facette recharge la page 1 seulement. Aucun `fetchUpTo` sur ce chemin (le seul est l'hydratation scroll-restore, :261).
- **Constat** : basculer sur « Likés »/« Dislikés » filtre les 24 premiers genres par nombre de tracks, et le scroll ne charge plus rien (sentinel off). Un genre liké classé au-delà du 24e rang n'apparaît JAMAIS dans sa facette — silencieusement (le compteur :225-227 affiche le nombre filtré, donc le mensonge est cohérent avec lui-même). Avec ~75 genres en prod, les deux tiers du catalogue sont invisibles pour ces facettes. À contraster avec ArtistsView:205-245 et SetsView:746-790 qui résolvent le même besoin correctement (one-shot serveur par `ids=`).
- **Recommandation** : au basculement sur une facette avis, charger toutes les pages (`fetchUpTo(total)` — ~4 pages de 24, borné et léger) avant le filtre client ; ou aligner sur le pattern `ids=` des autres vues si `/api/genres` accepte un filtre par noms.
- **Dépendances** : aucune
- **Tags** : QW-c

### [A4-04] SetsView ↔ WatchlistView : deuxième paire de jumelles (~50 % de lignes communes)
- **Type** : dette
- **Sévérité** : moyenne
- **Effort estimé** : L
- **Confiance** : haute
- **Preuve** : après normalisation des préfixes (`st-` / `pl-` → `PFX-`) : `diff` = 1519 lignes changées sur 3013 (SetsView 1669 LOC, WatchlistView 1344 LOC) ; `comm -12` sur lignes triées = **878 lignes identiques**. Les blocs communs : table enrichie (thead trié + rows), mode avis (cf. [A4-05]), orchestration `usePaginatedList` + `useScrollRestore` + `useUrlSync`, modal « Ajouter », gros socle CSS de table.
- **Constat** : la refonte Playlists (2026-07-27) a été livrée « jumelle Sets » (acté dans la mémoire projet) — c'est un copier-coller assumé au moment du vol, jamais refactorisé depuis. Moins grave que [A4-01] (les deux vues ont des colonnes et des blocs réellement propres : crawl status/cadence côté Playlists, ScoreRing/complétion côté Sets), mais le même mécanisme de dérive est enclenché sur ~900 lignes.
- **Recommandation** : traiter dans le même chantier d'extraction que [A4-01] — la table triable en composant partagé couvre les 4 vues (Explorer, Radar, Sets, Playlists) ; sinon borner l'extraction aux blocs verbatim (thead trié, socle CSS table, modal add).
- **Dépendances** : [A4-01] (chantier commun), [A4-05] (la branche opinion fait partie des lignes dupliquées)
- **Tags** : —

### [A4-05] Branche « opinion mode » copiée-collée ×3, avec plafonds silencieux à 100/200 items
- **Type** : dette
- **Sévérité** : moyenne
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** : le même bloc « résoudre les ids depuis le store opinions + fetch one-shot + écrire les refs partagées + `hasMore = false` » vit dans :
  - ArtistsView.vue:205-245 (`limit: 100`) ;
  - SetsView.vue:746-790 (`limit: 200`, variante `exclude_ids` pour « À explorer ») ;
  - WatchlistView.vue:407-453 (`limit: 200`, même variante).
  Chaque copie plafonne en dur et force `hasMore.value = false` (SetsView.vue:757+773+782, ArtistsView.vue:227+239) : au-delà de 100 artistes / 200 sets ou playlists likés, la liste est tronquée sans aucun indicateur.
- **Constat** : le contrat de `usePaginatedList` sanctionne explicitement ce mode (« Non-paginated side modes (opinion filters) live in the view and may write the returned refs directly », usePaginatedList.js:16-17) — ce n'est donc PAS une violation de pattern, mais la 3e copie du même bloc de ~40 lignes, avec déjà une divergence (le `exclude_ids` de « À explorer » n'existe que sur 2 des 3) et une limite silencieuse qui deviendra un bug utilisateur réel dès que quelqu'un dépasse 100 artistes likés (plausible à moyen terme pour un utilisateur actif).
- **Recommandation** : extraire un helper `useOpinionOneShot({ endpoint, kind, buildParams })` partagé par les 3 vues ; y traiter le plafond (paginer le one-shot, ou au minimum afficher « N premiers affichés » quand `data.total > items.length`).
- **Dépendances** : [A4-04] (les blocs Sets/Watchlist en font partie)
- **Tags** : —

### [A4-06] HubView (1730 LOC) toujours dans le chunk principal — RÉCURRENCE 2026-07/A4-09
- **Type** : perf
- **Sévérité** : moyenne
- **Effort estimé** : M
- **Confiance** : haute
- **Preuve** :
  - router.js:3 : `import HubView from './views/HubView.vue'` — toujours le seul import statique de vue (toutes les autres :5-20 sont lazy) ;
  - build 2026-08 : `index-C3Vtr0ih.js` = **211,56 kB (gzip 78,24 kB)** contre 191,55 kB (gzip 72 kB) à l'audit 2026-07 ; toujours aucun chunk HubView séparé ;
  - HubView est passée de 1511 à **1730 LOC** entre les deux audits (refonte D6 : DiscoveryCard, shelves « Ça sort »/« Pour toi », sources de file de lecture par shelf).
- **Constat** : le cliquet anticipé en 2026-07 s'est vérifié : +20 kB sur le bundle payé par toutes les routes d'entrée (login, deep links `/catalog/:id`, `/set/:id`) en un cycle de refonte. Le choix « Hub = route par défaut, pas d'aller-retour au premier paint » reste défendable, mais rien n'a été fait pour contenir ce que le Hub embarque, et chaque évolution future du Hub re-paiera ce coût.
- **Recommandation** : inchangée depuis 2026-07, désormais URGENTE au sens du cliquet : scinder HubView en sections composants (recherche, tendances, activité artistes suivis, reco) et lazy-loader les sections sous le fold (`defineAsyncComponent`) ; mesurer avant/après avec `vite build`. Alternative plus simple à trancher : lazy-loader le Hub lui-même et accepter le spinner sur `/` (le skeleton existe déjà).
- **Dépendances** : aucune
- **Tags** : RÉCURRENCE (2026-07/A4-09)

### [A4-07] Composants morts : PageHero et RingPct (0 référence) ; ScorePill et InLibBadge (vitrine dev uniquement)
- **Type** : mort
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** :
  - grep exhaustif (`PageHero|page-hero|RingPct|ring-pct`, insensible à la casse, sur tout src/ y compris tests et imports dynamiques) : **0 référence** hors les deux fichiers eux-mêmes ; aucun enregistrement global de composants dans main.js ;
  - `ScorePill.vue` et `InLibBadge.vue` : unique consommateur = `DesignSystemView.vue`, elle-même routée en dev seulement (router.js:54-63) — aucun chunk ne les contient dans le build prod ;
  - le build confirme : aucun chunk PageHero/RingPct/ScorePill/InLibBadge/DesignSystemView émis.
- **Constat** : PageHero et RingPct sont des orphelins des refontes D4/D6 (les héros et anneaux de complétion ont été réécrits localement dans les vues refaites). ScorePill et InLibBadge ne survivent que comme pièces de musée dans la vitrine design — trompeur pour qui cherche « le composant badge in-lib » (les vues refaites n'utilisent PAS InLibBadge). Aucun coût bundle (tree-shaking), coût de navigation du code uniquement.
- **Recommandation** : supprimer `components/PageHero.vue` et `components/RingPct.vue` ; supprimer `ScorePill.vue`/`InLibBadge.vue` ET leurs sections dans DesignSystemView (ou les y garder consciemment si la vitrine les documente comme « disponibles » — à trancher, mais l'état actuel où la vitrine expose des composants que plus aucune vue n'utilise est le pire des deux). Mettre à jour le compte « 57 components (48 shared + 9 admin) » de CLAUDE.md après suppression.
- **Dépendances** : aucune
- **Tags** : QW-c

### [A4-08] useUrlSync / useFilterState : timer de débounce jamais nettoyé — une écriture d'URL peut fuiter sur la route suivante
- **Type** : bug
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : moyenne
- **Preuve** :
  - `useUrlSync.js:41-57` : `timer = setTimeout(write, debounceMs)` (300 ms) — aucun `clearTimeout` au démontage ; `write()` fait `router.replace({ query })` sur `route.query` **courant** ;
  - `useFilterState.js:121-135` : même pattern (`timer = setTimeout(push, debounceMs)`, 250 ms), même absence de cleanup ; `push()` → `buildQuery()` relit `route.query` courant et y réinjecte les params sérialisés de l'état du composant démonté ;
  - les watchers, eux, meurent bien avec le scope du composant — seul le timer déjà armé survit.
- **Constat** : taper dans un champ débousé (recherche, range BPM) puis naviguer dans les ~250-300 ms qui suivent laisse le timer se déclencher APRÈS l'arrivée sur la nouvelle route : `router.replace` réécrit alors l'URL de la page de destination en y injectant les params de filtre de la page quittée (ex. le `q=` de GenresView collé sur `/explorer`). Fenêtre étroite et geste précis requis — d'où la sévérité basse — mais le mécanisme est certain à la lecture, et le symptôme (URL polluée, filtre fantôme réappliqué au retour) serait très déroutant à diagnostiquer.
- **Recommandation** : dans les deux composables, `onScopeDispose(() => clearTimeout(timer))` (une ligne chacun ; `getCurrentScope()` est garanti, ils sont toujours appelés en setup).
- **Dépendances** : aucune
- **Tags** : QW-c

### [A4-09] audioPlayer : un échec de preview non-503 ferme le player au lieu de passer au morceau suivant de la file
- **Type** : bug
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `stores/audioPlayer.js:124-138` — dans `load()`, tout échec autre qu'un 503 (`if (e.response?.status !== 503) break`) sort de la boucle de retry et atteint `close()` (:138), qui purge AUSSI `source.value` (:190) — la file de lecture entière est perdue. L'auto-avance (`playNext`, :200-222) ne skippe que les rows `has_preview === false` connues D'AVANCE (:206) ; un preview marqué disponible mais mort au fetch (404 `preview-url`, URL CDN Deezer expirée au `el.play()`) tombe dans le chemin `close()`.
- **Constat** : en « écoute active » (le geste central de la feature file de lecture), UN track au preview cassé au milieu d'une liste arrête toute la session d'écoute au lieu de passer au suivant — exactement le cas d'usage que `NEXT_LOAD_MORE_MAX` et le skip `has_preview` cherchent par ailleurs à protéger. L'historique du projet montre que les previews morts-mais-marqués-dispo existent en masse par vagues (incident `has_preview` stale : ~2,3k rows en 2026-07, remédié — mais la classe d'incident est récurrente : expiration CDN, re-crawl partiel).
- **Recommandation** : dans `load()`, sur échec final : si `source.value` est non-nul, tenter `playNext()` (borné — réutiliser un compteur type `NEXT_LOAD_MORE_MAX` pour qu'une liste entièrement morte ne boucle pas) au lieu de `close()` ; ne garder `close()` que pour le lancement single-shot.
- **Dépendances** : aucune
- **Tags** : QW-c

### [A4-10] `@media (max-width: 640px)` dans `assets/table.css` hors de l'exception `position: fixed`
- **Type** : dette
- **Sévérité** : basse
- **Effort estimé** : S
- **Confiance** : haute
- **Preuve** : `assets/table.css:122-131` :
  ```css
  /* ============ MOBILE ============ */
  @media (max-width: 640px) {
    table.dt .pbtn,
    table.dt .act {
      opacity: 1;
    }
    table.dt {
      min-width: 0;
    }
  }
  ```
  Aucun élément `position: fixed` concerné (règles de table). C'est la seule déviation restante à la règle CLAUDE.md « container queries everywhere ; `@media` ONLY for `position: fixed` ».
- **Constat** : les tables `.dt` vivent dans des vues dont les wrappers sont déjà des containers (les paliers responsive d'Explorer sont en `@container`) — le viewport et le container divergent dès que la sidebar est présente : à ~700 px de container dans une fenêtre > 640 px, les boutons play restent en `opacity` hover-only alors que le contexte est visuellement « mobile ». Par ailleurs l'intention réelle est « appareil tactile » (boutons toujours visibles), que ni le viewport ni le container ne capturent fidèlement.
- **Recommandation** : soit `@container (max-width: 640px)` pour rester cohérent avec les paliers des vues, soit — plus fidèle à l'intention — `@media (hover: none)` pour le bloc `opacity` (le `min-width: 0` peut rejoindre les styles de base). Mineur ; à faire au prochain passage sur table.css plutôt qu'en chantier dédié.
- **Dépendances** : [A4-01]/[A4-04] si la table partagée est extraite (le style bougerait avec)
- **Tags** : —

---

## Hypothèses réfutées

1. **« Les fetches offset de GenreDetailView violent les patterns sanctionnés »** — non : GenreDetailView.vue:573-636 (`fetchArtists`/`onArtistsLoadPage`/`fetchSets(append)`/`fetchPlaylists(append)`) sont des shelves bornées à bouton « voir plus » / pagination de page, SANS sentinel ni comptabilité `hasMore` — hors du périmètre de la règle (qui vise le tronc infinite-scroll et les tables virtualisées). La tracklist, elle, passe bien par `usePaginatedList` (endpoint réactif `MaybeRefOrGetter`, conforme à CLAUDE.md).
2. **« Les écritures directes des refs partagées (opinion mode) sont un pattern maison interdit »** — non : ce mode est explicitement contractualisé par le docblock de `usePaginatedList` (usePaginatedList.js:16-17). Le problème n'est pas la conformité mais la triplication ([A4-05]).
3. **« Des stubs string sur composants non résolus traînent dans les tests »** (pitfall CLAUDE.md) — non trouvé : `RouterLinkStub` est partout enregistré via `global.components` ; les stubs string restants (a11y.test.js:94-112, HubView.test.js:128, etc.) visent des composants réellement importés par le SFC testé, donc résolus — cas où le stub string fonctionne.
4. **« La refonte a réintroduit des couleurs hardcodées »** — non : seuls les hex du logo Google (résiduel accepté) et des entités HTML `&#8239;` (faux positifs du pattern `#[0-9a-f]{3,8}`).
5. **« Des polls maison ont survécu à useTaskPoll »** — non : unique `setInterval` de src/ dans useTaskPoll.js:65 ; tous les autres timers sont des débounces `setTimeout` légitimes.
6. **« DesignSystemView (1253 LOC) ship en prod »** — non : route conditionnelle `import.meta.env.DEV` (router.js:54-63), aucun chunk émis au build prod.
7. **« Les vulns npm audit touchent le runtime navigateur »** — non : les 5 vulns (esbuild/vite, nanoid, postcss) sont toutes dans la chaîne dev/build (portées par A5) ; les dépendances runtime (vue, vue-router, pinia, axios) n'en portent aucune.
8. **« Le fetch `new-count` du BottomNav est toujours cassé »** (2026-07/A4-01) — corrigé au-delà du fix demandé : préfixe `/api` ET gate `auth.isAuthenticated` (BottomNav.vue:54-66). Résidu assumé : refetch à chaque changement de route (une requête count légère, non déboussée — acceptable).

## Non couvert (budget)

- **Analyse fonction-par-fonction des grosses vues** (HubView 1730, SetsView 1669, GenreDetailView 1527) : les structures ont été cartographiées (imports, sections, orchestration) mais pas auditées ligne à ligne pour du code mort intra-fichier.
- **Accessibilité** : hors périmètre de cette passe (constats ponctuels positifs seulement : skip-link testé, `aria-pressed` LikeDislike).
- **Vérification RENDU** (pipeline CDP) : non exécutée — les findings de cette passe sont tous mécaniques ; les findings layout-sensibles éventuels (piège grid 1fr, absolus recouvrants) demanderaient une passe visuelle dédiée.
