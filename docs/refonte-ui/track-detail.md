# Détail track — `/catalog/:id`

Statut : ✅ figé  |  Vue : `views/TrackDetailView.vue`

## 1. Ce qu'on a (actuel)

**Bonne surprise : la page implémente déjà l'essentiel de la vision.** C'est une **refonte**, pas une création.

**Données** : `GET /api/catalog/{id}` renvoie tout — base (bpm, key, duration_ms, release_date, genres, style, **tags Rekordbox**, label, beatport_id, deezer_id, isrc, in_lib, avis, has_preview, nb_radar_playlists, nb_radar_sets) + **`radar_appearances[]`** (playlist_id/title/source, detected_at) + **`set_appearances[]`** (set_id/title, timecode_ms, played_date) + **`same_artist_tracks[]`**. Similaires via `GET /api/catalog/{id}/similar?limit=8` (moteur C2, score %). `PATCH /api/catalog/{id}/avis` (like/dislike).

**Structure actuelle (de haut en bas)** :
1. **Hero** (`PageHero`, cover carrée) : titre · **artist-chips** (avatar rond → `/artist`) · badges (InLibBadge, StyleTags → `/style`, tags Rekordbox) · actions (`HeroPlayer` preview, `LikeDislike`, **Ajouter à une collection** dropdown).
2. **StatStrip** : BPM · Key · Durée · Année · **Rating** · Radar (nb playlists) · Radar sets.
3. **Meta** : label + lien **Beatport ↗**.
4. **2 colonnes** : **« Détecté dans »** (playlists radar : source + date → `/playlists/:id`) · **« Apparaît dans »** (sets : **timecode ▶** + date → `/set/:id`).
5. **« Du même artiste »** (mini-grid : cover, titre, bpm, key, play, **rating★**, lib dot).
6. **« Tracks similaires »** (mini-grid + **score %** C2).
7. **`AdminCard`** (bas) : beatport_id/deezer_id/isrc + boutons enrich Beatport / genre Deezer.

**Composants** : PageHero, StatStrip, RelBlock, InLibBadge, StyleTag, HeroPlayer, AdminCard, LikeDislike, SourceBadge, LibDot.

**Dette / limites (factuel)** :
- **Rating** présent (StatStrip + étoiles dans « Du même artiste ») → à retirer (décision transverse).
- **`AdminCard` visible par TOUS** les users connectés (pas de garde `is_admin`) : expose les IDs internes + boutons enrich (qui 403 pour un non-admin). Incohérence.
- Mini-rows « même artiste » / « similaires » = lignes bespoke → candidates au **`<TrackCard>` compact partagé**.
- In-lib via InLibBadge (hero) + LibDot (rows) → à unifier avec l'indicateur cover `<Artwork>`.

## 2. Vision (William)

- Une **bande en haut** avec la cover + toutes les **infos de base**.
- Puis **plein d'infos sur où le son est** (apparu dans quel set / quelle playlist).
- Puis des blocs **« du même artiste »**, **« similaire »**, etc.
- Ordre & mise en forme **pas encore fixés** — « commence à regarder ».

## 3. Première lecture & proposition (Claude)

**L'ordre actuel colle déjà à ta vision.** Je le garderais, en le polissant. Proposition de structure :

1. **Hero** — cover (`<Artwork>` + **indicateur in-lib**), titre, artistes, genres + tags Rekordbox, **actions** (play, like, collection), liens externes (label, Beatport, Deezer). Stats essentielles **BPM · Key · Durée · Année** intégrées au hero ou juste dessous. **Rating retiré.**
2. **Contexte « Où on l'entend » — SOBRE** (le bloc distinctif, juste sous le hero) :
   - **Apparaît dans les sets** (timecode + date) + **Détecté sur les playlists** (source + date), avec le compteur du RelBlock.
   - Pas de nom de DJ / 1re-dernière détection / ligne de résumé (décision : sobre).
3. **Découverte / rebond** :
   - **Du même artiste**.
   - **Tracks similaires** (C2) — score en **`<ScoreRing>` /10**.
   - ~~Souvent joué avec~~ — **écarté** : la co-occurrence est déjà un facteur du moteur de similarité → redondant avec « Similaires ».
4. **Admin — réservé aux admins (`is_admin`)** — enrich Beatport/Deezer + IDs. Aujourd'hui visible par tous → **restreint**.

**Keep / Improve / Remove**
- ✅ **Garder** : hero, appears-in (sets + playlists) sobre, même artiste, similaires, collection, like/dislike, liens externes, tags Rekordbox.
- ➕ **Améliorer** : `<Artwork>` in-lib partout ; mini-rows → `<TrackCard>` compact partagé ; score similaire via `<ScoreRing>` /10.
- ➖ **Retirer** : Rating (transverse) ; AdminCard → gardée `is_admin`.

## 4. Ré-allocation des points retirés
- **Rating** → suppression globale (transverse), pas ré-alloué.
- **Bloc Admin** → pas supprimé mais **restreint `is_admin`** (reste sur la page, invisible aux users).
- Rien à déplacer vers d'autres pages.

## 5. Décisions figées *(mises à jour 2026-07-17 — handoff Design round 2, validé William)*
- **Structure** : Hero → **Découverte** (Du même artiste + Similaires) → « Où on l'entend » (sobre) → Admin (`is_admin`). *(Ordre Découverte/Où-on-l'entend inversé au round 2 : le rebond d'abord, le contexte radar ensuite.)*
- **Rating** : retiré partout (stats + étoiles des mini-lignes).
- **Bloc Admin** : réservé aux admins (`is_admin`), tout en bas.
- **StatStrip SUPPRIMÉE** (round 2, D1/D2) : les 4 stats musicales **BPM · Key · Durée · Année** intègrent le hero (data-row mono) ; les compteurs Radar (`nb_radar_playlists`/`nb_radar_sets`) deviennent les compteurs d'en-tête des blocs « Où on l'entend ».
- **`<Artwork>` in-lib** partout (plus d'InLibBadge ni LibDot) ; mini-lignes « même artiste / similaires » → **`<TrackCard>` ligne** partagé.
- **Score des similaires** : **`<ScoreRing>` /10** (cohérence Radar), jamais le float ni le %.
- **« Où on l'entend » sobre** : sets (chip timecode + date) + playlists (**glyphe source** `<PlatformLink variant="glyph">` au lieu du badge texte + date) + compteur en en-tête ; pas de DJ / 1re-dernière / résumé. **Troncature 5 lignes** + « Afficher plus (n) ».
- **« Du même artiste » tronqué à 6** + « Afficher plus (n) » ; similaires non tronqués (8 max API).
- **Liens externes en logos** : `<PlatformLink>` Beatport/Deezer, monochromes `currentColor` (D6 — jamais les couleurs de marque). Logos temporaires (tracés simplifiés) centralisés dans `PlatformLink.vue` en attendant les SVG officiels.
- **Écarté** : bloc « Souvent joué avec » (co-occurrence déjà un facteur de similarité).
- **Conserve** : hero (cover/artistes/actions), collection, like/dislike, label texte, tags Rekordbox.

## 6. Sortie next-step
**Handoff Design** — ✅ LIVRÉ (2026-07-17) : `docs/refonte-ui/handoff-track-detail/` (BRIEF-track-detail + BRIEF-composants-transverses + maquette pilote).

**Chantier work_manager**
- **Lot 1 (transverse)** : créer `<Artwork>`, `<TrackCard>` ligne, `<ScoreRing>`, `<PlatformLink>` + tests Vitest.
- **Lot 2 (page)** : refonte `TrackDetailView` — StatStrip retirée (stats dans le hero), Découverte avant « Où on l'entend », troncatures, glyphes source, retrait Rating de la page, **garde `is_admin`** sur l'AdminCard.
- **Back** : rien (données déjà servies par `GET /api/catalog/{id}` + `/similar`) ; le drop colonne Rating reste au chantier transverse Rating.

**Dépend de** : rien — première page implémentée de la refonte, elle CRÉE les composants partagés.
