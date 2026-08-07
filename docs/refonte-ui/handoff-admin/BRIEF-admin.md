# BRIEF — Admin `/admin` · Chantier D4-Admin + D7 (fusionnés)

> Maquette pilote : `Admin (pilote).html` — toggles thème dark/light + viewport desktop/375 px, et un sélecteur de **régime** (`Backlog chargé` · `Tout à jour` · `Chargement` · `Erreur`) qui rejoue les quatre états de l'Aperçu. Les 8 onglets sont cliquables (badges, état actif, scroll horizontal en mobile) ; les boutons d'action rapide basculent la carte en « job en cours ». Deux arbitrages sont comparables en direct via le panneau Tweaks (`badgeZero` : aucun badge à 0 / badge neutre à 0 · `regroupeAJour` : ordre fixe / cartes à jour repoussées en fin de grille).
> **Refonte CIBLÉE.** Un seul écran designé : le **nouvel onglet « Aperçu »**, en landing. Les 7 onglets existants gardent leur contenu **et** leur esthétique ops-console dense (tables, boutons de job, mono pour les nombres) ; **Monitoring** est conservé tel quel, hors périmètre. Le reste du chantier est de la **finition responsive mobile** sur des surfaces existantes — mise en forme uniquement, aucun contenu ne bouge.
> Page toujours `require_admin` (un seul utilisateur) : **aucun état invité**, aucune permission à dessiner.
> Tout en tokens `diggy-tokens.css`, zéro couleur hardcodée. Libellés 100 % français. Icônes **SVG inline `currentColor`**, zéro CDN, zéro emoji. Responsive **container queries** uniquement, palier unique **859 px** (aligné sur `AdminFlags`) + un palier de grille à 639 px. Aucun `position: fixed`.
> **Aucun composant transverse créé** : les cartes de l'Aperçu et les badges d'onglets sont **admin-locaux** (aucun autre consommateur).

## Ordre vertical

1. **Titre** « Admin » (`--fs-lg`, 700)
2. **Barre de 8 onglets** — `Aperçu` · Artistes · Flags · Sets · Genres · Crawl · Monitoring · Beatport, avec **badges de compte**
3. **Panneau Aperçu** — ligne de synthèse (+ bouton `Actualiser`) puis **grille de cartes de chantier**
4. (les 7 autres panneaux : contenu existant, inchangé)

## Décisions DA explicites

| # | Décision | Justification |
|---|---|---|
| **A1** | **Arbitrage central — une carte = UN compteur actionnable = UNE action.** Les pipelines à deux métriques sont **éclatés en deux cartes** (Artistes → « À lier sur Deezer » + « Sans pochette » ; Sets → « À recrawler » + « Set-flags en attente » ; Genres → « Tracks non classées » + « Mappings non mappés » ; Crawl → « Playlists dues » + « File d'échec (DLQ) »). La grille compte donc **11 cartes** pour 7 pipelines. L'appartenance au pipeline est portée par un **eyebrow** (`BEATPORT`, `ARTISTES`…, mono nano uppercase `--ink-3`) et par l'ordre : les cartes d'un même pipeline sont adjacentes | Trois raisons, toutes tranchées par l'état 0. **(i) L'état « à jour ✓ » n'est définissable que sur une métrique unique.** Une carte Genres portant `42 031 non classées` **et** `0 mapping non mappé` n'est ni à jour ni en retard : elle devrait afficher les deux traitements à la fois, ce qui détruit exactement le signal que la décision figée n°5 demande (« l'état sain est un état à 0 »). Éclatée, chaque carte a un état booléen net — et c'est le cas réel de la prod : Genres et Crawl sont **mixtes** aujourd'hui. **(ii) Une métrique = une action.** « Lancer le classement auto » et « Chercher un node de taxonomie » ne sont pas le même geste ; une carte à deux métriques aurait deux boutons primaires, donc aucun. Le slot d'action reste unique parce que la carte l'est. **(iii) Homogénéité de balayage.** 11 cartes identiques (eyebrow / intitulé / chiffre / contexte / action) se lisent en une saccade par carte ; un mélange de cartes simples et doubles obligerait l'œil à re-jauger la hiérarchie à chaque tuile. Coût assumé : 11 tuiles au lieu de 7 — absorbé par une grille dense de 252 px, 4 colonnes en desktop |
| **A2** | **Le chiffre principal est toujours l'actionnable** (`never_tried + due_retry` pour Beatport/Deezer). `total_missing` et `abandoned` descendent en **ligne de contexte** (`--fs-xs`, `--ink-3`, sous le chiffre) : « sur 65 722 manquantes · 14 abandonnées ». Jamais de second chiffre en gros, jamais de ratio, jamais de barre de progression | Le backlog brut est **non actionnable** : la passe de nuit ne prendra que 2 607 des 65 722 tracks manquantes. Afficher 65 722 en gros, c'est afficher un nombre sur lequel aucun bouton de la page n'a de prise — et c'est précisément ce qui rend Deezer illisible aujourd'hui (29 403 manquantes mais **rien** à faire). Le contexte reste parce qu'il explique le zéro ; il est en `--ink-3` parce qu'il ne se compare pas d'une carte à l'autre. Pas de barre : le ratio actionnable/total vaut 4 % côté Beatport et 0 % côté Deezer — une jauge quasi-vide partout n'est pas un signal (même arbitrage que la mini-barre écartée sur `/genres`) |
| **A3** | **Deux régimes de carte, quatre canaux disjoints.** **Backlog** : carte `--surface` + `--shadow-sm`, chiffre **mono 600 `--fs-display` `--ink`**, bouton d'action **`.btn--accent`**. **À jour** : carte **`--bg` sans ombre** (elle s'enfonce dans la page), pas de chiffre — un **check 14 px dans une pastille 24 px `--pos-soft` / `--pos-ink`** + « À jour » 600 `--fs-title` `--pos-ink`, bouton d'action **neutre `.btn`**. Aucun rouge, aucun ambre, aucune bordure colorée | La hiérarchie est portée par le **relief** (posé vs enfoncé) et par la **densité d'encre** (36 px de mono noir vs une ligne de 24 px), pas par la couleur : les cartes en retard ressortent même en niveaux de gris, et la grille ne devient jamais un sapin d'alertes. Le **retrait de l'accent** sur les cartes à jour fait le reste du travail : en régime chargé, le mauve ne vit que sur les boutons des cartes qui en ont besoin — l'œil suit les boutons. Et le zéro n'est **pas écrit** : « 0 » est un nombre, donc quelque chose à lire et à comparer ; « À jour ✓ » est un verdict, donc quelque chose à sauter. C'est la condition pour que l'écran soit **beau à 0** au lieu d'être un mur de zéros |
| **A4** | **La grille est belle vide comme pleine, sans changer de composition** : même ordre, même gabarit, même nombre de tuiles dans les deux régimes. En régime « tout à jour », les 11 cartes deviennent des tuiles calmes et la ligne de synthèse lit « Les 11 chantiers sont à jour. ». Option `regroupeAJour` (Tweaks) pour repousser les cartes à jour en fin de grille — **désactivée par défaut** | Une console d'ops se mémorise : la carte « Set-flags » est **toujours au même endroit**, qu'elle soit à 0 ou à 158. Un tri dynamique ferait danser la grille d'une session à l'autre et coûterait plus en re-repérage qu'il ne gagne en tri — d'autant que le traitement visuel A3 fait déjà remonter le backlog à l'œil. L'option reste livrée pour arbitrage si l'usage prouve le contraire. **Aucun état vide dédié** : le régime à 0 n'est pas un vide, c'est le bon état — lui donner une illustration ou un message centré le transformerait en anomalie |
| **A5** | **Ligne de synthèse** au-dessus de la grille : « **7 chantiers sur 11 ont du travail en attente.** » (600 `--fs-title` `--ink`) · « Snapshot 06/08 · 11:30 » (mono `--fs-sm` `--ink-3`) · bouton **`Actualiser`** (`.btn--sm` + icône refresh) fer à droite. **Pas de total agrégé** | Le seul agrégat honnête est un **compte de chantiers**, pas une somme d'éléments : additionner 2 607 tracks, 5 artistes et 158 paires produit un nombre qui ne veut rien dire. L'horodatage est indispensable parce que le backlog est un **snapshot** (la passe de nuit le fait bouger d'un facteur 10) — sans lui, l'admin ne sait pas s'il regarde l'état d'il y a 10 secondes ou d'il y a 4 heures |
| **A6** | **Slot d'action : 1 bouton primaire + 1 lien secondaire.** Le bouton **lance le job** quand il en existe un (`.btn--accent`, ex. « Lancer l'enrichissement », « Fetch artworks ») ; sinon il **renvoie à l'onglet** (`.btn` neutre, ex. « Ouvrir la revue », « Voir la DLQ »). Le lien secondaire « **Onglet Beatport** » (`--fs-sm` `--ink-3`) n'apparaît **que sur les cartes à job**, jamais sur les cartes de renvoi | Un bouton mauve dit « ceci déclenche du travail serveur », un bouton neutre dit « ceci ouvre un écran » : la couleur porte la conséquence du clic, pas l'importance de la carte. Sur une carte de renvoi, le lien « voir l'onglet » ferait doublon avec son propre bouton — d'où l'asymétrie. Les files de **revue humaine** (set-flags, flags artistes) n'ont volontairement pas de bouton accent : rien ne se lance, on va lire |
| **A7** | **État « job en cours »** : le bouton passe **disabled** et son libellé devient « **En cours…** » ; une ligne mono `--fs-xs` `--accent-ink` apparaît sous le contexte avec un **arc rotatif 13 px** : « Job en cours… ». **Le compteur ne bouge pas** tant que le polling existant n'a pas renvoyé un backlog frais | Le job est asynchrone et long : décrémenter le compteur à l'optimiste mentirait. Le retour visuel vit donc **sur le bouton** (là où le clic a eu lieu) et non sur la métrique. Le spinner est le **seul mouvement** de la page — la règle DA « pas de scale, pas de bounce » interdit toute autre animation |
| **A8** | **Badge d'onglet = somme des compteurs actionnables des chantiers que l'onglet porte** (Artistes `2 995` = 5 + 2 990 · Sets `659` = 501 + 158 · Genres `42,0 k` · Crawl `56` · Beatport `2 607`). **Aperçu et Monitoring ne portent jamais de badge** | Le badge est un **ordre de grandeur** (« y a-t-il du travail derrière cet onglet ? »), le détail vit dans l'Aperçu à un clic. Le badger sur l'Aperçu double-compterait l'écran qui affiche déjà tout ; Monitoring n'a pas de file d'attente, c'est de l'observation. La règle est **uniforme, sans exception par onglet** : une exception (« sur Sets on ne compte que les flags ») rendrait le badge inintelligible dès qu'un compteur bouge |
| **A9** | **Badge à 0 = pas de badge** (défaut ; variante « badge neutre à 0 » disponible en Tweaks). Format : mono 500 `--fs-nano`, pastille `--r-pill` min-width 20 px / hauteur 18 px, `--surface-3` / `--ink-2` au repos, **`--accent-soft` / `--accent-ink` sur l'onglet actif**. **Abrégé au-delà de 9 999** : `42 031` → `42,0 k` | Corollaire direct d'A3 : l'état sain est **silencieux**. Un badge « 0 » permanent sur Flags entraînerait l'œil à ignorer la zone des badges — le jour où il passe à 3, plus personne ne le voit. L'abréviation existe parce qu'un badge est un **repère**, pas une donnée : `42 031` en nano mono fait 7 glyphes et déforme la largeur de l'onglet ; la valeur exacte est sur la carte, à un clic. Seuil à 9 999 pour que tous les compteurs réalistes (2 607, 2 995) restent exacts |
| **A10** | **Barre d'onglets à 8 : scroll horizontal ancré, jamais de wrap** (`overflow-x: auto`, `scroll-snap-type: x proximity`, `flex: 0 0 auto` par onglet, scrollbar masquée, onglet actif ramené dans la vue à la sélection). Hauteur d'onglet **44 px** (`--touch-min`), actif = `--accent-ink` + **soulignement 2 px `--accent`**, filet `--line` sur toute la largeur | Le wrap sur deux lignes rendrait la barre **instable en hauteur** : la ligne de rupture change avec la longueur des badges (« Genres 42,0 k » vs « Genres »), donc le contenu de la page sauterait à chaque rafraîchissement du backlog. Le scroll garde une barre d'une ligne, à hauteur fixe, et conserve l'ordre figé — Aperçu reste toujours le premier élément atteignable. Le soulignement (look actuel) est conservé : la refonte est ciblée, on ne change pas la grammaire de sélection |
| **A11** | **Palier mobile unique : 859 px, en container query**, repris d'`AdminFlags` (déjà en prod). Les 3 surfaces converties (**set-flags**, **mappings Genres**, **logs Crawl**) et les **4 sections sync d'`AdminArtists`** basculent au même seuil, avec la même grammaire : `thead` masqué, `tr` → carte `--surface` + `1px --line` + `--r-md`, `td` → rangée `label ⟷ valeur` dont le label vient de **`data-label`** en `::before` (mono nano uppercase `--ink-3`), boutons **pleine largeur, hauteur `--touch-min` 44 px** | Un seul seuil pour toute la console : deux paliers différents (859 chez Flags, 639 sur le bloc « Lier ») produiraient des onglets qui ne basculent pas au même moment pendant un redimensionnement, ce qui se lit comme un bug. 859 est déjà **en prod et validé** — c'est lui qui s'élève au rang de règle, le 639 du bloc « Lier » devient un cas particulier interne toléré. `data-label` est repris tel quel : l'implémentation existe, l'agent n'a rien à inventer |
| **A12** | **Palier de grille 639 px** (Aperçu uniquement) : `minmax(252px, 1fr)` ≥ 860 → `minmax(220px, 1fr)` entre 640 et 859 → **1 colonne** < 640 | Seul écran à ne pas suivre le 859 pour sa mise en colonne : une carte de chantier porte un **chiffre de 36 px + un bouton de 32 px**, deux par ligne à 375 px donnerait 165 px de carte — le bouton passerait sur deux lignes et le chiffre casserait. À 375 px, 11 cartes en pleine largeur restent parfaitement scannables (chacune fait ~150 px de haut), et c'est le geste mobile attendu : on descend la liste des chantiers |

## Onglet « Aperçu » — anatomie d'une carte de chantier

Carte : `display: flex; flex-direction: column; gap: --space-25`, padding `--space-4`, `--r-md`, `1px solid --line`.

| Zone | Spec | Tokens |
|---|---|---|
| **Eyebrow** (A1) | nom du pipeline, 600 `--fs-nano` mono uppercase, tracking 0,08em, `--ink-3` | `--font-mono` |
| **Intitulé** | le chantier, 600 `--fs-title` `--ink`, `text-wrap: pretty`, 1–2 lignes (« Set-flags en attente », « Tracks non classées ») | `--fs-title` |
| **Compteur** (A2, A3) | bloc `min-height: 42px`. **Backlog** : valeur 600 `--fs-display` mono, tracking −0,02em, `--ink` + unité 400 `--fs-xs` mono `--ink-3` (`tracks`, `artistes`, `sets`, `paires`, `mappings`, `playlists`, `entrées`), alignées sur la **baseline**. **À jour** : pastille 24 px `--pos-soft` + check SVG 14 px `--pos-ink`, puis « À jour » 600 `--fs-title` `--pos-ink` | `--fs-display`, `--pos-*` |
| **Contexte** (A2) | optionnel, 400 `--fs-xs` `--ink-3`, `text-wrap: pretty`. Chiffres en mono. Ex. « sur 65 722 manquantes · 14 abandonnées » ; à 0 la formulation **explique le zéro** : « 29 403 manquantes, toutes en cooldown · 78 abandonnées » | `--fs-xs` |
| **Job en cours** (A7) | optionnel, arc 13 px en rotation 0,9 s + « Job en cours… », mono `--fs-xs` `--accent-ink` | `--accent-ink` |
| **Actions** (A6) | `margin-top: auto` (les rangées d'actions s'alignent entre cartes voisines) : `.btn--sm` (`.btn--accent` si job, neutre sinon) + lien « Onglet X » 500 `--fs-sm` `--ink-3` | `buttons.css` |
| **Absents** | pourcentage, jauge, sparkline, historique, seuil d'alerte, code couleur rouge/ambre, icône par pipeline, total agrégé | — |

### Les 11 cartes (valeurs prod 06/08, régime « backlog chargé »)

| Eyebrow | Intitulé | Compteur | Contexte | Action primaire | Lien |
|---|---|---|---|---|---|
| Beatport | Tracks à enrichir | **2 607** | sur 65 722 manquantes · 14 abandonnées | `Lancer l'enrichissement` (accent) | Onglet Beatport |
| Deezer | Tracks à enrichir | **À jour ✓** | 29 403 manquantes, toutes en cooldown · 78 abandonnées | `Lancer l'enrichissement` (neutre) | Onglet Monitoring |
| Artistes | À lier sur Deezer | **5** | — | `Lier les artistes` (accent) | Onglet Artistes |
| Artistes | Sans pochette | **2 990** | — | `Fetch artworks` (accent) | Onglet Artistes |
| Sets | À recrawler | **501** | recrawl_status ≠ final | `Lancer le recrawl` (accent) | Onglet Sets |
| Sets | Set-flags en attente | **158** | revue manuelle — attacher ou rejeter | `Ouvrir la revue` (neutre) | — |
| Flags artistes | Flags en attente | **À jour ✓** | fusions à valider ou écarter | `Ouvrir la revue` (neutre) | — |
| Genres | Tracks non classées | **42 031** | — | `Lancer le classement` (accent) | Onglet Genres |
| Genres | Mappings non mappés | **À jour ✓** | nom brut sans node de taxonomie | `Voir les mappings` (neutre) | — |
| Crawl | Playlists dues | **56** | cadence crawl_radar | `Voir la file` (neutre) | — |
| Crawl | File d'échec (DLQ) | **À jour ✓** | clé Redis dead_letter | `Voir la DLQ` (neutre) | — |

> **Deezer est le cas de test du design** : gros `total_missing`, zéro actionnable. Sa carte doit lire « à jour » **et** expliquer pourquoi (cooldown) — sinon l'admin croit à un bug de compteur. C'est la raison d'être de la ligne de contexte à 0.
> **La DLQ n'a pas de traitement d'alerte dédié.** À > 0 elle est une carte de backlog comme les autres. Si l'usage montre qu'une DLQ non vide doit crier (c'est un échec, pas une file de travail choisie), le canal à ouvrir est `--neg` sur cette carte **seule** — à trancher après quelques semaines d'observation, pas maintenant.

## Barre d'onglets + badges

| Élément | Spec | Tokens |
|---|---|---|
| Barre (A10) | `display: flex; gap: --space-1; overflow-x: auto; scroll-snap-type: x proximity`, scrollbar masquée, filet bas `1px --line`. Ordre **figé** : Aperçu · Artistes · Flags · Sets · Genres · Crawl · Monitoring · Beatport | `--line` |
| Onglet | `flex: 0 0 auto`, hauteur **44 px**, padding `0 --space-3`, 500 `--fs-base` `--ink-2`, hover → `--ink`, bordure basse 2 px transparente, transitions 0,12 s | `--touch-min` |
| Onglet actif | 600, `--accent-ink`, bordure basse **2 px `--accent`** | `--accent` |
| Badge (A8, A9) | pastille `--r-pill`, min-width 20 px, hauteur 18 px, padding `0 5px`, **mono 500 `--fs-nano`**. Repos `--surface-3` / `--ink-2` · onglet actif `--accent-soft` / `--accent-ink` · variante neutre à 0 `--surface-2` / `--ink-3` | `--font-mono` |
| À 0 | **badge absent** (défaut) | — |
| Format | exact ≤ 9 999 (`toLocaleString('fr-FR')`), **abrégé au-delà** : `42,0 k` | — |
| Chargement / erreur | **aucun badge** tant que `/api/admin/backlog` n'a pas répondu (pas de squelette de badge : la barre ne doit pas changer de largeur deux fois au chargement) | — |
| Mobile (A10) | identique, scrollé horizontalement ; l'onglet actif est ramené dans la vue à la sélection ; **pas de wrap, pas de menu « … », pas de select** | — |

## Finition responsive — 3 patterns (palier 859 px, grammaire `data-label`)

### Grammaire commune (reprise d'`AdminFlags`, non modifiée)

```
@container adm (max-width: 859px) {
  thead masqué · tr → carte (--surface, 1px --line, --r-md, padding --space-25/--space-3, marge --space-25)
  td → flex, label ⟷ valeur, filet --line entre rangées
  td::before { content: attr(data-label) } → mono 600 --fs-nano uppercase, tracking .07em, --ink-3
  td[data-lead] → ligne de tête sans label (l'identifiant de la rangée)
  td[data-act] → bloc, bouton pleine largeur, hauteur --touch-min
}
```

### 1. Revue set-flags (onglet Sets) — 158 paires en prod

| | Desktop (inchangé) | < 859 px |
|---|---|---|
| Structure | carte de paire, deux panneaux côte à côte séparés par un filet « VS » vertical | panneaux **empilés**, le filet « VS » devient une **bande horizontale 20 px** (`border-top` + `border-bottom` `--line`, libellé mono nano `--ink-3`) |
| Panneau | cover 44 px + titre 600 `--fs-sm` (ellipsis, `min-width: 0`) + méta mono `--fs-xs` `--ink-3` (`date · durée · N tracks`) | identique, pleine largeur |
| En-tête de carte | réf. de paire (mono nano uppercase `--ink-3`) ⟷ score de similarité (mono `--fs-xs` `--ink-2`) | identique |
| Signaux | chips `--surface-2` + `1px --line`, mono `--fs-xs` `--ink-2` (`titre 0,91`, `durée ±2 min`, `tracks 24/27`) | identique, wrap |
| Actions | `Rejeter` (`.btn--sm`) puis `Attacher` (`.btn--sm .btn--accent`), fer à droite | **`flex-direction: column-reverse`** → `Attacher` **au-dessus**, les deux **pleine largeur, 44 px** |

> `column-reverse` et non `column` : l'action **par défaut** (attacher, le cas majoritaire) doit rester la plus proche du pouce sans changer l'ordre du DOM ni l'ordre de tabulation.

### 2. Mappings Genres (onglet Genres)

4 colonnes : `nom brut` (mono `--fs-table-sm`) · `node taxonomie` (`--ink`, ou « — » `--ink-3` si absent) · `statut` (badge pill mono nano : **Mappé** `--pos-soft`/`--pos-ink` · **Non mappé** `--surface-2`/`--ink-3`) · `action` (fer à droite).
< 859 : `nom brut` = **ligne de tête** (`data-lead`, sans label) ; `Node` et `Statut` en rangées label ⟷ valeur ; l'action passe en `data-act` (bouton pleine largeur 44 px, ex. « Chercher un node »). La recherche inline de node reste dans la carte, `--fs-input` **16 px** obligatoire (zoom iOS).

### 3. Logs Crawl (onglet Crawl) — 7 colonnes

`date` · `type` · `cible` · `source` · `statut` · `durée` · `stats`.
< 859 : **`cible`** devient la ligne de tête (600 `--ink`, sans label) — c'est l'identifiant de la ligne pour l'œil ; les 6 autres colonnes deviennent des rangées label ⟷ valeur, valeurs en **mono `--fs-table-sm`** (`date`, `type`, `durée`, `stats`), `source` en mono nano uppercase `--ink-3`, `statut` en badge pill (**OK** `--pos-*` · **Échec** `--neg-*`).

> 7 colonnes = 7 rangées par carte : c'est long mais **complet**, et c'est la seule table de la console qu'on lit en diagonale pour trouver une anomalie. Aucune colonne n'est masquée en mobile — masquer `durée` ou `stats` reviendrait à retirer précisément ce qu'on vient chercher dans un log.

### 4. Sections sync `AdminArtists` (note)

Les 4 rangées bouton + résultat (Sync artistes · Liaison Deezer batch · Artworks artistes · Artworks playlists) sont **scopées container** (`container-type: inline-size`) et suivent le même palier : < 859 px, titre + description empilés, **bouton pleine largeur 44 px** sous la description, ligne de résultat en mono `--fs-xs` `--ink-3` en pied de bloc. Contenu et libellés inchangés.

## États

| État | Spec |
|---|---|
| **Chargement (1er affichage)** | **11 cartes squelette** dans la grille exacte (eyebrow 64 × 9 px, intitulé de largeur variable × 13 px, compteur 96 × 32 px, action 100 % × 34 px), `--surface-3`, pulsation 1,4 s. Pas d'ombre. **Pas de `.state` centré ici** : la forme de la grille est connue, un squelette évite le saut de mise en page ; l'utilitaire global `.state` reste le rendu de chargement des **onglets existants**, inchangé |
| **Rechargement** (`Actualiser`, retour de polling) | les cartes **restent affichées** avec leurs valeurs précédentes, le bouton `Actualiser` passe en `disabled` avec son icône en rotation. Aucun flash de squelette |
| **Erreur de chargement du backlog** | bandeau `--surface` + `1px --neg` + `--r-md` : pastille 30 px `--neg-soft` / `--neg-ink` (triangle 16 px), titre « **Backlog indisponible** » 600 `--fs-md`, texte `--fs-sm` `--ink-2` (« L'appel à `/api/admin/backlog` a échoué. Les onglets et leurs actions restent utilisables ; les badges de compte sont masqués tant que le backlog n'est pas chargé. »), `.btn--sm` « Réessayer ». **La grille n'est pas rendue** — pas de cartes à « — » |
| **Job en cours** (A7) | bouton `disabled` + « En cours… », ligne mono `--accent-ink` avec arc rotatif. Le compteur reste figé jusqu'au prochain backlog frais |
| **Badge à 0** (A9) | badge absent |
| **Tout à jour** (A4) | 11 cartes en régime « À jour ✓ », ligne de synthèse « Les 11 chantiers sont à jour. ». **Aucun empty state, aucune illustration** |

## Données (`GET /api/admin/backlog` — exhaustif)

```
beatport     { pending, total_missing, abandoned }   → 2 cartes ? non : 1 carte (pending) + contexte
deezer       { pending, total_missing, abandoned }   → 1 carte (pending) + contexte
artists      { to_link, no_artwork }                 → 2 cartes
sets         { recrawl, flags_pending }              → 2 cartes
artist_flags { pending }                             → 1 carte
genres       { unclassified, mappings_unmapped }     → 2 cartes
crawl        { playlists_due, dlq }                  → 2 cartes
```

`pending` = `never_tried + due_retry` (actionnable) · `total_missing` inclut le cooldown non actionnable · `abandoned` = renoncées après 3 essais. **Le même appel alimente les badges d'onglets** (A8) — un seul fetch pour la page.
**N'existent pas** : historique, série temporelle, seuil, ETA, débit (tout cela vit dans **Monitoring**, conservé).

## Hors périmètre (mentionné pour cadrage)

- **Monitoring** : conservé tel quel, non re-designé. Rôle **observation** (burn-down, débit, hit-rate, durées) ≠ rôle **action** de l'Aperçu. Ils ne fusionnent pas ; le seul lien entre eux est le lien secondaire « Onglet Monitoring » de la carte Deezer.
- **Contenu desktop des 7 onglets existants** : inchangé (tables, boutons de job, esthétique ops-console dense).
- **Pas d'état invité** : page `require_admin`, utilisateur unique.
- **Aucun composant transverse** : cartes de chantier et badges restent admin-locaux ; la famille `components/charts/` reste dans Monitoring.

## Chantier front induit

`views/AdminView.vue` : onglet **Aperçu** ajouté **en 1re position** (landing) · barre d'onglets en `overflow-x: auto` + snap + ancrage de l'onglet actif · **badges** alimentés par `/api/admin/backlog` (règle de somme A8, abréviation > 9 999, masqués à 0 et pendant chargement/erreur).
`components/admin/AdminOverview.vue` (nouveau, admin-local) : grille `container-type: inline-size` (paliers 859 / 639) · 11 cartes de chantier (A1) · deux régimes de carte (A3) · squelettes, erreur, job en cours (A7) · un seul fetch partagé avec les badges.
`components/admin/AdminSets.vue` : revue set-flags **scopée container**, palier 859 (empilement des panneaux, bande VS horizontale, actions `column-reverse` pleine largeur 44 px).
`components/admin/AdminGenres.vue` · `AdminCrawl.vue` : tables → cartes `data-label` au palier 859 (grammaire `AdminFlags`, `data-lead` sur `nom brut` / `cible`, `data-act` sur l'action).
`components/admin/AdminArtists.vue` : 4 sections sync scopées container, même palier, boutons pleine largeur 44 px.
**Back** : aucun ajout au-delà du `GET /api/admin/backlog` déjà cadré (Lot 0).

## Grille d'audit

Couleurs 100 % tokens · dark / light vérifiés · **accent discipliné** (onglet actif, badge de l'onglet actif, bouton de job, spinner de job — aucun autre mauve ; `--pos` réservé à l'état « à jour » et aux statuts OK, `--neg` à l'erreur de chargement et au statut Échec) · **mono pour tous les nombres** (compteurs, badges, dates, durées, stats, similarités) · `--fs-input` ≥ 16 px sur la recherche de node · **container queries uniquement**, palier **859 px** partout + 639 px pour la seule grille de l'Aperçu, aucun `@media`, aucun `position: fixed` · icônes **SVG inline `currentColor`** (check, refresh, alerte, arc de chargement), zéro CDN, zéro emoji · libellés 100 % FR · **le zéro n'est jamais écrit en gros** (« À jour ✓ ») · **aucun état vide** sur la grille · **pas de badge à 0** · badges abrégés > 9 999 · cibles tactiles 44 px (onglets, boutons mobiles) · aucun `transform` au hover · **7 onglets existants non re-designés**, Monitoring intact · **aucun composant transverse créé** · pas d'état invité.
