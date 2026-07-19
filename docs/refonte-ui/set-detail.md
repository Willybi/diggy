# Détail set — `/set/:id`

Statut : ✅ figé  |  Vue : `views/SetDetailView.vue`

## 1. Ce qu'on a (actuel)

**Données** : `GET /api/sets/{id}` (`DJSetDetailOut`) : id, title, source, **source_url**, played_date, duration_ms, has_artwork, total_tracks, identified_tracks, **artists[]** (id, name, role, has_artwork), **tracklist[]** (`SetTrackDetailOut` : position, timecode_ms, is_id, catalog_id, catalog_title/artist, catalog_artists[], has_artwork, in_lib, has_preview). Admin : gérer les artistes (`/api/admin/sets/{id}/artists`).

**⚠️ Champs absents du schéma → code mort dans la vue** : `genres`, `event`, `venue`, `description`. Donc les **badges genres**, le **sous-titre event/venue** et le **bloc Description ne s'affichent jamais**. Et la tracklist **ne renvoie ni bpm, ni key, ni durée, ni genre**.

**Structure actuelle** :
1. **PageHero (wide)** : artwork set, titre, sous-titre (artistes B2B · *event · venue* [morts]), badges genres [morts], action **« Voir sur {source} »** (SoundCloud / YouTube / 1001Tracklists / TrackID).
2. **StatStrip** : Durée · Date · Tracks + **grosse cellule « Identifiées »** (RingPct).
3. **Description** [morte].
4. **Artistes** (si > 1) : rows avatar → `/artist`.
5. **Tracklist** (table) : # · play · **Time** (timecode → lien horodaté vers la source) · cover · Track (titre + artiste, liens) · Lib/ID (gère `is_id` = non identifié).
6. **Admin** (gérer les artistes du set) — **visible par tous**.

**Dette** : blocs morts (genres/event/venue/description) · tracklist pauvre (pas de bpm/key) · % identifiées en grosse cellule · boutons plateformes en **texte** (pas logo) · Admin non gardé · mini-composants bespoke.

## 2. Vision (William)

- Page la **moins aimée** → la rendre **plus vivante** (peu d'infos aujourd'hui).
- **Image du set plus grande** + infos en bande (comme les autres détails) : **durée, date, nb tracks**, + **roue % identifiées plus discrète**.
- Bouton SoundCloud OK ; **à terme, tous les boutons plateformes = logos, pas des noms** (transverse).
- **Tracklist enrichie** : en plus de # (ordre), cover, titre, artiste, timecode → **BPM, KEY** (+ voir si autre chose).
- Section **Sets similaires** en bas ?
- **Genre(s) du set** : d'après les données du set **ou déduits des tracks**.

## 3. Revue de cohérence (Claude)

**Constat données** : le set n'a **aucun genre stocké** → genres **déduits des tracks** (agrégat familles/genres des tracks identifiées). event/venue/description = **morts** → retirés. bpm/key tracklist = à ajouter au endpoint.

**Structure proposée** :
1. **Hero immersif** — artwork set **plus grand** (option : fond flouté depuis la cover), titre, **artistes-DJ** (liens), **genres déduits** (StyleTags), bande d'infos (Durée · Date · Tracks) + **% identifiées en petit ring discret** (plus une cellule). Boutons plateformes → **logos** (transverse).
2. **Tracklist enrichie** : # · play · cover · Track (titre + artiste) · **BPM · KEY** · timecode (→ source horodatée) · lib/ID. *(option : StyleTag par track)*. Conserve les états ID / non identifié.
3. **Sets similaires** (NOUVEAU, bas de page) — sets proches par tracks partagées / genres / artistes.
4. **Admin** — gardé **`is_admin`**.

**Keep / Improve / Remove**
- ✅ **Garder** : hero + artwork, tracklist, **timecode cliquable** (excellent), artistes, lien source, états ID.
- ➕ **Améliorer** : image plus grande + plus vivant ; **genres déduits** ; tracklist + **BPM/KEY** ; **% identifiées discret** ; boutons plateformes → **logos** (transverse) ; **sets similaires** ; `<Artwork>` in-lib.
- ➖ **Retirer** : blocs morts (event / venue / description) ; Admin → `is_admin`.

**Réponses (William)**
1. **Genres du set** : ✅ **déduits des tracks** (agrégat top familles/genres).
2. **Sets similaires** : ✅ **réutiliser le moteur de proximité global (C2)** agrégé au niveau set (un set = sa tracklist ; sets les plus proches = tracks les plus proches/recouvrantes). Plus principiel qu'un heuristique tracks+genres+artistes.
3. **Tracklist** : **sobre** à ce niveau — BPM + KEY seulement, **pas** de StyleTag par ligne.

## 4. Ré-allocation des points retirés
- **Blocs morts** (event / venue / description) → **supprimés**.
- **Admin** → restreint `is_admin` (reste sur la page).
- **Boutons plateformes** → composant **`<PlatformLink>`** (logos) → [TRANSVERSE.md](TRANSVERSE.md).
- Rien à déplacer vers d'autres pages.

## 5. Décisions figées
- **Structure** : Hero immersif → Tracklist enrichie → **Sets similaires** → Admin (`is_admin`).
- **Hero** : artwork **plus grand** (option fond flouté depuis la cover), artistes-DJ (liens), **genres déduits des tracks** (StyleTags), bande **Durée · Date · Tracks**, **% identifiées en ring discret** (plus une grosse cellule), boutons plateformes en **logos** (`<PlatformLink>`).
- **Genres du set** : **déduits des tracks** (agrégat top familles/genres) — aucun champ set.
- **Tracklist** : # · play · cover · titre · artiste · **BPM · KEY · durée** _(durée = recap C5)_ · **timecode cliquable** (→ source horodatée) · lib/ID. **Sobre** (pas de StyleTag par ligne). `<Artwork>` in-lib. Conserve les états ID / non identifié.
- **Sets similaires** (nouveau) : **moteur de proximité global C2 agrégé au niveau set** (set = tracklist).
- **Retiré** : blocs morts (event / venue / description).
- **Admin** → `is_admin`.

## 6. Sortie next-step
**Handoff Design**
- [ ] Hero immersif (artwork agrandi + fond flouté option, genres déduits, ring % discret).
- [ ] Tracklist enrichie **sobre** (BPM/KEY) + `<Artwork>` in-lib.
- [ ] `<PlatformLink>` (logos) — transverse.
- [ ] Section **Sets similaires**.

**Chantier work_manager**
- **Back** : ajouter **bpm/key/durée** à `SetTrackDetailOut` (join catalog) ; **genres déduits** `top_genres[]` (miroir playlist) ; **endpoint « sets similaires »** `GET /api/sets/{id}/similar` via `similarity_service` (set = tracklist, proximité C2 agrégée) ; `catalog_visible` sur les **nouveaux agrégats** (la tracklist existante reste le résiduel accepté C3, non filtré).
- **Front** : hero immersif ; tracklist + BPM/KEY ; retrait blocs morts ; `<PlatformLink>` ; `is_admin` sur Admin ; `<Artwork>` in-lib ; section Sets similaires.
- **Transverse** : `<PlatformLink>`, `<Artwork>`.

**Dépend de** : moteur de proximité (sets similaires) ; composants transverses.

## 7. Arbitrages pré-vol (2026-07-17)

Vérification code + arbitrages William avant le prompt Design :

- **Dette « Admin non gardé » OBSOLÈTE** : `AdminCard` gate en interne sur `is_admin` (depuis le chantier Track Detail). La décision figée « Admin → is_admin » est déjà satisfaite en prod — rien à faire.
- **Genres déduits** : contrat **miroir playlist** — `top_genres[]` (`name`, `pillar`, `depth`, `pct`), **cap 5**, agrégé sur les tracks identifiées de la tracklist.
- **Sets similaires** : `GET /api/sets/{id}/similar` — carte set complète : `id`, `title`, `source`, `played_date`, `duration_ms`, `has_artwork`, `total_tracks`, `identified_tracks`, `artists[]` (noms), **`score` exposé** (0..1, tri décroissant ; l'afficher ou non = latitude Design). **Cap 8**, roots only (`parent_set_id IS NULL`), set courant exclu.
- **Étanchéité C3** : `catalog_visible` appliqué aux **nouveaux agrégats** (genres déduits + sets similaires), miroir du lot 0 Playlist Detail. La tracklist existante reste le résiduel accepté (CLAUDE.md) — la mention « garder catalog_visible sur les tracks » du §6 originel était imprécise, corrigée.
- **Précision back** : `bpm` / `key` / `duration_ms` ajoutés à `SetTrackDetailOut` — le catalog est déjà `selectinload`é dans `get_set_detail`, coût quasi nul.
- **`_load_set_map`** : le double-comptage parents virtuels/enfants est corrigé depuis le 2026-07-16 (roots-only, fix pooling C4) — l'endpoint similaires s'appuie dessus sans correctif préalable.
- **PlatformLink** : la map couvre déjà `youtube` / `soundcloud` / `trackid` / `1001tl` — aucun logo à ajouter pour cette page.

## 8. Décisions handoff (round unique, 2026-07-17)

Handoff versionné dans [handoff-set-detail/](handoff-set-detail/) (README = provenance + conformité). Décisions DA S1-S10 du brief, dont les arbitrages pris dans la latitude laissée :

- **S1 Fond flouté retenu** : backdrop = artwork `blur(48px)`, opacité 0.22 light / 0.50 dark, pas de scrim — `has_artwork=false` → bande `--surface` nue.
- **S3 StatStrip supprimée** : Durée · Date · Tracks · Identifiées en data-row dans le hero (aligné Track/Playlist Detail).
- **S4 Ring % identifiées = `<ScoreRing mode="pct">`** (extension additive, défaut `'score'` bit-à-bit identique) — 1ʳᵉ migration de la cible TRANSVERSE « RingPct → géométrie ScoreRing ».
- **S5 Artistes-DJ** : séparateur « b2b » mono dès N ≥ 2 ; le `role` d'import (peu fiable) n'est plus affiché.
- **S6 Genres déduits sans %** : StyleTags seuls, le `pct` du contrat sert au tri.
- **S8 Tracklist = extension ADDITIVE `<TrackCard>`** (`position`, `timecode {ms, href?}`, `state 'id'/'unresolved'`) — pas de rangée bespoke ; le `href` timecode est construit par la page (le composant ignore les plateformes).
- **S9 Responsive < 640 px re-tranché** : le timecode RESTE (axe du set + accès source), BPM + durée tombent — inverse de l'actuel. Conditionnel : sans prop `timecode`, comportement actuel inchangé (zéro régression Track/Playlist).
- **S10 Sets similaires sans score affiché** : grille `<SetCard>` 4/3/2 colonnes triée par score ; slot `#footer` de la carte = porte ouverte pour `/sets`.
- **Nouveau composant `<SetCard>`** (SPEC-set-card.md) : carte set réutilisable, 1ʳᵉ conso ici, réutilisée par la future refonte de `/sets`.

**Amendements post-revue (FIX round unique, 2026-07-19 — détail dans [handoff-set-detail/FIX-set-detail.md](handoff-set-detail/FIX-set-detail.md))** :
- **Timecode cliquable** : le href se construit depuis le **domaine de `source_url`** (YouTube/SoundCloud horodatables), JAMAIS depuis `source` — un set `source=trackid` dont l'URL pointe vers SoundCloud a des timecodes cliquables, c'est voulu (la lettre initiale du brief supposait le contraire à tort).
- **Langage « donnée manquante » unifié dans TrackCard** : BPM/KEY absents sur rangée identifiée → « — » `--ink-3` (comme la durée) — s'applique aux 3 pages détail.
- `fmtCue` assoupli (`m:ss` sous l'heure) = format des timecodes ; ScoreRing n'affiche plus d'arc à 0 % ; ombre `--shadow-md` sur la cover hero.
- Layout cellule IDENTIFIÉES (label au-dessus) : arbitrage documenté — pattern data-row des pages détail, prime sur le pilote.
