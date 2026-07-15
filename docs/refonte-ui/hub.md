# Hub / accueil — `/`

Statut : ✅ figé (décisions actées ; assets Design + fiches des 2 pages filles restent à produire)  |  Vue : `views/HubView.vue`

## 1. Ce qu'on a (actuel)

**Rôle** : porte d'entrée + moteur de recherche global. Deux états pilotés par `isEmpty` (= champ de recherche vide) :
- **État vide** (accueil) : hero + search bar + extras + étagères de découverte.
- **État recherche** : liste de résultats unifiée (track/artist/set/playlist/genre) avec tri (connecté) et lock-row (invité).

**Top bar** (sticky) : wordmark « Diggy » (glyph `D` dans carré accent) + à droite CTA login (invité) ou pastille user (connecté).

**Search bar** : dropdown scope (Tout / Tracks / Artistes / Sets / Playlists / Genres) + champ. Debounce 150 ms → `GET /api/search`.
- Icônes scope : **incohérentes** — le bouton (label court mobile) utilise des emoji (`⊕ ♫ ● ◎ ☰ ◆`), le menu et les badges de résultats utilisent un set SVG (`scopeIcons`).

**Extras** (état vide seulement), dans cet ordre :
1. **Genres populaires** : pills issues de `GET /api/genres?limit=10&sort=tracks`, teintées par pilier. Largeur variable (auto-size selon le nom + count) → rendu inégal.
2. **Essaie** : suggestions statiques (`house`, `disclosure`…), préfixe `↳` en CSS `::before`.

**Étagères de découverte** (état vide) :
| Étagère | Source | Condition | Payload dispo |
|---------|--------|-----------|---------------|
| Ça sort en ce moment | `GET /api/radar/trends?limit=20` (+ `FamilyChips`) | tous (invités inclus) | title, artist, has_artwork, has_preview, **bpm, key**, rank, family — **pas de release_date** |
| Pour toi | `GET /api/recommendations?limit=12` | connecté | CatalogEntryOut complet : **bpm, key, release_date, duration_ms**, has_artwork, has_preview |
| Nouveautés de tes artistes | `GET /api/following/activity?limit=12` (+ new-count + seen) | connecté | type, title, artist, **bpm, key, release_date**, has_artwork, has_preview, catalog_id / set_id / external_url |

- Cards de trend/reco : affichent **seulement** artwork + rank + titre + artiste. BPM/KEY/âge **présents en données mais pas affichés**.
- « Nouveautés » affiche déjà `relativeAge(release_date)` (« Sorti il y a … ») ; fonction `relativeAge()` réutilisable telle quelle.
- « Ça sort » : `openTrend()` bloque les invités (toast « connecte-toi »), mais l'étagère leur est visible.

**Résultats de recherche** : liste `rrow` typée, highlight du terme, tri Pertinence/BPM/A–Z (connecté) ou lock-row (invité) + lock-row « connecte-toi pour voir les N autres ».

**Responsive** : container queries (680 / 640 / 540 px). Shelf en 1 colonne < 640.

**Dette / limites** :
- Set d'icônes scope dédoublé emoji/SVG.
- Wordmark = glyph texte, pas de vrai logo.
- Étagères non paginées / non « voir plus » → tout est plafonné à 12-20 en dur.
- Pas de page dédiée pour « Pour toi » ni « Nouveautés artistes ».

## 2. Ce que je voudrais (William)

**Search bar** : dropdown recherche détaillé — meilleures icônes adaptées à la roadmap.
**Logo** : bosser un vrai logo Diggy.
**Genres populaires** : normaliser la taille des items ; réduire le nombre affiché ou revoir la forme.
**Essaie** : déplacer juste sous la search bar (éléments très liés) ; revoir l'icône flèche.
**Ça sort en ce moment** : réduire au top ~9 ; bouton « voir plus » → Radar ; invité → « se connecter avec Google ».
**Pour toi** : TRANCHER laisser ici vs vue dédiée ; si gardé, même principe « voir plus ».
**Nouveautés de tes artistes** : même principe « voir plus » → **page dédiée à créer**.
**Cards (transverse)** : ajouter KEY / BPM ; ajouter « Sorti il y a … ».

## 3. Faisabilité (analyse Claude)

| # | Item | Effort | Nature | Back ? |
|---|------|--------|--------|--------|
| a | Icônes scope cohérentes | S | Design (set d'icônes) + code (unifier emoji→SVG) | non |
| b | Vrai logo Diggy | M | Design (asset SVG, CSP inline) + intégration | non |
| c | Genres populaires : normaliser taille | S | CSS (min-width / grid) | non |
| d | Genres populaires : réduire nombre / forme | S | Front (limit → ~8) + Design si nouvelle forme | non |
| e | Essaie sous la search bar | XS | Réordonner les blocs | non |
| f | Essaie : nouvelle icône flèche | XS | Front (remplacer `::before ↳`) | non |
| g | Ça sort : top 9 | XS | Front (slice/limit) | non |
| h | Ça sort : « voir plus » → `/catalog?view=radar` (invité → `/login`) | XS | Front | non |
| i | Pour toi : garder vs vue dédiée | — | **décision** (voir §4) | selon choix |
| j | Nouveautés artistes : « voir plus » + page dédiée | M | **Nouvelle vue** + route (fiche propre dans le registre) | pagination à confirmer |
| k | Cards : KEY / BPM partout | S | Front pur (data déjà présente) | non |
| l | Cards : « Sorti il y a … » | S | Front pour Pour toi + Nouveautés (data OK) ; **+ back léger** pour Ça sort (ajouter `release_date` à `TrendItem` + query) | oui (trends only) |

Notes :
- `relativeAge()` existe déjà → réutilisable pour (l) partout.
- L'endpoint `/api/following/activity` accepte `limit` : une page dédiée « Nouveautés » branchera dessus (pagination `offset`/`usePaginatedList` à ajouter si liste longue).
- Invariants à tenir : zéro couleur hardcodée (tokens), container queries, `useTaskPoll`/`usePaginatedList` pour toute nouvelle liste, UI FR.

## 4. Décisions figées

**Search bar** : dropdown de recherche détaillé (icône par scope).
- Le **set d'icônes unifié** (scope + badges de résultat) est un sujet **transverse** → [TRANSVERSE.md](TRANSVERSE.md) § Système d'icônes.

**Logo** : **transverse** (DA globale long terme) → [TRANSVERSE.md](TRANSVERSE.md) § Brand. Hors périmètre Hub ; le glyph « D » actuel reste d'ici là.

**Genres populaires** : **bloc RETIRÉ du Hub** (allègement, principe « état vide maîtrisé »). L'entrée par genre reste couverte par « Essaie » (suggestions déjà à dominante genre), le scope `genre` de la recherche et la page Genres dédiée → **zéro perte de découvrabilité**. Option future d'entrée « par vibe » riche = sur la page Genres, pas le Hub.

**Essaie** : déplacé **juste sous la search bar** ; icône flèche revue (fin du `::before ↳`). Devient le seul bloc d'amorces (rééquilibrer éventuellement le mix genre/artiste/set des suggestions).

**Ça sort en ce moment** : aperçu réduit au **top 9** + bouton **« voir plus »** → **future page Radar** (cible provisoire `/catalog?view=radar`, dépend de la restructuration nav → [TRANSVERSE.md](TRANSVERSE.md) § Navigation) ; invité → `/login`.

**Parcours invité** (acté, funnel voulu) : le contenu (trends, aperçus) est montré **librement** ; le « voir plus » et les actions profondes **amènent à se connecter**. → [TRANSVERSE.md](TRANSVERSE.md) § Principes UX.

**Pour toi** : **reste en aperçu sur le Hub** (top 9) + **« voir plus »** → **Radar** (colonne « Pour toi » ; la page `/for-you` est **fusionnée dans Radar**) → [radar.md](radar.md).

**Nouveautés de tes artistes** : aperçu Hub + **« voir plus »** → **nouvelle vue dédiée** ([new-releases.md](new-releases.md), route proposée `/new-releases`), branchée sur `/api/following/activity` (pagination via `usePaginatedList`).

**Cards (transverse)** : afficher **KEY / BPM** + **« Sorti il y a… »** (`relativeAge`) sur les 3 étagères. → **ajout `release_date` à `TrendItem` + query** (`routers/radar.py`) pour couvrir « Ça sort ».

> Routes `/for-you` et `/new-releases` = propositions (cohérence avec les slugs anglais existants) — ajustables.

## 5. Sortie next-step

**Handoff Design (Hub)**
- [ ] Icône « Essaie ».
- [ ] Card de découverte enrichie (BPM · KEY · âge) → **produit le `<TrackCard>` partagé** (transverse).
- [ ] Layout de la nouvelle page new-releases (Pour toi → fusionné dans Radar).
- _Icônes + logo = transverse, pas ici._

**Chantier work_manager (Hub)**
- **Front** : réordonner Essaie + nouvelle flèche ; **retirer le bloc Genres populaires** ; top 9 sur Ça sort + Pour toi ; boutons « voir plus » ; méta `BPM · KEY · âge` (ligne mono compacte) sur les cards.
- **(recap C1)** : **compteurs par type** sur le sélecteur de scope (Tout/Tracks/Artistes/… — `totals.*` déjà calculés puis jetés).
- **(recap C5)** : sur les cards trends/reco → badge **« sur N sources »** (`source_count`, viralité) + **chip genre** + **durée** (tout déjà renvoyé).
- **Back** : `release_date` → `TrendItem` + query `list_trends` (`catalog_visible` déjà en place).
- **Nouvelles vues** : `for-you` + `new-releases` (routes + entrées nav à décider avec la restructuration), pagination `usePaginatedList`.

**Dépend de** : composants partagés + icônes/logo (transverse) pour la passe visuelle finale ; cible « voir plus » de Ça sort attend la **nav Radar** (transverse). Le reste (structure, retrait Genres, méta, back `release_date`) est livrable sans attendre.

## 6. Avis & recommandations (Claude)

### Verdict point par point
- **Icônes scope unifiées** — ✅ l'incohérence emoji/SVG est réelle, à corriger. ⚠️ ce set sert AUSSI de badge de type de résultat à ~13px : il doit rester lisible tout petit. 💡 « Tout » peut se passer d'icône (texte seul).
- **Vrai logo** — ✅ sur le principe, mais ⚠️ ce n'est PAS un item Hub : un logo touche top bar, favicon, login, écrans de chargement, icône PWA. 💡 le traiter comme **tâche brand globale, décidée une fois**, exposée en composant `<BrandLogo>` réutilisé partout. Rester sobre : le glyph « D » actuel est déjà correct, gros risque de sur-design.
- **Genres populaires (normaliser + ~8)** — ✅ pour la normalisation. ⚠️ ne pas perdre l'info utile au passage (count + couleur pilier). 💡 question de fond : cette liste double la page Genres ; sur le Hub elle devrait être un **point d'entrée “goût”** (peu d'items, visuels) plutôt qu'un mini-annuaire.
- **Essaie sous la search bar** — ✅ fort accord, ce sont des amorces de recherche, leur place est avec l'input. 💡 aujourd'hui statique/hardcodé : candidat à du dynamique plus tard (recherches récentes / requêtes tendance) — hors scope pour l'instant.
- **Ça sort → top 9 + voir plus → Radar** — ✅ top 9 (grille 3×3 nette). ⚠️ **vigilance** : `/catalog?view=radar` est un tableau dense de détections radar, pas la même présentation ni forcément le même tri que l'étagère “tendances rank #1..N” → risque que « voir plus » atterrisse sur autre chose que « la suite ». 💡 à trancher quand on fera Catalog : soit `view=radar` sait trier par rang de tendance, soit « voir plus » vise une vraie vue tendances.
- **Pour toi → /for-you** & **Nouveautés → /new-releases** — ✅ cohérent avec ton choix « une vue par étagère ». 💡 le coût de 3 destinations quasi-identiques se neutralise avec la reco A ci-dessous.
- **Nouveautés : feed hétérogène** — ⚠️ le feed mélange 3 types (track crawlé, lien externe fallback, set) : la page dédiée doit gérer les 3 proprement (+ filtre releases/sets envisageable).
- **KEY/BPM + âge sur les cards** — ✅ data présente partout. ⚠️ la card est compacte : empiler 3 métas de plus la charge (surtout mobile 1-col). 💡 les mettre en **ligne mono compacte** (`BPM · KEY · âge`) façon `.rmeta`, pas en lignes empilées ; dégrader pour genre/artiste (pas de BPM/KEY).
- **release_date sur trends (back)** — ✅ petit, faible risque : join live sur `CatalogEntry`, aucun recompute du nightly `compute_trends`.

### Recommandations transverses → toutes portées dans [TRANSVERSE.md](TRANSVERSE.md)
- **A. Composants de découverte mutualisés** — ✅ validé. `<TrackCard>` + `<DiscoveryShelf>`/`<DiscoveryList>` partagés Hub + destinations.
- **B. Brand-first (logo + icônes globaux)** — ✅ validé, sujets globaux (dont le logo, long terme DA).
- **C. Densité de l'état vide** — ✅ validé. 1re application : **retrait du bloc Genres populaires** du Hub.
- **D. Parcours invité** — ✅ acté : **funnel voulu** — montrer librement, gater le « voir plus » derrière le login.
