# BRIEF — Extension `<TrackCard>` ligne · durée + artistes cliquables

> **Extension ADDITIVE** du composant en prod, spec canonique : `BRIEF-composants-transverses.md`. Contrainte dure : **zéro changement pour les consommateurs actuels** (TrackDetailView) — tout est optionnel, la forme actuelle reste le défaut. Composant autonome : première consommatrice Playlist Detail, réutilisé ensuite par Radar, Nouveautés et toute liste de tracks.
> Démo vivante : nuancier en bas de `Playlist Detail (pilote).html` (défaut inchangé · + durée · artistes cliquables · fallback · playing).
> Tout en tokens `diggy-tokens.css`. Implémentation en lot dédié : tests Vitest + vitrine DesignSystemView.

## Ce qui ne bouge pas

Anatomie, grille de base `36px 1fr 42px 30px [auto]`, padding, tokens, slot de fin (`<ScoreRing>`…), play overlay au hover, état `playing` (`--accent-wash` + pause), « sans preview → jamais de play », play toujours visible < 640 px, transitions 0.12 s. **Sans les nouvelles props, le rendu est bit-à-bit identique à aujourd'hui.**

## Props ajoutées

| Prop | Type | Défaut | Notes |
|---|---|---|---|
| `showDuration` | `boolean` | `false` | opt-in explicite du consommateur — la colonne n'existe pas sinon |
| `track.duration_ms` | `number?` | — | lu seulement si `showDuration` ; null → tiret « — » `--ink-3` (l'alignement de la grille est conservé) |
| `track.artists` | `{id, name}[]?` | — | fourni → liens ; absent → fallback chaîne `track.artist` existante (rendu inchangé) |

## Durée (optionnelle)

- **Placement** : colonne insérée **entre Key et le slot de fin** → grille `36px 1fr 42px 30px 44px [auto]`.
- **Rendu** : mono `--fs-sm` 400 `--ink-2`, alignée droite — même voix que BPM (la Key garde seule l'accent, D4).
- **Format** : `m:ss` (minutes non paddées, secondes sur 2 chiffres) ; ≥ 1 h → `h:mm:ss` (rare, mixes).
- **Responsive** : **masquée < 640 px** (container query, convention max-width exclusif) — donnée secondaire, la place revient au titre/artistes. BPM et Key restent.

## Artistes cliquables (optionnels)

Concerne la ligne artiste (rendue quand `showArtist=true`, inchangé).

- `artists[]` fourni → **un lien par artiste** vers `/artist/:id`, séparés par « , ». **Ne jamais supposer un seul artiste.**
- Style : liens `--fs-xs` `--ink-3` (identique au texte actuel) → hover `--ink` + underline. La ligne complète reste ellipsée sur un niveau (`white-space: nowrap`), troncature en fin de liste.
- **Clic artiste ≠ clic ligne** : `stopPropagation` — n'active ni la navigation de la ligne ni le play.
- `artists[]` absent ou vide → **fallback chaîne plate `artist`**, non cliquable, rendu strictement identique à l'existant.
- A11y : liens réels (`<a href>`), le nom est le libellé — pas d'`aria-label` supplémentaire.

## États — inchangés

repos · hover (`--surface-2` + `--line-2` + play visible) · playing (`--accent-wash`, pause, hover reste wash) · sans preview (jamais de play). Les liens artistes restent lisibles sur `--accent-wash` (`--ink-3`/`--ink` passent les deux thèmes).

## Consommateurs

| Consommateur | showDuration | artists[] | Slot fin |
|---|---|---|---|
| Track Detail (prod, inchangé) | — | — (chaîne plate) | `<ScoreRing>` / vide |
| **Playlist Detail** (1ʳᵉ vague) | ✅ | ✅ (✦ lot 0 back) | vide |
| Radar, Nouveautés, listes (ensuite) | selon page | ✅ | `<ScoreRing>` |
