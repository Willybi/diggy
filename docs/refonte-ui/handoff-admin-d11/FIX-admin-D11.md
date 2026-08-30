# FIX — Admin D11 · revue design + triage work-manager

Revue Claude Design (round unique, 2026-08-31, captures prod `f57956a`). 6 écarts remontés, **tous CONFIRMÉS contre le code** au triage. Verdict revue : implémentation fidèle (socle .at-*, data-label hybride, scroll intérieur, discipline accent, segmenté sans mauve, pagination C, troncature 6, gouttière CSS + labels HTML — les 2 pièges signalés du brief évités).

## Triage (verdicts work-manager) → lot correctif unique

| # | Tag | Écart | Vérif code | Verdict | Fix retenu |
|---|---|---|---|---|---|
| V1 | visuel | `.btn--danger` sans état de repos → reset Beatport = neutre au repos | `buttons.css` .btn--danger uniquement au :hover (l.51-52) | **ACCEPTÉ** p1 | règle admin-locale (scoped) : repos `--neg-ink`/`--neg`, sans toucher buttons.css. Sur déclencheur + confirmation |
| S1 | spec | « Sets attachés »/« Flags » : badge = total mais fetch limit=50 client-paginé → au-delà de 50 inatteignable | endpoint set-flags supporte `offset` (admin.py:336) | **ACCEPTÉ** p2 | **option 2** : pagination SERVEUR (limit=10 + offset, 0 back — param existant), file complète |
| V2 | visuel | `niceCeil` pas 1/2/5/10 → 230k plafonne à 500k | TimeSeriesChart niceCeil (l.140) | **ACCEPTÉ** p2 | pas enrichis 1/1,5/2/2,5/3/4/5/10 |
| V3 | visuel | `Batch size` à l'opposé de son bouton, label inline | — | **ACCEPTÉ** p3 | aligner sur AdminGenres (champ dans le bloc d'action) |
| S2 | spec | `.at-table td` en `--ink-2` (brief B : `--ink`) | admin-table.css (l.87) | **ACCEPTÉ** p3 | td → `--ink` ; `.at-tech` garde `--ink-2` |
| V4 | visuel | `.dl-empty` encadré → lu comme input désactivé | AdminArtists (l.912) | **ACCEPTÉ** p3 | dé-encadrer (ligne nue) |
| V5 | visuel | `source` nulle = cellule vide (desktop) | — | **ACCEPTÉ** p4 | `.at-source:empty::before { content:'—' }` (préserve le `:empty` mobile — meilleur que le fix suggéré par la vue) |

Non vérifiable dans le round (files vides / jobs non déclenchés) : splitter E, lignes de résultat de job, already_running, error_message tronqué Crawl, recherche node inline — code relu conforme, aucun écart présumé.

Les 8 arbitrages d'implémentation actés (palette --chart-*, 12 glyphes, détache-groupe boucle, horodatage/conséquence non fabriqués, mappings non paginé, bouton ré-activable, antériorité D20 pts 3-4) n'ont PAS été rouverts par la revue — conformes.
