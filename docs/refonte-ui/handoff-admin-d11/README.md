# Handoff — Admin `/admin` · chantier D11 (reskin de la console entière)

Provenance : projet **Claude Design** (livraison 2026-08-30), sur la base de [`PROMPT-claude-design-admin-D11.md`](../prompts/PROMPT-claude-design-admin-D11.md) + fiche [`admin.md`](../admin.md) **§8** (prime pour D11).

## Fichiers

| Fichier | Rôle |
|---|---|
| `BRIEF-admin-D11.md` | **Contrat d'implémentation** (source de vérité du chantier). Réencodé UTF-8 propre à la réception. |
| `Admin-D11-pilote.html` | Maquette interactive (6 onglets, régimes de job, reset danger, splitter). **Référence visuelle uniquement** — bâtie en React + Google Fonts CDN ; on implémente en Vue d'après le BRIEF, PAS d'après ce code. Déposée par William (fichier lourd). |

## Portée livrée (rappel)

Reskin du **contenu desktop des 5 onglets** non-designés (Artistes/Sets/Genres/Enrichissement/Observabilité) **+** Monitoring (archétype F) **+** harmonisation de l'Aperçu — soit **toute la console** hormis le chrome de la barre d'onglets. 6 archétypes A→F + l'Aperçu harmonisé (D20).

## Décisions issues de la latitude / des rounds (légitimes, PAS des anomalies)

- **D1 — socle CSS admin partagé `.at-*`** pour les 4 tables (admin-local, un seul fichier `assets/admin-table.css`). Latitude explicitement accordée §8.5. Rejette correctement `TrackTable` (track-spécifique/virtualisé) **et** l'extension de `list-table.css` (en prod sur Sets/Watchlist).
- **D4 — panneaux d'action groupés en UNE région** (vs 4 cartes). Latitude densité accordée. Variante 4 cartes livrée en Tweaks, non retenue.
- **D5 — filtres segmentés SANS accent** (sélection par relief/pastille surélevée). Décision DA cohérente avec la discipline d'accent ; `SegmentedFilter` non modifié.
- **D19 — archétype C paginé, 10 groupes/page** (nouveau) ; pas de hauteur max / scroll interne. Bien argumenté.
- **D20 — Aperçu = harmonisation seule** : composition/ordre/libellés/régimes de D4 intouchés ; 5 alignements (icônes D2, nombres de contexte mono+groupés, slot de compteur centré, carte à jour enfoncée `--bg`, **régime « inconnu »** pour une métrique `null`) + 12ᵉ carte `bpm.pending`. Absorbe FIX-admin V1/V3/V4 + « DLQ à null ».
- **Absorption de FIX-admin.md** (V1-V7, S1) sur les surfaces du périmètre — pas de round séparé. Légitime.

## ⚠️ Écart à corriger à l'implémentation (NON un round Claude Design — mécanique)

**D22 — palette de séries des courbes.** Le BRIEF réinvente une palette à partir des hues de piliers de genre (`oklch(L C var(--hue-techno))`, avec **L/C en dur par thème**) et de deux opacités pour la paire total/à-traiter. **Or `diggy-tokens.css` contient déjà une palette de charts dédiée**, CVD-validée et theme-flippante, que l'`AdminMonitoring` actuel consomme déjà :

| Série | Token à utiliser (existe) | Ce que propose le BRIEF (à écarter) |
|---|---|---|
| Deezer total / à traiter | `--chart-deezer-soft` / `--chart-deezer` | `oklch(… var(--accent-h))` ×2 opacités |
| Beatport total / à traiter | `--chart-beatport-soft` / `--chart-beatport` | `oklch(… var(--pos-h))` ×2 opacités |
| Embeddings | `--chart-embeddings` (cyan 230) | `var(--hue-techno)` |
| BPM | `--chart-bpm` (ambre 60) | `var(--hue-house)` (72) |
| Albums (covers/méta) | `--chart-albums` (magenta 330) | `var(--hue-trance)` |
| Sets non fiables | `--chart-sets` (rose 20) | — |
| Grille / axe | `--chart-grid` / `--chart-axis` | `--line` / `--ink-3` |

**Instruction pour le lot Monitoring** : garder le mapping `--chart-*` existant (déjà en place dans `AdminMonitoring.vue`, cf. lignes 95/292-299/458-479), NE PAS introduire les `--mon-s*` de la maquette. Sémantique de la paire : **couleur pleine = actionnable, variante `-soft` = total/parqué** (documentée dans les tokens), donc ligne « à traiter » = `--chart-deezer`, aire/ligne « total » = `--chart-deezer-soft`. Ça respecte l'exigence « 100 % tokens » (les L/C en dur du BRIEF ne la respectent PAS) **et** l'intention DA de D22 (une teinte par source, total = variante atténuée de la même teinte). Le reste de l'archétype F (blocs, tuiles, sparklines, gouttière d'axe en CSS, texte en HTML positionné, table au socle `.at-*`) est conforme et conservé.

## Conformité (Phase 2)

✅ Décisions figées §8.4 respectées : purge emoji → jeu SVG (D2) · container-queries 859px + 3 trous mobiles comblés (D18) · discipline d'accent (D5) · `require_admin` sans état invité · logique/endpoints/colonnes inchangés · Aperçu+Monitoring traités selon le périmètre élargi (D20/D21). ✅ Aucune donnée inventée hors `GET /api/admin/backlog` / `/monitoring`. ✅ Aucun composant transverse Vue créé ; `SegmentedFilter`/`list-table.css`/`TrackTable` non modifiés.

**Verdict : GO**, avec la correction D22 (ci-dessus) portée comme instruction du lot Monitoring — pas de retour Claude Design nécessaire (elle préserve le design et n'ouvre aucune question DA).
