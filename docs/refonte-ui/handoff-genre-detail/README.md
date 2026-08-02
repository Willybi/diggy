# Handoff — Détail genre `/style/:genre` (D6, dernière page)

**Provenance** : Claude Design (projet claude.ai), livré 2026-08-02. Prompt source : [`../prompts/PROMPT-claude-design-genre-detail.md`](../prompts/PROMPT-claude-design-genre-detail.md). Fiche de cadrage : [`../genre-detail.md`](../genre-detail.md) (bloc « Pré-vol chantier 2026-08-02 » prime).

## Contenu livré
- `BRIEF-genre-detail.md` — handoff de la page (versionné ici, encodage vérifié, zéro mojibake).
- `Genre Detail (pilote).html` — maquette interactive **non versionnée** (364 KB, reste dans `~/Downloads/livraison-genre-detail/` chez William). Toggles Genre riche/pauvre + thème + viewport 375, panneau Tweaks (cas mosaïque 6/4/2/0, avatars 3/2/0, BPM absent, `is_admin`), nuancier en bas de page. NB : le BRIEF la cite `…(pilote).dc.html` — le fichier livré s'appelle `…(pilote).html` (cosmétique).
- `diggy-tokens.css` — copie fournie, **identique au repo** (diff vérifié, aucune dérive).

## Check de conformité — PASS (rendu pilote contrôlé par screenshot headless)

**Décisions FIGÉES respectées** : ordre vertical complet (hero → stats secondaires+actions → Artistes → Sets → Playlists → Tracks → Genres proches → **Admin en dernier**), hero immersif overlay (label pilier + titre + stats clés Tracks·Artistes·BPM + avatars + play), **StatStrip absorbée**, **« Tout filtrer dans Catalog » retiré non ré-alloué**, tracklist **`<TrackCard>` + avis slot `end`** (G9, arbitrage 2026-08-02), **contrôles simples restylés PAS la FilterBar Explorer** (G10), **glyph source playlists** (G8), Genres proches gardés, gate `is_admin` reconnu déjà en place, FR, pas d'état invité, **aucun composant transverse créé ni modifié**.

**Aucune donnée inventée hors API** : tous les champs consommés sont au schéma des 6 endpoints ; la ligne « N en bib » des cards Artistes utilise `inLibCount` **déjà renvoyé** par `/api/genres/artists/`. « — » (jamais « 0–0 ») pour le BPM absent. Tokens **25/25 vérifiés existants** dans `diggy-tokens.css`.

## Évolutions légitimes issues de la latitude DA (à noter, PAS des anomalies)

1. **G7 — Badge % des cards Sets déplacé** : pastille sur l'image avec seuils colorés 80/45 → **pied de carte** hairline « `NN %` de ce genre » mono neutre. Latitude explicite du prompt (« peut être raffiné ») ; aligne le footer `<SetCard>` d'Artist Detail ; le libellé « de ce genre » lève l'ambiguïté avec le « % identifiées » des autres pages ; les seuils colorés inventaient une lecture qualitative sur une valeur structurellement variable (20–96 %).
2. **G4 — Stats secondaires fusionnées avec la ligne d'actions** (En bib · Sets · Playlists à gauche, « Écouter un aperçu » + avis à droite) — remplace la StatStrip sans la réinventer ; « En bib » reprend le traitement de référence `--pos-ink`/« — ».
3. **G1/G2/G3 — Exécution du hero** : bande 340 px (288 < 640), 3 couches fixes (voile α 0.34 + teinte pilier + scrim vertical) pour un contraste prévisible dark ET light, titre en échelle fluide `cqw` clampé 2 lignes (**jamais d'ellipsis 1 ligne** — répond à la troncature constatée capture 03).
4. **G5 — Play hero en « verre »** (overlay-soft + blur) → hover accent : préserve « un seul `.btn--accent` par page ».
5. **G6 — 0 avatar → cluster absent** (pas de placeholder initiales, doublon de la shelf Artistes).
6. **G11 — Teinte pilier du corps de page BORNÉE** (dégradé 520 px puis `--bg` neutre) ; pilier « autres » = chroma 0 partout.
7. **Cards Artistes : ligne « N en bib »** ajoutée (donnée existante, cohérence traitement in-lib des cards agrégées).
8. **Empty recherche avec bouton « Réinitialiser »** (vide `q` + toggle En bib), en-tête conservé.
9. **Pagination** : `usePaginatedList` + sentinelle texte pulse (aligné sur l'arbitrage pré-vol — l'IntersectionObserver inline disparaît).

## Lots induits (déjà actés au pré-vol, aucune migration)
- **Back lot 0** : `artists[]` `{id,name}` (ordre position, via `catalog_artists`) sur `GET /api/genres/tracks/{name}` — le fallback plat `artist` reste.
- **Purge orphelins** : `GenreTrackRow`, `LibDot`, `StatStrip` supprimés (plus aucun consommateur).
