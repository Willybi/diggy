# FIX — Track Detail · revue post-implémentation Claude Design (2026-07-17, round unique)

> Base : captures `/catalog/641` (5 vues) + code `master` contre les briefs versionnés du dossier.
> Verdict Claude Design : **implémentation très conforme** — 7 écarts, aucun bloquant.
> Triage work manager + corrections livrées au lot 3 (même jour). Statut final par écart ci-dessous.

| # | Écart | Triage | Résolution |
|---|---|---|---|
| 1 | [spec] Padding de page dérivé de `--pad` (scopé densité, cf. design-decisions.md §3) au lieu de `--page-px` | ACCEPTÉ | ✅ Corrigé : `.detail-view` → `var(--space-6) var(--page-px) var(--space-10)`. NB : les autres pages détail (Artist/Set/Playlist) gardent l'ancien pattern — à aligner à leur tour de refonte |
| 2 | [spec] Hauteurs hero non alignées (`.btn-coll` 34px vs PlatformLink 38px) | ACCEPTÉ partiel | ✅ `.btn-coll` → 38px. `LikeDislike` (30px) est un composant PARTAGÉ (CatalogView…) — hors périmètre d'un fix local, à traiter quand la refonte touchera ses autres consommateurs |
| 3 | [spec] Dropdown : « + Nouvelle collection » absent + border `--line` au lieu de `--line-2` | ACCEPTÉ | ✅ Corrigé : border `--line-2` + item en pied (filet `--line`) → input inline, Entrée = `POST /api/collections/` puis ajout du track, push optimiste + ✓ |
| 4 | [spec] `.mini-grid` gap uniforme au lieu de `--space-2`/`--space-4` | ACCEPTÉ | ✅ Corrigé |
| 5 | [visuel] Compteurs Découverte adjacents au titre au lieu d'alignés à droite | ACCEPTÉ | ✅ Corrigé : `.disc-head` → `space-between` |
| 6 | [spec] Seuils containers inclusifs (720/640) vs « < 720/640 » du pilote (719/639) | REJETÉ | Arbitré « tel quel » : convention inclusive du repo ENTIER (toutes les vues) ; coller au pilote créerait une divergence interne pire que l'écart (1px théorique) |
| 7 | [spec] Garde `is_admin` non visible dans la vue | CLOS | Confirmé : la garde est interne à `AdminCard.vue:2` (`v-if="auth.user?.is_admin"`) — pas de fuite |

**Hors périmètre (données, pas design)** : doublons constatés sur les captures — « Burnin' (Art Edit) » ×2 (doublons catalog, asymétrie de merge assumée), set Defected ×3 (doublons sets → chantier C8), « le track lui-même dans ses similaires » = faux positif (c'est l'*Extended Mix*, entrée catalog distincte et légitime).

**Conforme sans correction** (dixit la revue) : Rating absent, ordre vertical, Artwork (tailles/offsets/pastille lisible sur vraies covers), ScoreRing, PlatformLink (variantes, focus, TODO logos), TrackCard (états complets), lignes « Où on l'entend », troncatures, squelette, D3, dark/light/375px.
