# FIX — Set Detail · Revue post-implémentation (round unique) — ARCHIVÉ + TRIAGE

> Livré par Claude Design le 2026-07-19 (revue de `master`@41e9315 + 7 captures).
> Triage du 2026-07-19 : chaque [spec] vérifié contre le code avant verdict.
> Verdicts : 5 ACCEPTÉS (correctifs livrés en mini-lot) · 2 CLOS (non-écarts) · 1 REJETÉ (arbitrage documenté).

## Tableau d'écarts annoté

| # | Tag | Constaté | Attendu (brief) | Sévérité | **Verdict & résolution** |
|---|-----|----------|-----------------|----------|--------------------------|
| 1 | [spec+visuel] | KEY absente sur rangée identifiée → cellule vide (`keyText` → `''`) | « — » `--ink-3` (États de rangée) | mineur | **ACCEPTÉ** — TrackCard : langage « donnée manquante » unifié (« — » atténué) pour KEY sur rangée normale. S'applique à tous les consommateurs (harmonisation Track/Playlist/Set — le trou dans la grille prédatait ce round) ; tests màj documentée |
| 2 | [spec+visuel] | Tiret BPM manquant rendu `--ink-2` | « — » `--ink-3` (pattern `.tk-dur--empty`) | cosmétique | **ACCEPTÉ** — même correctif que #1 (classe empty sur BPM manquant) |
| 3 | [spec] | `stroke-dasharray "0 C"` + `linecap round` → point à 12 h à 0 % | « 0 % → piste seule » | mineur | **ACCEPTÉ** — arc non rendu quand la fraction vaut 0 (les deux modes : l'artefact existait aussi en mode score, jamais exposé) |
| 4 | [spec] | `timecode_ms = 0` traité comme absent (garde `!timecodeMs` + `fmtMs(0)` → « — ») | 0:00 valide ; seul null → tiret | mineur | **ACCEPTÉ** — garde `== null` dans `makeTimestampUrl` ; colonne timecode formatée par `fmtCue` assoupli (`m:ss` sous l'heure, garde null) = **suggestion A intégrée**. Effet de bord assumé : les cues « Où on l'entend » de Track Detail passent de `0:21:34` à `21:34` (harmonisation au format spécifié) |
| 5 | [spec+visuel] | Cover hero sans ombre | `--shadow-md` (tableau Hero, S2) | cosmétique | **ACCEPTÉ** — porté par la page (`.hero-cover`), `Artwork` inchangé |
| 6 | [spec] | Pas de cap client sur `similarSets` | cap 8 | cosmétique | **CLOS (non-écart)** — le back cappe (défaut 8, `Query(le=24)`, `limit=8` service), vérifié en prod (8 exactement). Pas de slice défensif ajouté |
| 7 | [visuel] | Timecodes en lien sur un set « SOURCE TrackID » | « trackid → texte non cliquable » | mineur (à trancher) | **CLOS (non-écart code) + amendement doc** — vérifié en prod : le set des captures (`6892`) est `source=trackid` mais `source_url=soundcloud.com/…` → le lien horodaté est réel et fonctionnel. Le code sert l'INTENTION (« lien quand constructible ») ; c'est la lettre du brief qui supposait à tort qu'un set TrackID n'a jamais d'URL horodatable. Doc amendée (fiche §8) : le href se construit depuis le DOMAINE de `source_url`, jamais depuis `source` |
| 8 | [visuel] | Cellule IDENTIFIÉES : label au-dessus, ring+fraction dessous | Pilote : ring à gauche du bloc label+fraction | cosmétique | **REJETÉ (conforme)** — le brief texte ne fige pas l'arrangement ; le layout livré suit le pattern data-row (label au-dessus) des cellules voisines ET des pages Track/Playlist Detail. Cohérence inter-pages > fidélité pilote (doctrine des rounds précédents) |

## Suggestions hors FIX

- **A (fmtCue)** : ACCEPTÉE, fusionnée dans #4. `fmtCue` n'avait plus qu'un consommateur (Track Detail) et son format `h:mm:ss` permanent ne correspondait pas au format spécifié par le brief extension.
- **B (aria par défaut du mode %)** : notée, non retenue — la page passe déjà le libellé complet ; le défaut composant reste « N % ».

## Hors FIX mais embarqué dans le même mini-lot (décision deploy_verify)

Latence `GET /api/sets/{id}/similar` (~21 s sur un set à 24 seeds, froid comme chaud — pool par requête + scoring 24×98k) : cache Redis par `(set_id, viewer)` TTL 6 h + `SIMILAR_SETS_SEED_CAP` 24→12. Constaté au /deploy_verify du 2026-07-19, exclu du périmètre de la revue design.
