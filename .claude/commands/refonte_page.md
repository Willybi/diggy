---
description: Déroule le pipeline complet de refonte d'une page (fiche → Claude Design → chantier → deploy → revue design → clôture)
allowed-tools: Read, Glob, Grep, Write, Edit, AskUserQuestion, Bash(git log:*), Bash(git diff:*), Bash(git status:*), Bash(git fetch:*), Bash(npm run lint:*), Bash(npx vitest run:*), Bash(ssh diggy-vps:*), Bash(curl:*), Bash(node:*), Bash(mkdir:*)
argument-hint: [nom de la page, ex. playlist-detail]
---

Tu pilotes la refonte UI de la page suivante : **$ARGUMENTS**

Pipeline éprouvé sur Track Detail (D4 p.1, 2026-07-17) : tu orchestres, les agents codent (via /work_manager), Claude Design produit le design, moi (William) je fais les relais externes (envois à Claude Design, transmission des prompts agents, commits/push, checklist humaine). **Les captures d'écran, c'est TOI qui les produis** (décision 2026-07-20, chantier Artist Detail) : pipeline headless authentifié Chrome CDP + JWT de debug minté sur le VPS — recette complète dans la mémoire `verif-visuelle-headless`. Dépose-les dans `C:\tmp\captures-$ARGUMENTS\`, je n'ai plus qu'à les joindre. Chaque phase se termine par un point de contrôle explicite — tu n'enchaînes pas sans lui.

## Phase 0 — Cadrage & pré-vol (bloquant)

1. Lis `docs/refonte-ui/$ARGUMENTS.md` (la fiche de cadrage), `docs/refonte-ui/TRANSVERSE.md`, `docs/refonte-ui/INDEX.md`. Si la fiche n'existe pas ou n'est pas ✅ figée → STOP : on la produit d'abord ensemble selon la boucle de l'INDEX.
2. **Vérifie l'état RÉEL du code contre la fiche** — les « dettes » listées peuvent être obsolètes (leçon Track Detail : le gate `is_admin` d'AdminCard était déjà fait). Vérifie aussi quels composants transverses existent déjà dans `src/components/` (Artwork, TrackCard, ScoreRing, PlatformLink… créés au fil des pages) et lesquels manquent.
3. **Traque les incohérences internes de la fiche**, en particulier §5 (décisions) vs §6 (« Back : rien de neuf ») : si la page exige du back (champs jamais renvoyés, agrégats à calculer), liste précisément les besoins et fais-moi TRANCHER avant le prompt Design — le back devient alors un lot du chantier (leçon : fiche playlist-detail contradictoire détectée en amont).
4. Questions de périmètre restantes → AskUserQuestion. Aucune hypothèse silencieuse.

## Phase 1 — Prompt Claude Design

Rédige `docs/refonte-ui/prompts/PROMPT-claude-design-$ARGUMENTS.md`, sur le modèle de `PROMPT-claude-design-track-detail.md`. Obligatoire :
- décisions FIGÉES de la fiche verrouillées (« à respecter, pas à rediscuter ») ; la latitude DA explicite là où la fiche en laisse ;
- **données disponibles EXHAUSTIVES** (champs exacts des endpoints — « ne rien inventer au-delà ») ;
- livrables : `BRIEF-$ARGUMENTS.md` + spec autonome des composants transverses NOUVEAUX si la page en crée + maquette pilote HTML (toggles thème/viewport) ;
- **livraison : exiger EXPLICITEMENT une archive zip téléchargeable (un seul lien) contenant tous les livrables** — sans cette consigne Claude Design ne la génère pas et le transfert des fichiers devient manuel (leçon playlist-detail, 2026-07-17) ;
- contraintes DS : tokens only, container queries, CSP (SVG inline, zéro CDN), UI en français, pas d'état invité sur les pages internes ;
- pièces que je dois joindre : `diggy-tokens.css`, la fiche, TRANSVERSE.md, un brief récent en **référence de FORMAT uniquement** (avertir Claude Design que son contenu peut contredire les décisions actuelles) ;
- capture de la page ACTUELLE (recommandée quand on garde des éléments existants, ex. le hero-bannière Artist Detail) : **produis-la toi-même** en headless (desktop dark full au minimum, + mobile si le comportement étroit est à re-trancher) et dépose-la dans `C:\tmp\captures-$ARGUMENTS\`.

**STOP** : je l'envoie à Claude Design, je gère les rounds de retours, je te rapporte le handoff (fichiers ou texte collé).

## Phase 2 — Réception du handoff

1. Check de conformité : décisions figées respectées, aucune donnée inventée hors API. Les évolutions issues de mes rounds avec Claude Design sont légitimes — liste-les explicitement, ce ne sont pas des anomalies.
2. Versionne dans `docs/refonte-ui/handoff-$ARGUMENTS/` (briefs + README de provenance ; maquette lourde déposée par moi). **Répare l'encodage** : le copier-coller casse l'UTF-8 (Ã©, â€¦) — réécris les fichiers proprement.
3. **Mets à jour la fiche et TRANSVERSE** avec les décisions des rounds : la fiche RESTE la source de vérité. Reliquats assumés (placeholders, TODO) → table « Reliquats » de `docs/ROADMAP.md`.
4. Verdict GO/NO-GO argumenté avant de lancer le chantier.

## Phase 3 — Chantier (délègue à /work_manager)

Enchaîne sur le processus /work_manager avec ces règles spécifiques refonte :
- **composants partagés existants : JAMAIS modifiés pour une page** (ils servent d'autres vues) — un besoin local se règle par override `:deep()` scopé dans la vue (pattern hero Track Detail) ; les incohérences de composants partagés repérées (ex. LikeDislike 30px) se notent pour les pages suivantes, pas plus ;
- composants transverses NOUVEAUX = lot 1 séparé (avec tests Vitest + section vitrine DesignSystemView), page = lot 2, back éventuel = lot 0 avant tout ;
- lots séquentiels (pas de parallèle dans le même working tree) ; contrôle sur pièces : diff relu, tests ET lint rejoués indépendamment du compte rendu.

## Phase 4 — Deploy & vérification

1. Après mon commit : **vérifie `git status -sb` que la branche n'est pas `ahead`** avant de considérer le deploy parti (leçon : push oublié le 17/07).
2. /deploy_verify, avec les spécificités connues : le front est **code-splitté par vue** → vérifier le chunk de LA page (hash changé + marqueur textuel du nouveau code dedans), pas le bundle `index-*.js` ; `/api/catalog` et `/api/artists` exigent le **slash final** (307 sinon) ; artefacts curl dans le scratchpad, jamais dans le repo.
3. **Vérification VISUELLE obligatoire** : capture headless authentifiée de LA page en prod + coup d'œil au rendu — le check statique chunk+marqueurs valide que le code est LIVRÉ, pas qu'il REND (leçon Artist Detail 2026-07-20 : DOM complet et CSS conformes, page pourtant cassée par un débordement grid `minmax(auto,1fr)` peignant par-dessus le hero ; ni vitest ni la lecture du CSS ne peuvent l'attraper). En cas de doute sur un élément, mesurer `getBoundingClientRect`/`getComputedStyle` via CDP plutôt que déduire du code.
4. Checklist humaine ciblée sur les nouveautés de la page — je la valide.

## Phase 5 — Revue design post-implémentation (round UNIQUE, timeboxé)

Produis le prompt de revue pour Claude Design (modèle : celui de Track Detail) :
- canal captures : **TU produis le jeu de captures toi-même** (pipeline headless, mémoire `verif-visuelle-headless`) dans `C:\tmp\captures-$ARGUMENTS\`, numérotées et nommées (`01-desktop-dark-full.png`…). Jeu type : desktop dark full + zoom hero + desktop light full + zoom light + mobile 375 dark + les cas de DONNÉES de la page (entité riche, entité pauvre, états dépliés/lecture — choisis les entités via SQL read-only sur le VPS si besoin). Le prompt liste chaque fichier avec son contenu ;
- canal code : les fichiers EXACTS à relire sur GitHub, conformité à SES briefs uniquement — interdiction explicite de commenter l'architecture JS/les patterns Vue ; les placeholders assumés ne sont pas des écarts ; **déclare les arbitrages d'implémentation déjà actés** (ils reviennent sinon en faux écarts si le round tourne sans ton prompt sous les yeux) ;
- livrable : `FIX-$ARGUMENTS.md` unique, écarts tagués [visuel]/[spec] avec valeurs constatées/attendues.

**STOP** : j'envoie le prompt + tes captures, je te rapporte le FIX.

## Phase 6 — Triage du FIX + lot correctif

1. **Chaque [spec] se vérifie contre le code AVANT acceptation** — un écart annoncé n'est pas un écart confirmé. Cas connus : écart pré-existant à TOUT le repo → le canon s'applique à la page refondue seulement (les autres s'aligneront à leur tour) ; convention repo vs pilote (ex. seuils inclusifs 720/640) → la convention repo prime, arbitrage documenté.
2. Archive le FIX annoté de tes verdicts (ACCEPTÉ/REJETÉ/CLOS + résolution) dans `docs/refonte-ui/handoff-$ARGUMENTS/FIX-$ARGUMENTS.md`.
3. Mini-lot correctif via prompt agent (format /work_manager), contrôle sur pièces, commit. Deploy léger : pour du CSS pur, TA vérification visuelle headless suffit (capture avant/après si utile) ; sinon /deploy_verify ciblé.

## Phase 7 — Clôture

- /roadmap_update (statut du chantier parent + tâche de la page cochée avec date et commit).
- Mets à jour la mémoire projet (page livrée, composants créés, leçons nouvelles).
- Annonce la page suivante pressentie et ses préalables (incohérences de fiche, besoins back).
