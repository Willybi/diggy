# BRIEF — Extension `<TrackCard>` ligne · position + timecode + états set

> **Extension ADDITIVE** du composant en prod, même modèle que `BRIEF-trackcard-extension.md` (durée + artistes, livrée). Spec canonique de base : `BRIEF-composants-transverses.md`. Contrainte dure : **zéro changement de rendu pour les consommateurs actuels** (Track Detail + Playlist Detail en prod) — tout est optionnel, sans les nouvelles props le rendu est **bit-à-bit identique**. Première consommatrice : Set Detail ; réutilisable ensuite par toute liste positionnelle ou horodatée (charts, cue lists).
> Démo vivante : nuancier en bas de `Set Detail (pilote).dc.html` (identifiée · ID · non résolue · BPM/KEY absents · timecode non cliquable · playing).
> Tout en tokens `diggy-tokens.css`. Implémentation en lot dédié : tests Vitest + vitrine DesignSystemView.

## Ce qui ne bouge pas

Anatomie, grille de base `36px 1fr 42px 30px [auto]`, extension durée + artistes (`44px` entre Key et slot fin, artistes-liens `stopPropagation`, fallback chaîne plate), padding, tokens, play overlay au hover, état `playing` (`--accent-wash` + pause), « sans preview → jamais de play », play toujours visible < 640 px, transitions 0.12 s.

## Props ajoutées

| Prop | Type | Défaut | Notes |
|---|---|---|---|
| `position` | `number?` | — | fournie → colonne `#` insérée **en tête de grille** |
| `timecode` | `{ ms: number \| null, href?: string }?` | — | prop présente → colonne timecode insérée **entre durée et slot de fin** ; `ms` null → tiret |
| `state` | `'id' \| 'unresolved'?` | — | absent = comportement actuel (track identifiée) |

Chaque colonne n'existe que si sa prop est fournie (même logique opt-in que `showDuration`). Grille complète Set Detail : `28px 36px 1fr 42px 30px 44px 58px [auto]`.

## Position (optionnelle)

- Colonne 28 px en tête, mono `--fs-sm` 400 `--ink-3`, alignée droite. Pas de zéro-padding (« 7 », pas « 07 »).
- Donnée d'ordre pur — jamais un lien, aucun état hover.

## Timecode (optionnel)

- Colonne 58 px entre durée et slot de fin (assez pour `1:57:32`), mono `--fs-sm`, alignée droite. Format `m:ss` / ≥ 1 h → `h:mm:ss` (même `fmtMs` que la durée).
- `href` fourni → **lien** `--ink-2` → hover `--ink` + underline, `target="_blank" rel="noopener"`, `@click.stop` (n'active ni la ligne ni le play). Le `href` est **construit par la page consommatrice** (YouTube `?t=`, SoundCloud `#t=`) — le composant ne connaît pas les plateformes.
- `href` absent → **texte** `--ink-3` non cliquable — la voix (`--ink-2` vs `--ink-3`) distingue les deux sans icône.
- `ms` null → « — » `--ink-3`, grille conservée.

## `state="id"` — non identifiée

Visuellement **en retrait**, rien à attendre de cette rangée :

- bg `--bg` (vs `--surface` — la rangée s'efface dans la page), border 1 px `--line` inchangée.
- Artwork : placeholder rayé standard à **opacité 0.55**, **sans** indicateur in-lib, **jamais** de play overlay.
- Titre : « ID » **mono** 600 `--ink-3` ; ligne artiste (si `showArtist`) : « non identifié » `--fs-xs` `--ink-3`. `raw_title` / `raw_artist` ignorés.
- BPM / KEY / durée : cellules **vides** (pas de tirets — le tiret dit « donnée manquante », ici la track elle-même est inconnue). Position + timecode rendus normalement.
- Ligne **non cliquable** (`cursor: default`), hover : aucun changement de fond ni de bordure.

## `state="unresolved"` — non résolue

Track lue dans la source mais absente du catalog (`catalog_id` null, `is_id=false`) :

- Rendu standard (`--surface`) mais titre = `raw_title` et artiste = `raw_artist`, **texte plein sans lien** (`artists[]` ignoré).
- Artwork : placeholder rayé pleine opacité, sans indicateur in-lib (pas de notion de bibliothèque hors catalog), sans play.
- BPM / KEY / durée : « — » `--ink-3` (données inconnues, grille conservée). Timecode normal.
- Ligne non cliquable, hover neutre.

## Responsive (container query, < 640 px — max-width exclusif)

- Durée : déjà masquée (extension précédente, inchangé).
- **Quand `timecode` est fourni** : la colonne **BPM tombe aussi** — la place revient au titre et au timecode (décision S9 du brief page : le timecode est l'axe du set, BPM est une donnée de préparation). Grille : `28px 36px 1fr 30px 58px`.
- **Sans `timecode`** : comportement actuel strictement inchangé (BPM reste) — zéro régression Playlist/Track Detail.
- Play toujours visible (inchangé).

## États — récapitulatif

repos · hover (`--surface-2` + `--line-2` + play — rangées cliquables seulement) · playing (`--accent-wash` + pause) · sans preview (jamais de play) · `state="id"` (retrait `--bg`, non cliquable) · `state="unresolved"` (raw sans lien, non cliquable) · timecode lien / texte / tiret.

## Consommateurs

| Consommateur | position | timecode | state | showDuration | artists[] |
|---|---|---|---|---|---|
| Track Detail (prod, inchangé) | — | — | — | — | — (chaîne plate) |
| Playlist Detail (prod, inchangé) | — | — | — | ✅ | ✅ |
| **Set Detail** (1ʳᵉ vague) | ✅ | ✅ (href si YouTube/SoundCloud) | ✅ (`id` / `unresolved`) | ✅ | ✅ |
