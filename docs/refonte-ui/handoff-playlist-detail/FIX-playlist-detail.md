# FIX — Playlist Detail · Revue post-implémentation (round unique, 2026-07-17)

> Produit par Claude Design (canal captures + canal code @ master `ef8505f`).
> Verdict revue : « implémentation très fidèle — aucun écart bloquant. 5 écarts. »
> **Triage work manager (2026-07-17)** : chaque [spec] vérifié contre le code, le [visuel] #2 vérifié
> contre la prod, AVANT acceptation. Verdicts ci-dessous. Correctif : commit à venir (lot FIX).

## Écarts + verdicts

| # | Tag | Constaté | Attendu (brief) | Sévérité | **Verdict** |
|---|-----|----------|-----------------|----------|-------------|
| 1 | [spec] | `<640px : .detail-view { padding: var(--page-px-mobile) }` — le shorthand écrase le padding vertical (`--space-6`/`--space-10` → 16px) | § Responsive : « padding **horizontal** → `--page-px-mobile` » | mineur | **ACCEPTÉ** → `padding-inline`. Découverte au passage : TrackDetailView (p.1) a le MÊME shorthand (L1206-1209), non relevé par son propre FIX round → noté reliquat, s'alignera à son tour (le round FIX de la p.1 est clos) |
| 2 | [visuel] | Avatar « Alchemical Sisters » = pictogramme personne sur cercle gris (pas les initiales) | Sans artwork → initiales sur `--accent-soft` | mineur | **CLOS — non-écart** : vérifié en prod, l'artiste a `has_artwork=true` (id 3146) ; l'image stockée est l'artwork **générique Deezer** (pictogramme). Le code affiche fidèlement la donnée ; `initials()`/`.ins-av--ph` sont conformes et exercés dès que `has_artwork=false`. Qualité de donnée (détection des artworks Deezer par défaut), pas implémentation |
| 3 | [visuel] | Top artistes en items horizontaux (avatar 48 à gauche, texte à droite), 2/rangée | Pilote : tuiles verticales centrées 76px | mineur | **REJETÉ — conforme au brief** : le BRIEF versionné (« rangée wrap de 6 max : avatar rond 48 px + nom + count ») est le contrat et tolère les deux (reconnu par la revue elle-même) ; le pilote diverge du brief, le brief prime — même règle que convention repo vs pilote |
| 4 | [spec] | `.ins-bar[data-fam='autres'] i { background: var(--ink-3) }` | P7 : « autres » = **chroma 0** via la mécanique dot → `oklch(var(--tag-dot-l) 0 0)` | cosmétique | **ACCEPTÉ** (pattern `--ink-3` hérité de l'ancienne vue ; le canon P7 s'applique à la page refondue) |
| 5 | [spec] | `{{ g.pct }}%` → « 78% » collé | Typographie fr : « 78 % » (espace insécable étroite) | cosmétique | **ACCEPTÉ** → `&#8239;%` (U+202F) |

## Conforme (relevé par la revue, rien à corriger)

Hero P1/P2/P3/P9, bannière crawl P4, description P5, insights P6/P7 (formule teinte exacte),
tracks détectées + tri, extension TrackCard (additive, grille, `fmtMs`, `@click.stop`), états,
grille d'audit (tokens only, container queries, zéro Suivre, AdminCard gatée en bas).

## Limites du round (actées)

Captures 7/8/11 absentes → états vides/no-artwork/crawl jugés côté code uniquement (conformes).
Mobile fourni en light seulement. Round unique clos — pas de second passage.

## Suggestion hors FIX

Aucune.
