# Prompt — Claude Design · Admin D11 — reskin desktop des 5 onglets non-designés

> Envoyer ce prompt au projet Claude Design (claude.ai/projects).
> Joindre en fichiers :
> - `diggy-tokens.css` (source de vérité des tokens)
> - `docs/refonte-ui/admin.md` (fiche de cadrage — **lire §8 en priorité, elle PRIME sur §1-7 pour D11**)
> - `docs/refonte-ui/handoff-admin/BRIEF-admin.md` (**la DA déjà établie sur l'Aperçu — c'est la grammaire à ÉTENDRE, pas à rediscuter**)
> - `docs/refonte-ui/TRANSVERSE.md` (décisions transverses — système d'icônes SVG, monochrome `currentColor`)
> - `docs/refonte-ui/prompts/PROMPT-claude-design-genre-detail.md` (référence de **FORMAT uniquement** — contenu sans rapport, ne pas en reprendre les décisions)
> - Captures de l'état ACTUEL (dans `C:\tmp\captures-admin-d11\`) — elles montrent le look « ops-console dense » à faire évoluer :
>   - `apercu-dark-desktop.png` + `apercu-light-desktop.png` + `apercu-dark-mobile.png` — onglet **Aperçu** (déjà designé, à HARMONISER) : grille de 12 cartes de chantier, 2 régimes backlog↔« À jour ✓ »
>   - `artistes-dark-desktop.png` — onglet Artistes : 4 panneaux d'action (sync / liaison Deezer / artworks ×2) + formulaire « Lier un artiste » double-liste + table Flags artistes (**archétypes A, D, B**)
>   - `sets-dark-desktop.png` — onglet Sets : cartes de paires set-flags (Attacher/Rejeter) + liste « Sets attachés » (Détacher) + panneau lier artistes (**archétype C + A**)
>   - `genres-dark-desktop.png` — onglet Genres : panneau Reclassify + table Mappings (filtre segmenté) (**archétypes A, B**)
>   - `enrichissement-dark-desktop.png` — onglet Enrichissement : panneau Beatport (input batch) + Backfill + **Réinitialiser Beatport (variante DANGER)** (**archétype A**)
>   - `monitoring-dark-desktop.png` + `monitoring-light-desktop.png` + `monitoring-dark-mobile.png` — bloc **Monitoring** (haut de l'onglet Observabilité), courbes rendues : StatTiles + 4 blocs de courbes + sparklines + table « dernier passage » (**archétype F**)
>   - `observabilite-dark-desktop.png` — onglet Observabilité : les tables **Crawl History** (7 col.) et **Journal d'audit** sous le Monitoring (**archétype B** ; le Monitoring y apparaît en « Chargement… » car async — voir les captures `monitoring-*` pour son rendu réel)
>   - `sets-dark-mobile.png`, `genres-dark-mobile.png`, `observabilite-dark-mobile.png` — mobile 375 : grammaire cartes `data-label` (palier 859px) **déjà acquise**, à harmoniser
>   - `artistes-light-desktop.png` — thème light témoin

---

## Contexte

Tu es le designer de **Diggy**, web app DJ (Vue 3, DA « Wildflower », dark par défaut, tokens centralisés, container queries). L'UI est refondue page par page ; tu produis le **handoff purement design** qu'un agent applique ensuite.

**Cette page : `/admin`** — une **console d'ops** réservée à l'admin (`require_admin`, un seul utilisateur : le créateur). Elle sert à lancer des jobs (enrichissement, crawl, sync) et à modérer des files (flags artistes/sets, mappings de genres, logs, audit).

**Historique — lis bien, il cadre exactement ton périmètre :**
- Un premier chantier (D4-Admin) a **designé l'onglet « Aperçu »** (dashboard backlog) et posé la **finition responsive mobile** (palier 859px, grammaire `data-label`). Son handoff = `BRIEF-admin.md` (joint). **Il a délibérément GARDÉ le look « ops-console dense » brut** des autres onglets (tables sans traitement, boutons de job ad-hoc, emoji dans les résultats).
- Depuis, l'IA a été figée à **6 onglets** : `Aperçu` · `Artistes` · `Sets` · `Genres` · `Enrichissement` · `Observabilité`.

**D11 = ce chantier-ci : lever ce gel.** Tu appliques la **DA déjà établie sur l'Aperçu** au **contenu DESKTOP** des 5 onglets qui ne l'ont jamais reçu, pour que la console entière ait la même qualité visuelle. Ce n'est PAS un nouveau langage : c'est l'**extension cohérente** de la grammaire du `BRIEF-admin.md` (cartes `--surface`/`--r-md`/`--line`, accent discipliné, mono pour les nombres, `--pos`/`--neg` soft pour les statuts, spinner d'unique mouvement).

**Périmètre strict : design/UX visuel.** Aucune logique ne change (mêmes endpoints, mêmes jobs, mêmes données). Les données listées plus bas sont **exhaustives — ne rien inventer au-delà**.

## L'Aperçu (`AdminOverview`) — HARMONISATION, pas refonte

L'onglet **Aperçu** a **déjà une DA validée** : c'est exactement le `BRIEF-admin.md` (joint) — grille de **cartes de chantier**, **2 régimes** (backlog = chiffre mono + bouton accent · à jour = pastille check `--pos` + « À jour »), badges d'onglets A8/A9, états squelette/erreur/job-en-cours. **Il fait partie de la livraison D11** (William veut une console cohérente d'un bloc), mais tu le traites en **HARMONISATION** : tu le **ré-émets dans le BRIEF/la maquette D11** en le rendant cohérent avec les nouveaux archétypes (icônes **SVG** partout, pills de statut identiques, mêmes tokens) — **sans jeter** la structure éprouvée (grille de cartes, 2 régimes, badges). Ne réinvente pas sa composition ; aligne son détail. NB : il porte aujourd'hui **12 cartes** (une carte « À analyser (BPM) » a été ajoutée depuis le BRIEF D4 qui en listait 11) — prends-le en compte, ne le ramène pas à 11.

## Ce que tu NE touches PAS (hors périmètre, à ne pas re-designer)

- **La barre d'onglets et les badges** (`AdminView`) : grammaire figée (scroll horizontal ancré, onglet actif souligné 2px `--accent`, badge mono nano abrégé > 9999, absent à 0). Latitude légère sur le spacing du header seulement — ne re-litige pas la grammaire.

> **NB périmètre** : le **Monitoring** (dashboard de courbes de l'onglet Observabilité) fait DÉSORMAIS partie du reskin — voir l'**archétype F** ci-dessous. Il n'y a plus rien d'« intact » dans la console hormis la barre d'onglets. L'onglet Observabilité (Monitoring + Crawl + Audit) devient donc **entièrement designé** : compose sa cohérence interne (le dashboard au-dessus, les deux tables en dessous).

## Décisions produit FIGÉES (fiche §8.4 — à respecter, pas à rediscuter)

1. **Purge des emoji.** Le code actuel affiche des emoji/glyphes dans les lignes de résultat et les chips (`✓ ⚠ ↷ 🔗 🔎 ⌀ 🗑 ↩`). La DA impose **SVG inline `currentColor`, zéro emoji, zéro CDN**. Fournis/nomme le petit jeu d'icônes nécessaire (check, warn, skip/undo, link, search, trash, spinner/arc) et un traitement typographique **mono** des compteurs de résultat.
2. **Container queries uniquement, palier 859px** comme norme (déjà en prod sur la plupart). **Combler les 3 trous mobiles** (voir archétypes) : le panneau Beatport, le panneau Actions d'enrichissement et le widget de découpe n'ont aujourd'hui **aucune** adaptation mobile (boutons non tactiles < 44px). Aucun `@media` (sauf `position:fixed`, absent), aucun `position:fixed`.
3. **Tokens & accent du `BRIEF-admin.md` font foi.** Accent mauve discipliné (déclencheur de job, spinner de job, onglet actif) ; `--pos` = état à jour / statut OK ; `--neg` = erreur / échec / action destructive (reset). **Aucun rouge/ambre décoratif, aucune bordure colorée gratuite.** `--font-mono` pour **tous les nombres** (compteurs, dates, durées, fans, confidence, ids).
4. **Page `require_admin`, utilisateur unique** : aucun état invité, aucune permission à dessiner.
5. **Logique inchangée** : mêmes endpoints/payloads/jobs/gardes (confirmation du reset, polling de statut). Reskin **visuel pur** — tu ne changes ni le contenu, ni les libellés fonctionnels, ni le nombre de colonnes des tables.

## Ce que tu dois designer — l'Aperçu harmonisé + les 6 archétypes UI

En plus de l'**Aperçu harmonisé** (section précédente), le reste de la console se ramène à **6 archétypes**. Donne à chacun un langage unique, appliqué partout (fin de la divergence ad-hoc actuelle où chaque composant re-déclare ses propres `.sync-*` / `.flag-table` / `.state`). Pour chaque archétype : anatomie, tokens, états, et rendu desktop **+** mobile 859px.

### A — Panneau d'action / déclencheur de job
Surfaces : les **4 sections sync** d'`AdminArtists` (Sync artistes · Liaison Deezer batch · Artworks artistes · Artworks playlists), le panneau **Beatport**, les **Actions d'enrichissement** (Backfill multi-artistes + Réinitialiser Beatport), le § **Lier artistes aux sets** (AdminSets), le § **Reclassifier tous les genres** (AdminGenres).
- Anatomie type : **titre + description courte + bouton de lancement + ligne de résultat mono**. Réutilise la grammaire de carte de l'Aperçu (`--surface`, `1px --line`, `--r-md`). Bouton = `.btn--accent` pour un job.
- **État « job en cours »** = reprends le pattern **A7 du BRIEF Aperçu** : bouton `disabled` + libellé « En cours… » + **arc rotatif** `--accent-ink` (le spinner est le seul mouvement autorisé, pas de scale/bounce).
- **Ligne de résultat** : compteurs mono + micro-icône SVG par item (ex. « ✓ 12 créés · ⚠ 3 erreurs · ↷ 5 en attente » deviennent des paires `icône SVG + nombre mono + label`). Prévois les variantes : succès, partiel (warns), « déjà en cours » (lock pris), erreur.
- **Variante DANGER** (Réinitialiser Beatport) : discipline `--neg`, **confirmation inline conservée** (bouton → zone d'avertissement → Confirmer / Annuler). C'est la seule surface destructive ; elle doit se lire comme telle sans crier.
- Un champ optionnel accompagne certains panneaux : `Batch size` (number, Beatport), `Planifier à` (datetime-local, reclassify). Style d'input aligné tokens, `--fs-input` ≥ 16px (anti-zoom iOS).

### B — Table dense paginée
Surfaces : **Flags artistes** (AdminFlags), **Logs Crawl** (AdminCrawl, 7 colonnes), **Journal d'audit** (AdminAuditLog), **Mappings genres** (AdminGenres).
- Anatomie type : **header** (titre + badge compte + barre de filtres) → **table** → **pagination** (Précédent / `page / total` / Suivant).
- Traitement desktop : filet `--line`, en-têtes discrets, **statuts en pills** (`--pos-soft`/`--pos-ink` OK · `--neg-soft`/`--neg-ink` échec · neutre `--surface-2`/`--ink-3`), **nombres/dates/durées en mono**, `reason`/`action`/`source` en pills nano uppercase. Hover de ligne sobre.
- **Mobile 859px `data-label` : ACQUIS pour Flags/Crawl/Audit/Mappings — ne le casse pas, harmonise-le** avec la nouvelle grammaire desktop (mêmes pills, mêmes icônes SVG).
- Cas particuliers à respecter : Crawl a une colonne `stats` (chips `clé: valeur`) + `error_message` tronqué ; Audit a une colonne `détails` (JSON dépliable `<details>`) ; Mappings a une **recherche de node inline** dans la ligne (input + dropdown de résultats) ; Flags a une **ligne éditeur dépliable** qui embarque le widget de découpe (archétype E).
- Piste socle partagé : voir Latitude.

### C — Revue par cartes de paires
Surfaces : **Set-flags en attente** + **Sets attachés** (AdminSets).
- Cartes de paires (set A ↔ set B, ou liste de `member_titles`) avec méta (`flag_type` Doublon/Parties, `confidence %`, signaux `part_numbers` / `date_span_days` / `date_gap_days`) et actions **Attacher** / **Rejeter** ; les sets attachés listent leurs membres avec un bouton **Détacher**.
- Le desktop actuel est déjà en cartes mais brut → applique le langage de carte de l'Aperçu. Le **mobile 859px** (empilement des panneaux, bande « VS » horizontale, actions `column-reverse` pleine largeur 44px) est **acquis** — harmonise-le.

### D — Formulaire de recherche + double liste
Surface : le § **« Lier un artiste à Deezer »** d'`AdminArtists`.
- Deux inputs de filtre, **colonne gauche** = artistes sans deezer_id (toggle Actifs/Dormants + liste de rows : vignette/initiale + nom + actions au hover `✗ Deezer` / `Flagguer` / `Splitter`), **colonne droite** = résultats Deezer (image + nom + `nb_fan` mono + id), puis **carte de confirmation** (« Lier X → Deezer Y », Confirmer). Palier double-colonne → empilé sous 639px (acquis, à harmoniser).
- Applique le langage de liste/rows et de carte de confirmation cohérent avec le reste.

### E — Widget interactif de découpe (`ArtistSegmentSplitter`)
Composant partagé (enfant d'AdminArtists et AdminFlags). Découpe une chaîne d'artiste brute en segments : **boutons de coupe** togglables entre les unités (`|` actif / `·` inactif), **chips de segments** avec signal Deezer live par segment (spinner / `✓ nom · N fans` / `✗`) et bouton garder/supprimer, puis bouton Confirmer.
- **Trou tactile à combler** : les boutons de coupe (~20px) et poubelle sont sous la cible `--touch-min` 44px. Donne-leur un traitement tactile propre. Remplace les glyphes emoji (🗑 ↩) par SVG.

### F — Dashboard d'observation (`AdminMonitoring` + `components/charts/`)
Surface : le bloc **Monitoring** (haut de l'onglet Observabilité). Composants SVG **maison, déjà token-driven** : `StatTile` (tuile chiffre + libellé + sparkline optionnelle), `TimeSeriesChart` (courbe multi-séries avec légende, axes, aires), `SparkLine`. Anatomie actuelle (à re-styler, PAS à ré-architecturer) :
- **Rangées de StatTiles** : « Backlogs d'enrichissement » (Deezer/Beatport/artistes/sets/sets non fiables/catalogue/BPM/embeddings/covers/métadonnées…), « Intégrité artiste » (divergence, sans lien) — grille de tuiles chiffre mono + libellé nano uppercase + sous-texte + mini-sparkline.
- **Blocs de courbes** `TimeSeriesChart` : « Enrichissement plateforme dans le temps », « Backfills de contenu », « Petits soldes & qualité », « Débit & taux de réussite » (2 courbes côte à côte) — chacune avec **titre + phrase d'explication + légende de séries + axes datés**.
- **StatTiles « Erreurs & durées »** (erreurs période avec sparkline, durée max, dernier run par pipeline).
- **Table « Dernier passage par tâche »** : pipeline · source (pill) · statut (pill Succès/Erreur/En cours) · ancienneté · durée (mono).
- **Toolbar** : sélecteur de fenêtre (`30 jours`) + bouton `Rafraîchir` + horodatage « Dernier instantané ».
Objectif : donner au dashboard le **même raffinement visuel** que le reste (hiérarchie des titres/légendes, densité, traitement des axes/grille, couleurs de séries **discipline tokens** — plusieurs séries = plusieurs teintes, mais dérivées des tokens, pas un arc-en-ciel). **Ne change ni les données, ni les séries, ni le nombre de graphes.** Mobile 859px : tuiles en colonne, courbes pleine largeur lisibles.

> Les 3 composants `charts/` ne sont montés QUE par Monitoring : tu as toute latitude pour les re-styler (légendes, axes, épaisseurs, aires, tooltips). Reste en **container queries** et **tokens** ; les courbes doivent rester lisibles en dark ET light.

## Données disponibles (exhaustif — ne rien inventer au-delà)

Tout existe déjà côté back (D11 n'ajoute aucun endpoint). Champs réellement affichés :

**Aperçu (archétype cartes de chantier)** — `GET /api/admin/backlog` (déjà en place, alimente cartes ET badges d'onglets) : `beatport {pending,total_missing,abandoned}` · `deezer {pending,total_missing,abandoned}` · `bpm {pending}` (carte « À analyser (BPM) », ajoutée E2.c) · `artists {to_link,no_artwork}` · `sets {recrawl,flags_pending}` · `artist_flags {pending}` · `genres {unclassified,mappings_unmapped}` · `crawl {playlists_due,dlq}`. `pending`=`never_tried+due_retry` (actionnable), `total_missing` inclut le cooldown, `abandoned`=renoncées. Les valeurs prod et l'anatomie détaillée sont dans le `BRIEF-admin.md` (§ « Les 11 cartes » + « Données ») — reprends-les, en ajoutant la carte BPM.

**Panneaux d'action (archétype A)** — lancent un job puis pollent son statut (`{status, result, error}`). `result` par job :
- sync artistes : `{created, flagged, skipped}`
- liaison Deezer artistes : `{linked, searched, abandoned, errors, dropped_by_budget}`
- artworks artistes : `{fetched, skipped, errors, dropped_by_budget}`
- artworks playlists (synchrone) : `{fetched, failed, total}`
- Beatport : `{enriched, not_found, errors, total}` ou `{skipped:'already_running'}`
- backfill multi-artistes : `{enriched, errors, total}` ou `{skipped}`
- lier artistes aux sets : `{linked, skipped}`
- réinitialiser Beatport (synchrone, DANGER) : `{cleared, bpm_reverted, key_reverted}`
- reclassify genres : renvoie un `task_id` (confirmation simple, pas de suivi)

**Tables (archétype B)** :
- Flags artistes : `{id, raw_artist_string, reason, tokens[], status}` (+ signal Deezer live par token : `nb_fan`)
- Logs Crawl (7 col.) : `{started_at, task_type, target_label, source, status, duration_ms, stats{}, error_message}`
- Journal d'audit : `{created_at, user_email, action, target_type, target_id, details{}}`
- Mappings genres : `{rawName, nodeLabel, nodeId, nodeWikidataId}` + recherche de node → `{label, wikidataId}`

**Cartes de paires (archétype C)** :
- Set-flags : `{id, flag_type, confidence, member_titles[], title_a, title_b, signals{part_numbers[], date_span_days, date_gap_days}}`
- Sets attachés : groupes `{id, sets:[{id, title}]}`

**Formulaire liaison (archétype D)** :
- artistes sans deezer : `{id, name, has_artwork}` (+ `active_count`, `dormant_count`) ; vignette = `/storage/artist-artworks/{id}.jpg`
- hits Deezer : `{deezer_id, name, picture, nb_fan}`

**Monitoring (archétype F)** — `GET /api/admin/monitoring` (déjà en place) : renvoie des **StatTiles** (compteurs instantanés de backlog + intégrité), des **séries temporelles** (enrichissement plateforme, backfills embeddings/BPM/albums, petits soldes covers/sets-non-fiables, débit & taux de réussite/jour) et le **dernier run par pipeline** (statut, ancienneté, durée). Tu re-STYLES ces visualisations existantes (tuiles, courbes, table) — **tu ne changes ni les séries ni les données**. La liste exacte des tuiles/courbes est dans les captures Monitoring jointes ; ne rajoute aucune métrique.

**N'existent PAS** (ne pas inventer) : score de progression global, ETA, seuils d'alerte. Les tuiles/séries de Monitoring sont **exactement** celles des captures — ne pas en imaginer d'autres.

## Ce que tu dois livrer

### 1. `BRIEF-admin-D11.md` — le handoff
Même format que `BRIEF-admin.md` (tables de tokens, anatomie par archétype, états, décisions DA explicites `Dn` avec justification). Doit couvrir **l'Aperçu harmonisé** (grille de cartes reprise du BRIEF-admin.md + carte BPM, icônes SVG) **et** les **6 archétypes** (A→F, desktop + mobile 859px), la **purge emoji → jeu d'icônes SVG**, le **dashboard Monitoring re-stylé** (StatTiles, courbes, table — données inchangées) et sa cohérence avec les tables sous lui, la variante **danger** (reset), et une **grille d'audit** finale (tokens, accent discipliné, séries de courbes dérivées des tokens, mono, container-queries 859px, 44px tactile, zéro emoji, FR, pas d'état invité).

### 2. `Admin-D11-pilote.html` — maquette interactive
Maquette HTML autonome consommant les tokens (zéro couleur hardcodée), montrant **l'Aperçu harmonisé** (grille de cartes, 2 régimes backlog↔à-jour, carte BPM) **et les 6 archétypes reskinnés** avec des données réalistes (utilise les champs ci-dessus) : un panneau d'action (avec état job-en-cours + variante danger), une table dense (avec pills de statut + un cas mobile), une carte de paire, le formulaire double-liste, le widget de découpe, **un extrait du dashboard Monitoring re-stylé (une rangée de StatTiles + une courbe TimeSeriesChart multi-séries + la table « dernier passage »)**. Toggles **dark/light** + **viewport desktop / 375px** — les courbes doivent être lisibles dans les deux thèmes.

### Livraison — IMPORTANT
**Fournis tous les livrables dans une SEULE archive `.zip` téléchargeable (un seul lien).** Sans cette consigne explicite l'archive n'est pas générée et le transfert devient manuel. L'archive contient `BRIEF-admin-D11.md` + `Admin-D11-pilote.html`.

## Latitude accordée

- **Socle de table partagé (archétype B)** : tu peux proposer que les 4 tables partagent **un socle CSS admin commun** (le repo a déjà `assets/list-table.css` `.lt-*`, socle des listes Sets/Watchlist — **PAS `TrackTable`, qui est track-spécifique et virtualisé, inapplicable ici**) plutôt que 4 traitements divergents. Décris le rendu ; l'implémentation tranchera le vecteur.
- **Densité / regroupement** : compose comme tu le sens les 4 sections sync d'`AdminArtists` (4 cartes empilées, ou un bloc groupé), la disposition des panneaux d'action de l'Enrichissement, etc.
- **Filtres segmentés** : le repo a un composant `components/filters/SegmentedFilter` — tu peux t'aligner sur son look **sans le modifier**, ou décrire un segmenté admin-local.
- **Aucun composant transverse Vue nouveau attendu** (surfaces admin-locales). Un éventuel socle CSS partagé n'est pas un composant Vue.

## Design system — contraintes (rappel)
- **Tokens** : tout via `var(--...)` de `diggy-tokens.css`. Zéro couleur hardcodée.
- **Typo** : `--font-ui` texte, `--font-mono` pour **tous les nombres**.
- **Icônes** : SVG **inline `currentColor`**, aucun CDN (CSP), **zéro emoji**.
- **Thèmes** : dark par défaut + light, la maquette supporte les deux.
- **Responsive** : container queries (`@container`), palier **859px** (jamais `@media` sauf `position:fixed`, absent ici). Cibles tactiles 44px (`--touch-min`).
- **UI en français.** **Pas d'état invité** (`require_admin`).

## Récapitulatif des livrables (dans un seul `.zip`)

| Fichier | Contenu |
|---------|---------|
| `BRIEF-admin-D11.md` | Handoff : Aperçu harmonisé + 6 archétypes A→F (desktop + mobile 859px), dashboard Monitoring re-stylé, purge emoji → icônes SVG, variante danger, états job/erreur/vide, grille d'audit |
| `Admin-D11-pilote.html` | Maquette interactive : Aperçu harmonisé + un exemplaire de chaque archétype (dont un extrait Monitoring : StatTiles + courbe + table), toggles thème/viewport |
