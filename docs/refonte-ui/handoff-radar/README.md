# Handoff Claude Design — Radar (D6, nouvelle page)

> **Provenance** : projet Claude Design (claude.ai/projects), round unique, livré le **2026-07-22**
> (dossier `livraison-radar` déposé par William), versionné le même jour.
> Prompt d'origine : `docs/refonte-ui/prompts/PROMPT-claude-design-radar.md`.
> Fiche de cadrage source de vérité : `docs/refonte-ui/radar.md` (dont §7 « Décisions Phase 0 » du 2026-07-22).

## Contenu

| Fichier | Rôle |
|---------|------|
| `BRIEF-radar.md` | Handoff page : head (titre + compteur bi-score, menu « + » imports RETIRÉ), rappel barre de filtres (réutilisée d'Explorer), **anatomie de la ligne bi-score** (2 colonnes `<ScoreRing>` Tendance/Pour toi), colonne active surlignée (bande verticale `--accent-wash`), état « — » muet, accent velocity ▲, cold-start (Pour toi vide + invite), états de rangée/page, column-drop 4 paliers préservant les 2 scores jusqu'au 375 px, drawer mobile. Décisions DA R1-R9 |
| `pilote/Radar (pilote).html` | Maquette interactive (format export artifact : wrapper bundler Claude Design + React via unpkg + fontes Google — **nécessite le réseau** pour s'ouvrir). Toggles dark/light + desktop/375 px, panneau Tweaks (scénarios `tri tendance`/`tri pour toi`/`filtres actifs`/`cold-start`/`aucun résultat`/`chargement` + densité), tri et filtrage réellement appliqués aux 20 sons démo |

## Notes de versionnage

- **Encodage** : fichiers livrés en UTF-8 propre (téléchargement direct, pas copier-coller) — aucune réparation nécessaire.
- `diggy-tokens.css` non versionné ici (copie de travail Claude Design — éviter une divergence).
- Comme pour Explorer, les refs externes du pilote (unpkg React, Google Fonts) et les hex hardcodés appartiennent au **wrapper bundler** de l'export, pas au design : le CSS de la page est tokens. Le pilote n'est pas autonome hors-ligne ; les BRIEFs restent la référence d'implémentation. L'archive ZIP unique demandée n'a pas été produite (dossier de fichiers — transfert OK).
- **Rendu du pilote vérifié en headless le 2026-07-22** (`C:\tmp\captures-radar\pilote-01-default.png` desktop dark, `pilote-02-desktop-light.png`, `pilote-03-mobile-375-light.png`) : bi-score + bande de colonne active + « — » + ▲ velocity + #rank + in-lib + liked/disliked conformes ; **claim responsive validée** — à 375 px Style/BPM/Key tombent mais **les 2 scores survivent** (Play · Track · Tendance · Pour toi · Avis).

## Conformité (check du 2026-07-22)

Décisions figées (fiche + §7 Phase 0) : **toutes respectées**. Colonnes exactes Play · Track (`<Artwork>` + in-lib + titre + #rank + artistes cliquables) · Style (`StyleTag`) · BPM · Key · **Tendance** · **Pour toi** · Avis — **pas de colonne Durée**, **Rating absent partout**. Deux scores en `<ScoreRing size="sm">`, note `/10` relative à leur colonne, **« — » muet** pour score absent (union bornée = beaucoup de lignes mono-score). **Tri défaut = Tendance TOUJOURS** (+ Pour toi/BPM/Récent, clic d'en-tête, colonne active surlignée). **Cold-start = état** (Pour toi vide + invite « Débloque Pour toi »), pas de page séparée. Windowing (rangée fixe + sticky header, pas de pagination), filtres façon Explorer synchronisés URL, like/dislike sans pondération Radar, libellés FR, pas d'état invité. **Aucun composant transverse créé** — `<ScoreRing>`/`<Artwork>`/famille filtres/`<StyleTag>` consommés tels quels, géométrie ScoreRing non redéfinie. Zéro donnée inventée hors surface endpoint bi-score.

Évolutions légitimes issues du round (latitude donnée par le prompt) — **✦ = impact à porter au lot 0 back** :
- **Menu « + » imports RETIRÉ** du head (Ajouter track / Importer XML) : spécifique Explorer, hors sens sur une surface reco. Décision DA saine, sans impact back.
- ✦ **Compteur de head bi-score** « 1 240 tendances · 100 pour toi » : l'endpoint doit exposer les **bornes de l'union** (nombre de tendances + nombre de recos), pas seulement `total`. Cold-start → « … · Pour toi en attente de tes likes ». (Le compteur live « N sons » = total filtré, comme Explorer.)
- ✦ **Accent velocity ▲** : le brief consomme `velocity` (float) et affiche ▲ quand « élevée » — **le seuil de « élevée » reste à définir** au lot (percentile serveur, ou booléen `is_rising` renvoyé par l'endpoint). Non bloquant, optionnel.
- **Colonne active = bande verticale continue** `--accent-wash` (en-tête + cellules), pas seulement l'en-tête surligné : élaboration DA de « colonne active surlignée ».
- **Column-drop 4 paliers** (1000/860/700/640) hérité d'Explorer, réordonné pour **préserver les 2 scores** (Style → Key → BPM tombent avant).
- **Reliquat assumé (hérité d'Explorer)** : < 640 px le sélecteur de tri est masqué en v1 (ordre par défaut) — « le tri vivra dans le drawer à terme ». Même reliquat que la refonte Explorer.

Ces fichiers sont la référence d'implémentation du chantier ; en cas de contradiction, la fiche `radar.md` prime.
