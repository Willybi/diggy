# Prompt — Claude Design · Refonte Admin (`/admin`) — chantier D4-Admin + D7 fusionnés

> Envoyer ce prompt au projet Claude Design (claude.ai/projects).
> Joindre en fichiers :
> - `diggy-tokens.css` (source de vérité des tokens)
> - `docs/refonte-ui/admin.md` (fiche de cadrage — **lire §7 en priorité, elle prime sur §1-6**)
> - `docs/refonte-ui/TRANSVERSE.md` (décisions transverses — système d'icônes SVG, PlatformLink monochrome)
> - `docs/refonte-ui/prompts/PROMPT-claude-design-genres-list.md` (référence de FORMAT uniquement — contenu sans rapport, ne pas en reprendre les décisions)
> - Captures de la page ACTUELLE (`/admin`) : `01-admin-actuel-desktop-dark.png`, `02-admin-actuel-mobile-375.png` (jointes — voir plus bas)

---

## Contexte

Tu es le designer de **Diggy**, web app DJ (Vue 3, DA « Wildflower », dark par défaut, tokens centralisés, container queries). On refond l'UI page par page ; chaque page est cadrée dans une fiche figée et tu produis le **handoff purement design** qu'un agent applique ensuite.

**Cette page : `/admin`** (`AdminView.vue` + `components/admin/*`), une **console d'ops** réservée à l'admin (`require_admin`, un seul utilisateur : le créateur). C'est une **console d'administration dense**, pas une page produit — elle sert à lancer des jobs (enrichissement, crawl, sync) et à modérer des files (flags d'artistes/sets, mappings de genres).

⚠️ **Refonte CIBLÉE, pas un reskin complet.** Décision produit (fiche §7.2) : on garde l'esthétique ops-console actuelle des onglets existants ; **le seul écran vraiment « designé » est un nouvel onglet « Aperçu »**. Le reste du travail est de la **finition responsive mobile** sur des surfaces existantes. **Ne propose donc PAS** de refonte visuelle des 7 onglets, ni de hero, ni de grille de cartes façon pages produit : ce serait hors périmètre.

**Périmètre strict : design/UX.** Les données listées plus bas sont exhaustives — ne rien inventer au-delà.

## État actuel (ce qu'on garde)

`/admin` = un shell (`AdminView`) avec une **barre de 7 onglets**, chacun montant un composant :
`Artistes` · `Flags` (flags d'artistes) · `Sets` · `Genres` · `Crawl` · `Monitoring` · `Beatport`.
Chaque onglet = des **boutons pour lancer des jobs** + des tables de données/modération. Look : dense, tokenisé, tables, `--font-mono` pour les nombres. **On garde les 7 onglets tels quels dans leur contenu et leur esthétique.** L'onglet **Monitoring** (dashboard : graphes burn-down, débit, hit-rate, durées) est **conservé tel quel, hors de ton périmètre** — ne le re-designe pas.

## Décisions produit FIGÉES (fiche §7 — à respecter, pas à rediscuter)

1. **Nouvel onglet « Aperçu » en landing (1er onglet).** C'est le cœur de ce handoff — un **tableau de bord backlog orienté ACTION** : une **grille de cartes, une par pipeline**, chacune = un **compteur de travail en attente** + une **action rapide** (bouton déclenchant le job existant, ou lien vers l'onglet). Pipelines : **Beatport**, **Deezer**, **Artistes** (à lier + sans pochette), **Sets** (à recrawler + set-flags en attente), **Flags artistes**, **Genres** (non classées + mappings non mappés), **Crawl** (playlists dues + DLQ).
2. **Badges de compte sur les onglets** (ex. « Sets 158 », « Beatport 2607 ») : voir le pending **sans ouvrir** l'onglet. Mêmes données que l'Aperçu.
3. **Coexistence Aperçu / Monitoring.** L'Aperçu = « qu'est-ce que je dois traiter maintenant » (action, instantané). Monitoring (existant, gardé) = « comment ça évolue » (observation, historique). Ils cohabitent — **ne pas fusionner, ne pas re-designer Monitoring**.
4. **Métrique des cartes = travail ACTIONNABLE**, pas le backlog brut. Pour Beatport/Deezer : `pending = never_tried + due_retry` (ce que la passe de nuit prendrait réellement) ; `total_missing` (dont cooldown) et `abandoned` sont du **contexte secondaire** (petit, discret) — jamais le chiffre principal.
5. **L'état sain est un état à 0.** En régime normal, plusieurs cartes sont à **0** (rien à faire) — c'est le bon état, pas un vide raté. Une carte à 0 doit lire **« à jour ✓ »** (calme, positif), et les cartes avec du backlog doivent **ressortir**. Le tableau doit être **beau quand tout est à 0** autant que quand ça déborde. Prévois explicitement les deux rendus.
6. **Ordre** : Aperçu premier, puis les 7 onglets existants inchangés.
7. **Finition responsive mobile** (ex-chantier D7, absorbé) sur des surfaces existantes — **responsive uniquement, pas de refonte visuelle** :
   - **Barre d'onglets** : à 8 onglets (Aperçu + 7) elle **déborde** en largeur sur mobile. Spécifier le comportement (scroll horizontal ancré, ou wrap) + où logent les badges.
   - **Revue « Set-flags en attente »** (onglet Sets) : liste de cartes de paires à comparer (attach/reject) — aujourd'hui flex-only, à rendre lisible/tactile < 640px. **158 en attente en prod** = surface réellement utilisée.
   - **Tables Genres (mappings) et Crawl (logs, 7 colonnes)** : aujourd'hui simple scroll horizontal → spécifier une conversion **table → cartes empilées data-label** sur mobile.
   - **Référence responsive DÉJÀ EN PLACE à réutiliser/élever** (ne pas régresser) : `AdminFlags` convertit sa table en cartes empilées sous **859px** (container-query + libellés de données), boutons tactiles pleine largeur ; le bloc « Lier » d'`AdminArtists` empile ses colonnes sous **639px**. Ton pattern mobile doit s'**aligner sur ce palier 859px** et cette grammaire de cartes data-label.

## Ce que tu dois livrer

### 1. `BRIEF-admin.md` — le handoff

Même format que les briefs existants (tables de tokens, anatomie, états, décisions DA explicites). Doit couvrir :

- **Onglet « Aperçu »** — la pièce maîtresse :
  - **Anatomie d'une carte pipeline** : label du pipeline, **compteur principal** (le chiffre actionnable, `--font-mono`, gros), sous-texte de contexte optionnel (« sur 65 722 au total », « 14 abandonnées » — discret), **1 à 2 actions** (bouton primaire « action rapide » + éventuel lien « voir l'onglet »). Certains pipelines portent **deux compteurs** (ex. Artistes = « à lier » + « sans pochette » ; Sets = « à recrawler » + « flags en attente » ; Genres = « non classées » + « mappings non mappés ») → décide si c'est **une carte à deux métriques** ou **deux cartes** — tranche et justifie.
  - **État à 0 (« à jour ✓ »)** vs **état backlog** : traitement visuel distinct (couleur/accent/icône), hiérarchie qui fait ressortir ce qui déborde. Montre les deux.
  - **Grille** : container queries, responsive (pilote 375px), lisible d'un coup d'œil.
  - **Latitude DA** : c'est le seul écran où tu as de la liberté de composition — donne-lui une vraie identité (mais cohérente avec les tokens et l'esprit ops-console, pas une page marketing).
- **Barre d'onglets + badges** : anatomie du badge (nombre `--font-mono`, seuil « 0 → pas de badge » ou « badge neutre à 0 »), comportement responsive de la barre (8 onglets), état actif.
- **Finition responsive (mobile)** : specs table→cartes pour **Set-flags** (onglet Sets), **mappings Genres**, **logs Crawl**, + note sur les 4 sections sync d'`AdminArtists` (les rendre cohérentes avec le pattern). **Aligne tout sur le palier 859px + la grammaire data-label existante d'`AdminFlags`.** Pas de refonte du contenu — juste la mise en forme mobile.
- **États** : loading (utilitaire global `.state`), erreur de chargement du backlog, job « en cours » après clic sur une action rapide (le polling existe déjà côté app), badge à 0.
- **Hors périmètre à mentionner seulement** : Monitoring (gardé), le contenu desktop des onglets existants (inchangé), pas d'état invité (page toujours `require_admin`).

### 2. `Admin (pilote).html` — maquette interactive

Maquette HTML autonome consommant les tokens de `diggy-tokens.css` (zéro couleur hardcodée) :
- **l'onglet Aperçu complet** avec des données réalistes (utilise les valeurs prod de la section Données), **dans ses deux régimes** : « tout à 0 / à jour » ET « backlog chargé » (deux vues ou un toggle) ;
- **la barre des 8 onglets avec badges**, y compris son comportement mobile (montre l'état 375px) ;
- **les 3 patterns table→cartes mobiles** (Set-flags, mappings Genres, logs Crawl) en aperçu ;
- toggle **dark/light**, toggle **viewport desktop / 375px**.

### Livraison — IMPORTANT
**Fournis tous les livrables dans une SEULE archive `.zip` téléchargeable (un seul lien).** Sans cette consigne explicite l'archive n'est pas générée et le transfert devient manuel. L'archive contient `BRIEF-admin.md` + `Admin (pilote).html`.

**Pas de spec de composant transverse** : les cartes Aperçu et les badges sont **admin-locaux** (réutilisés nulle part ailleurs). N'invente pas de composant partagé.

## Données disponibles (exhaustif — ne rien inventer au-delà)

**Nouvel endpoint agrégé `GET /api/admin/backlog`** (créé pour ce chantier, alimente cartes Aperçu ET badges) :
```
{
  "beatport":     { "pending": int, "total_missing": int, "abandoned": int },
  "deezer":       { "pending": int, "total_missing": int, "abandoned": int },
  "artists":      { "to_link": int, "no_artwork": int },
  "sets":         { "recrawl": int, "flags_pending": int },
  "artist_flags": { "pending": int },
  "genres":       { "unclassified": int, "mappings_unmapped": int },
  "crawl":        { "playlists_due": int, "dlq": int }
}
```
`pending` (beatport/deezer) = travail actionnable (`never_tried + due_retry`) ; `total_missing` inclut le cooldown non-actionnable ; `abandoned` = renoncées après 3 essais.

**Valeurs prod réelles à utiliser dans la maquette** (snapshot 2026-08-06) — utilise-les pour le régime « backlog chargé » :
- beatport : pending **2607**, total_missing 65722, abandoned 14
- deezer : pending **0**, total_missing 29403, abandoned 78  ← pipeline « à jour » malgré un gros total_missing (tout en cooldown) : bon cas de test de ton état « 0 / à jour ✓ »
- artists : to_link **5**, no_artwork **2990**
- sets : recrawl **501**, flags_pending **158**
- artist_flags : pending **0**  ← autre carte « à jour ✓ »
- genres : unclassified (variable), mappings_unmapped **0**  ← « à jour ✓ »
- crawl : playlists_due (≤ 56), dlq (souvent 0)

**Actions rapides par carte** (bouton) — mapping indicatif vers les jobs existants : Beatport → lancer enrich Beatport ; Artistes → sync artworks / link Deezer ; Sets → recrawl / revue set-flags ; Genres → reclassify ; Flags/Crawl → renvoi vers l'onglet. Le câblage exact est côté implémentation ; toi, prévois juste **le slot d'1 action primaire** (+ éventuel lien secondaire vers l'onglet).

**Surfaces existantes à rendre responsive** (contenu inchangé, tu ne spécifies que le mobile) :
- **Set-flags** (onglet Sets) : cartes de paires — set A vs set B (titre, date, nb tracks, cover), signaux de similarité, boutons **Attacher** / **Rejeter**.
- **Mappings Genres** (table) : colonnes `nom brut` → `node taxonomie` (+ recherche inline), badge mappé/non mappé.
- **Logs Crawl** (table 7 col.) : `date` · `type` · `cible` · `source` · `statut` · `durée` · `stats`.
- **Sections sync AdminArtists** : rangées bouton + résultat (Sync artistes, Liaison Deezer batch, Artworks artistes, Artworks playlists).

## Design system — contraintes (rappel)

- **Tokens** : tout via `var(--...)` de `diggy-tokens.css`. Zéro couleur hardcodée.
- **Typo** : `--font-ui` (Space Grotesk) texte, `--font-mono` (JetBrains Mono) pour **tous les nombres** (compteurs, badges, durées, dates).
- **Icônes** : SVG **inline / data-URI**, aucun CDN (CSP). Monochrome `currentColor` (l'accent mauve est le seul signal coloré). Pas d'emoji.
- **Thèmes** : `[data-theme="dark"]` par défaut + light — la maquette supporte les deux.
- **Responsive** : container queries (`@container`), jamais `@media` sauf `position: fixed`. **Aligne le palier mobile sur 859px** (référence `AdminFlags` existante).
- **UI en français.**
- **Pas d'état invité** : page toujours `require_admin`.

## Récapitulatif des livrables (dans un seul `.zip`)

| Fichier | Contenu |
|---------|---------|
| `BRIEF-admin.md` | Handoff : onglet Aperçu (cartes pipeline, états 0/backlog), barre d'onglets + badges, finition responsive mobile (set-flags, tables Genres/Crawl), états, tokens |
| `Admin (pilote).html` | Maquette interactive : Aperçu (régimes à-jour / backlog), barre 8 onglets + badges, patterns mobiles, toggles thème/viewport |
