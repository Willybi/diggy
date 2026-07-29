# Handoff — Genres (liste) `/genres` (D6 p.7)

**Provenance** : Claude Design (projet claude.ai), livré 2026-07-29. Prompt source : [`../prompts/PROMPT-claude-design-genres-list.md`](../prompts/PROMPT-claude-design-genres-list.md). Fiche de cadrage : [`../genres-list.md`](../genres-list.md) (bloc « Précisions pré-vol 2026-07-28 » prime).

## Contenu livré
- `BRIEF-genres-list.md` — handoff de la page (versionné ici, encodage vérifié).
- `Genres (pilote).html` — maquette interactive **non versionnée** (mockup React+CDN lourd, reste dans `~/Downloads/livraison-genres-list/` chez William). Toggles thème/viewport + panneau Tweaks (scénarios + arbitrages `statsLayout`/`grilleMobile`).
- `diggy-tokens.css` — copie fournie, **identique au repo** (aucune dérive, vérifié).

## Check de conformité — PASS

**Décisions FIGÉES respectées** : anatomie card gardée (G6/G7/G8/G9), badge in-lib overlay retiré + coin haut-gauche vide (G2), in-lib en stat « En bib » `--pos-ink`/« — » (G3), **aucun %/mini-barre** (G4, respecte l'arbitrage pré-vol), SegFilter + « En bib » (G5), admin strip gaté `is_admin` (G11), FamilyChips (G12), play (G9), infinite scroll, clic → `/style/:name` (G15), FR, pas d'état invité.

**Aucune donnée inventée hors API** : champs consommés = `name/pillar/depth/trackCount/artistCount/bpmLo/bpmHi/inLibCount/artworks[]/artists[]` (tous au schéma) ; `sort=tracks|alpha|lib`. Tokens tous réels (13/13 vérifiés). CSP : refs externes uniquement dans le mockup (harnais React), le BRIEF-spec est 100 % tokenisé.

## Évolutions légitimes issues de la latitude DA (à noter, PAS des anomalies)

1. **G1 — BPM sort de la ligne de stats** vers une **ligne de signature** (`HOUSE · 93–136 BPM`) sous le nom ; la ligne de stats reste à **3 comptes homogènes** `Tracks · Artistes · En bib`. C'est l'**option (b)** explicitement offerte en latitude (fiche §5 : « si 4 stats serrent, le BPM remonte près du pilier »). Bien argumenté (nature intervalle vs comptes, largeur mono, valeur métier DJ). Variante « 4 stats » disponible dans les Tweaks du pilote.
2. **G8 — Avis hover-reveal PAR DÉFAUT mais bouton actif ÉPINGLÉ** quand un avis est posé (au lieu de hover-only strict actuel). Cohérent transverse « un contrôle qui porte un état ne peut être hover-only » ; nuance ici : l'état est déjà porté par la card (halo/estompe), donc seul le bouton concerné s'épingle, l'autre reste hover. **Faisable en `:deep()` scopé** sur `.ld[data-state=…] .ld-btn.…` sans modifier `LikeDislike`.
3. **G13/G14 — Grille jamais 1 colonne** (2 col fixes < 640, palier intermédiaire 216px car card paysage) + **container queries par card** (seuils 243/219, stats en 2 lignes sous 219 avec « En bib » sur sa propre ligne). Reprise assumée de l'arbitrage `ArtistCard` A12/A13 (diverge du code actuel qui passait à 1 col < 520). Dans la latitude « responsive » du prompt.
4. **G6 — Raffinements art** : scrim allégé en haut / renforcé en bas (lisibilité covers + avatars), tuiles placeholder **teintées pilier** (genre sans covers reste identifiable). Latitude finitions.
5. **G11 — Repli mobile admin strip corrigé** (texte pleine largeur + bouton dessous). Fix du défaut constaté.
6. **Empty states facettes Liked/Disliked** enrichis (pastille colorée + bouton retour + pédagogie de l'avis), sur le modèle de l'empty « Suivis » de `/artists`.

## Lot back induit (léger, aucune migration)
`/api/genres` : pattern `^(tracks|alpha)$` → `^(tracks|alpha|lib)$` + branche `elif sort == "lib"` dans `list_genres` (tri `-in_lib_count`, tie-break `-track_count`, `name`). `in_lib_count` déjà calculé au SQL ; tri déjà en Python sur le `fetchall` complet.
