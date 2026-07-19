# Handoff Claude Design — Artist Detail (D4, page 4)

> **Provenance** : projet Claude Design (claude.ai/projects), round unique, livré le **2026-07-20**
> (dossier `handoff-artist-detail` déposé par William), versionné tel quel le même jour.
> Prompt d'origine : `docs/refonte-ui/prompts/PROMPT-claude-design-artist-detail.md`.
> Fiche de cadrage source de vérité : `docs/refonte-ui/artist-detail.md` (§7 arbitrages pré-vol du 2026-07-20).

## Contenu

| Fichier | Rôle |
|---------|------|
| `BRIEF-artist-detail.md` | Handoff page : hero-bannière poli (code mort retiré, logos `<PlatformLink>`, stats repliées), tracks `<TrackCard>`, sets en grille `<SetCard>` (footer badge %), artistes proches `<ShelfCard>`, aliases, slots futurs Bio/Albums, états, responsive. Décisions DA A1-A9 |
| `pilote/Artist Detail (pilote).html` | Maquette interactive autonome (format export `.dc.html` : wrapper bundler Claude Design + React inline). Toggles dark/light + desktop/375 px, panneau Tweaks (états), nuanciers en bas |

## Notes de versionnage

- **Encodage** : fichiers livrés en UTF-8 propre (téléchargement direct, pas copier-coller) — aucune réparation nécessaire.
- `diggy-tokens.css` livré dans le dossier : identique au repo aux annotations `/* @kind other */` près (outillage Claude Design, valeurs byte-identiques) — non versionné ici pour éviter une copie divergente.
- Les hex hardcodés du pilote (`#faf9f5`, `#999`…) appartiennent au **wrapper bundler** de l'export (loader + overlay d'erreur), pas au design de la page — le CSS de la page est 100 % tokens (vérifié au check du 2026-07-20).
- Le brief mentionne `Artist Detail (pilote).dc.html` ; le fichier livré s'appelle `Artist Detail (pilote).html` — même artefact.

## Conformité (check du 2026-07-20)

Décisions figées de la fiche : toutes respectées — structure verticale conforme, code mort non ressuscité (real_name · country, SoundCloud), Rating moy. absent, artistes proches = avatar + nom seulement (pas de score/« pourquoi »), slots Bio/Albums en repères non livrables, Admin hors design (gate `is_admin` déjà en prod). Zéro donnée inventée hors contrats `ArtistDetailOut` (+ champs ✦ lot back `ArtistSetOut.artists[]`/`duration_ms`) et `connections`. Compat composants vérifiée : `PlatformLink` a déjà `size="md"` (38 px) et les entrées deezer/trackid dans sa map ; `ShelfCard variant="round"` + `ExpandableShelf` (aperçu 12) déjà consommés par la vue actuelle ; `SetCard` consommée telle quelle (slot `#footer`) ; `dv-back` = pattern existant (Track/Playlist/Set Detail). **Aucun composant créé, aucune extension** — conforme à l'attendu « zéro extension » du prompt.

Évolutions légitimes issues du round (latitude donnée par le prompt) :
- **A2** StatStrip repliée dans le hero en data-row mono (aligné Track/Playlist/Set Detail) ;
- **A3** montage pauvre (1-11 covers) → tuiles **cyclées** ; catalog vide → bande **placeholder rayé** sous scrim conservé (pas de faux décor) ;
- **A4** avatar : ring 3 px `--surface` (au lieu du 4 px `--bg` actuel) ; < 640 px en flux à 72 px (comportement actuel conservé) ;
- **A5** footer `<SetCard>` = **badge sobre** « NN % identifiées » (pas de `<ScoreRing mode="pct">` — discipline accent en grille ; le ring reste disponible si le besoin émerge) ;
- **A7** artistes des `<SetCard>` joints par « , » (spec canonique) — le séparateur « b2b » reste un traitement du hero de Set Detail ; `role` d'import jamais affiché (même règle que S5) ;
- État « Artiste introuvable » enrichi d'un bouton « Retour aux artistes » ;
- Grille Sets : 4 colonnes → 3 (< 720) → 2 (< 640).

Ces fichiers sont la référence d'implémentation du chantier ; en cas de contradiction, la fiche `artist-detail.md` prime.
