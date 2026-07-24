# Handoff — Sets (liste) `/sets` · Refonte D6

## Provenance
- **Fiche de cadrage** : [`../sets-list.md`](../sets-list.md) (✅ figé ; les « Précisions pré-vol 2026-07-23 » priment sur le corps d'origine).
- **Prompt Design** : [`../prompts/PROMPT-claude-design-sets-list.md`](../prompts/PROMPT-claude-design-sets-list.md).
- **Livré par Claude Design** (2026-07-24), reçu via `Downloads/livraison-sets-list/` :
  - `BRIEF-sets-list.md` — handoff page (versionné ici, encodage vérifié propre, aucun mojibake).
  - `pilote/Sets (pilote).html` — maquette interactive (toggles thème/viewport + scénarios démo).
- Captures de la page ACTUELLE (référence Design) : `C:\tmp\captures-sets-list\` (01 desktop dark · 02 desktop light · 03 mobile 375).

## Décisions produit (rappel — verrouillées à la fiche)
Tableau enrichi (pas de grille de cartes) · exclusion des sets 0 % identifié (sans toggle) · genre déduit (1–2 StyleTags) · **colonne Source retirée** (100 % `trackid` en base) · infinite scroll `usePaginatedList` + sort server-side · opinion = filtre SegFilter + `ids` (tri « Avis » retiré) · form Ajouter conservé · aucun composant transverse créé.

## Évolutions légitimes issues des rounds Claude Design (à retenir pour le chantier)
1. **Panneau Ajouter → MODAL** (S7) : Claude Design a transformé le formulaire inline actuel en **modal 2 onglets** (recentré desktop, **bottom-sheet `position: fixed`** mobile). Latitude accordée (rafraîchissement du panneau) — évolution assumée. Le **flux** (recherche TrackID + import par résultat · import URL) est conservé.
2. **Genre replié sous le titre < 860 px** (S1) : la colonne Genre desktop se replie en chips dans la cellule Set plutôt que de disparaître.
3. **Échelle de column-drop** 1000/860/700/640 (S1, responsive) définie pour le nouveau jeu de colonnes.
4. **Rangée `min-height`** (pas hauteur fixe, S8) : l'infinite scroll ici n'est **pas** virtualisé (≠ Explorer) → pas de contrainte de hauteur constante.

## Résolutions Phase 2 (à appliquer au chantier — écarts brief vs code)
1. **Colonne Tracks = `<ScoreRing mode="pct" size="md">`, PAS `<RingPct>`.** Le brief S3 (40 px · « N %  » **centré** · arc accent · espace fine insécable) décrit en réalité `<ScoreRing mode="pct">` (existant, livré au chantier Set Detail), pas `<RingPct>` (30 px, % **à côté** de l'anneau, coche à 100 %, tiers `--warn`). On consomme **`<ScoreRing mode="pct" size="md" :score="identified_tracks / total_tracks">`** → concrétise la migration « RingPct → géométrie ScoreRing » actée dans TRANSVERSE. Effet de bord bénéfique : le % étant **centré** dans l'anneau, le « masquage du libellé < 640 px » (S3) devient **inutile** (l'ensemble anneau+% reste compact). `identified_tracks` ≥ 1 → arc jamais nul.
2. **Artistes cliquables → besoin back.** Le brief (cellule Set) rend **chaque artiste cliquable → `/artist/:id`**, mais `GET /api/sets/` renvoie `artists: list[str]` (noms simples, sans id). → le **lot back** doit renvoyer `SetListItemOut.artists` en `[{id, name}]` (l'`artist_id` est dispo via `SetArtist`). Cohérent avec le reste de l'app (artistes cliquables partout). _Petit ajout de contrat au-delà de la fiche — signalé au verdict, William peut le couper au profit de noms simples._
3. **Méta des résultats de recherche Ajouter** (S7, onglet Rechercher) : le brief affiche « TrackID · durée · **N % identifié** » ; or un résultat de recherche TrackID (`TrackIDSearchResult`, **avant** import) n'a pas de « % identifié » (rien n'est encore résolu). → utiliser les champs réels dispos : **`channel` · `track_count` tracks · `created_on` (date)** (comme l'impl actuelle). Détail mineur du pilote.

## Vérifications faites
- **Tokens** : tous les tokens cités par le brief existent dans `diggy-tokens.css` (audit OK).
- **Couleurs hardcodées** : les seuls hex du pilote sont dans le **harness de bundler** Claude Design (`#__bundler_*`, `body`) — la CSS design réelle est 100 % tokens.
- **Données inventées** : aucune hors API sauf le « % identifié » du panneau Ajouter (point 3 ci-dessus).
