# FIX — Artist Detail · Revue design post-implémentation (round unique) — ARCHIVÉ AVEC VERDICTS

> Reçu le 2026-07-20 (canal visuel seul : 5 captures, artiste Dennis Ferrer ; pas d'accès code sur ce round).
> Triage work manager du 2026-07-20 : chaque écart vérifié contre le code ET contre le rendu réel en prod
> (pipeline headless authentifié Chrome CDP — captures + styles calculés mesurés sur diggy-music.fr).
> Correctifs livrés : c81b7e3 (axe du nom, pré-FIX) puis **01548f4** (cause racine + proches).

## Leçon majeure du round

Les écarts #1-#4 semblaient contredire le code (bloc sous-banner présent dans le chunk déployé, règles CSS
conformes au brief) — le contrôle statique les avait d'abord jugés « non confirmés ». La vérification VISUELLE
headless a prouvé que Claude Design avait raison : **une seule cause racine de layout** rendait invisible un DOM
pourtant complet. `grid-template-rows: 1fr 1fr` = `minmax(auto, 1fr)` : les covers 250×250 imposaient ~170px
par rangée → montage 339px dans un banner de 216px, et le grid **positionné** peignait par-dessus tout le bloc
sous-banner **en flux** (avatar, genres, actions, labels des stats). Le pilote ne montrait pas le bug car son
banner avait `overflow: hidden` (perdu à l'implémentation, déplacé sur `.hero` 380px).

## Verdicts

| # | Écart annoncé | Verdict | Résolution |
|---|---|---|---|
| 1 | Bloc sous-banner absent (avatar, genres, actions) | **ACCEPTÉ — symptôme cause racine** | 01548f4 : `.hb-tiles` rows `minmax(0,1fr)` + `.hero-banner` overflow hidden. Bloc visible en prod (vérifié au pixel) |
| 2 | Stats « nombres nus » chevauchant le montage | **ACCEPTÉ — symptôme cause racine** | Idem — labels CATALOG · IN LIB · SETS visibles (ils étaient rendus mais recouverts par les tuiles débordantes) |
| 3 | Nom centré sur bande sombre au milieu du banner | **ACCEPTÉ — symptôme cause racine** | Idem — le nom était au vrai bas du banner (216px), au milieu du montage VISUEL (339px) ; le « bandeau sombre » était le bord dur du scrim. Nom en bas-gauche sur l'axe du contenu (axe corrigé en amont, c81b7e3) |
| 4 | Tuiles à hauteurs irrégulières débordant du cadre | **ACCEPTÉ — symptôme cause racine** | Idem — montage 6×2 uniforme contraint aux 216px (vérifié au pixel) |
| 5 | Aperçu proches : 2e rangée coupée en plein milieu | **ACCEPTÉ** | 01548f4 : `.proches :deep(.shelf) { max-height:none; overflow:visible }` — le crop 1-rangée (180px) d'ExpandableShelf est neutralisé par override scoped ; 12 cartes entières vérifiées en prod |
| 6 | « Voir les 8 autres » en lien texte accent (attendu : `.btn--sm` « Afficher les N autres artistes ») | **REJETÉ page → TRANSVERSE** | Libellé + style codés en dur dans `ExpandableShelf` (composant partagé, aucune prop) — règle chantier : jamais modifié pour une page. Noté comme polish transverse futur d'ExpandableShelf |
| 7 | Compteur en pastille collé au titre (attendu : « 20 artistes » mono à droite) | **CLOS — arbitrage acté** | En-tête rendu par `RelBlock` via `ExpandableShelf` (composant inchangeable) — arbitrage déclaré au chantier, ce round de revue n'avait pas le prompt le listant |
| 8 | Fallback avatar « silhouette de personnage » (Danil Wright) | **CLOS non-écart page — DONNÉE** | Le fallback code est bien l'initiale. L'image stockée dans MinIO (`has_artwork=true`) EST un placeholder « silhouette » Deezer ingéré tel quel par `fetch_artist_artworks` (vérifié : artist-artworks/4248.jpg). → Reliquat backlog : filtrer les placeholders Deezer à l'ingestion (md5/URL connue, même logique que le placeholder TrackID prévu en C8.a) |

## Vérification post-correctif (2026-07-20, prod, headless authentifié)

Hero : montage 6×2 contraint, nom bas-gauche sur l'axe du contenu, avatar 120px débordant ring `--surface`,
StyleTag genre, actions (accent aperçu + Suivre + logo plateforme), stats labellisées — ✓ au pixel.
Proches : 12 cartes entières (2 rangées), `overflow:visible`/`max-height:none` calculés — ✓.
AdminCard : rend normalement en bas — ✓.
Non re-testés visuellement (données indisponibles sur l'artiste témoin) : aliases, montage pauvre/vide,
avatar hero sans artwork, mobile 375 — couverts par le brief + tests unitaires, à l'œil humain au fil de l'eau.
