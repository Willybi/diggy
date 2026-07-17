# Diggy — Design System · v1 « Wildflower »

Diggy est une application web personnelle de **catalogage musical pour workflow DJ** : bibliothèque de tracks, sets, artistes, genres. Interface dense de type outil de travail — tables, cartes, badges, navigation latérale. Une seule surface produit (l'app web).

## Sources

- `uploads/diggy-tokens.css` — **source de vérité** de toutes les valeurs (couleurs oklch + override `[data-theme='dark']` complet, spacing `--space-*`, font-sizes `--fs-*`, radii `--r-*`, ombres, tokens de composant). Copié verbatim en `tokens/diggy-tokens.css`.
- `uploads/design-decisions.md` — autorité sur l'**intention** derrière les tokens (règles de snapping, scope densité, règle iOS 16px, liste blanche des littéraux px).
- `uploads/buttons.css`, `uploads/page.css` — classes CSS partagées réelles du codebase (copiées en `styles/`).
- `uploads/design-system-light-2026-07-08.png` / `-dark-…` — captures de la page de référence `/design-system` (illustratives ; en cas de divergence, le CSS gagne).

Aucune valeur n'a été inventée ; en cas de doute, se référer aux deux premiers fichiers.

## Thèmes & densité

- **Thème** : `data-theme="dark"` sur `<html>` ou `<body>` ; light par défaut (`:root`), forçable localement via `data-theme="light"`.
- **Densité** : `data-density="compact" | "comfy"` (défaut normal) pilote `--pad` (padding de contenu répétitif) et `--row-h` (hauteur de ligne de table). Scope de `--pad` : surfaces de contenu répétitif uniquement (tables, listes de résultats, cards de catalogue). Navigation, modals, PlayerBar, détail hors-table = spacing fixe `--space-*`.

## CONTENT FUNDAMENTALS

- **Langue** : français, avec vocabulaire métier anglais non traduit (track, set, in lib, watchlist, hover).
- **Ton** : outil de travail, factuel, télégraphique. Pas de marketing, pas d'exclamation, pas d'emoji dans la copy (le seul glyphe : ✓ dans le badge « In lib »).
- **Casse** : Sentence case partout (« Titre de page », « Titre de carte »). Micro-labels et clés techniques en **UPPERCASE mono** (`--fs-nano` / `--fs-label`) : `DEEZER`, `TIDAL`, `SPOTIFY`, en-têtes de table.
- **Chiffres** : denses et omniprésents (compteurs « 1 234 éléments », BPM, notes « 7.5 /10 ») — rendus en mono quand tabulaires.
- **Exemples** : sous-titre de page = compteur factuel (« 1 234 éléments ») ; documentation interne précise et normative (« Tout autre usage est une erreur. »).

## VISUAL FOUNDATIONS

- **Couleur** : neutres chauds — ivoire chaud en light (`--bg` oklch 0.974 h92), bleu-nuit en dark (h262). Accent unique **mauve Wildflower** (hue 328) piloté par `--accent-h/l/c` ; duo positif « prairie » (hue 138, in-lib/like), négatif terracotta (hue 28), warning ambre (hue 70). Tout est oklch ; les variantes dérivent des composantes hue/L/C — ne jamais introduire d'hex.
- **Piliers de genre** : 6 hues fixes (House 72, Techno 242, Trance 292, DnB 162, Hardcore 28, Hard Dance 338) + « Autres » gris (chroma 0). La profondeur taxonomique baisse le **chroma** du chip, jamais le hue : fond `chroma × (1 − 0.17·d)`, dot `L + 0.04·d`, `chroma × (1 − 0.19·d)`.
- **Type** : Space Grotesk (UI) + JetBrains Mono (clés, badges plateforme, chiffres). Échelle `--fs-*` avec tokens de **rôle** : `--fs-table` 14.5px / `--fs-table-sm` 12.5px RÉSERVÉS aux tables ; `--fs-input` 16px minimum sur tout contrôle de formulaire (iOS zoome au focus en dessous) ; `--fs-nano` 9px badges uppercase mono ; `--fs-label` 10.5px en-têtes de table ; `--fs-title` 15px titres de carte/section ; `--fs-lg` 22px titres de vue. Trois `clamp()` hors échelle autorisés (titres hero responsives).
- **Spacing** : grille hybride — pas de 2px jusqu'à 12px, pas de 4px au-delà (`--space-05`→`--space-15x`). 14px n'existe pas : 16px par défaut, 12px en contexte dense.
- **Radii** : 6 / 9 / 13 / 18 / 24 px + pill. Boutons `--r-sm` (9px), cartes `--r-md`/`--r-lg`, chips pill.
- **Ombres** : trois niveaux chauds et discrets (`--shadow-sm/md/lg`), alpha faible en light, ombres noires renforcées en dark. Pas de bordures colorées ; les cartes = `--surface` + `1px solid var(--line)` + ombre légère.
- **Fonds** : couleurs pleines, pas de gradients décoratifs. Les seuls gradients : scrims fonctionnels sur image (`--genre-tile-scrim`, hero scrim composé avec alpha au point d'usage) et fallbacks de cartes sans cover (`--fb-*` 2 stops, `--ct-*` teinte de corps de carte via `--th`).
- **Interaction** : hover = changement de fond/bordure (btn : `--surface-2` + ink plus foncé ; accent : `--accent-hover`), transitions 0.12s sur background/color/border-color. Pas de scale, pas de bounce. Rangée en lecture : tint `--accent-wash` ; rangée likée : `--pos-wash` (repos) / `--pos-wash-2` (hover).
- **Overlays** : invariants toujours sombres quel que soit le thème (`--overlay-modal`, `--overlay-soft`, `--overlay-text`).
- **Layout** : sidebar 232px, page max 1400px, détail max 1080px, padding horizontal de page 30px (16px mobile), bottom-nav mobile 56px, cibles tactiles ≥ 44px.

## ICONOGRAPHY

Aucun fichier d'icône ni logo fourni. Le codebase utilise des **SVG inline** (référence `.btn svg { width/height: 15px }` et le triangle play optiquement centré dans HubView) — set exact non fourni. Pas d'icon-font, pas d'emoji ; le glyphe unicode ✓ sert d'icône dans le badge « In lib ». Le kit UI reste volontairement sans icônes plutôt que d'en dessiner ; si des icônes deviennent nécessaires, utiliser [Lucide](https://lucide.dev) (stroke fin, 15px dans les boutons) en substitution flaguée, et fournir les SVG réels pour les remplacer. **Pas de logo** : le nom « Diggy » est rendu en Space Grotesk 700 partout où une marque apparaîtrait.

## Composants

Inventaire limité à ce que les sources définissent (buttons.css, page.css, screenshots `/design-system` §6, tokens de composant) :

- `components/buttons/Button` — `.btn` + variantes `accent`, `ghost-accent`, `sm`, `danger`, `disabled`.
- `components/badges/Badge` — badges d'état (`✓ In lib`, `Not in lib`), plateformes uppercase mono (`DEEZER`…), note `7.5 /10`.
- `components/tags/StyleTag` — chip pill de pilier de genre (hue par pilier, chroma décroissant avec la profondeur, « autres » gris).
- `components/page/PageHead` — `.page-head` : titre de vue `--fs-lg` + compteur.
- `components/table/TrackTable` — table dense pilotée par `--row-h`/`--pad`/`--fs-table`.

**Non recréés faute de code source** : GenreCard, ArtistCard, GenreTile, PlayerBar, SidebarNav, BottomNav, modals — leurs tokens existent (`--ct-*`, `--fb-*`, `--genre-tile-*`, `--hero-scrim-*`) mais pas leur markup ; le kit UI en donne une lecture prudente, à valider.

## Index

- `styles.css` — entrée globale (@imports uniquement)
- `tokens/` — `diggy-tokens.css` (verbatim), `fonts.css`
- `styles/` — `base.css`, `buttons.css`, `page.css` (copiés du codebase)
- `guidelines/` — cartes specimen (couleurs, type, spacing, radii, ombres, densité)
- `components/{buttons,badges,tags,page,table}/` — composants React + cartes
- `ui_kits/diggy/` — écran catalogue interactif
- `SKILL.md` — guide agent
