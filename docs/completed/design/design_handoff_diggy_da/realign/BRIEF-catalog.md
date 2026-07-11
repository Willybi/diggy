# Brief — Catalog (pilote réaligné)

> Maquette : `realign/Catalog (pilote).html` · Tokens : `realign/diggy-tokens.css`
> Cible Vue 3. La barre sombre en haut est un **outil de revue**, PAS dans le produit.

---

## Écarts prod → DA corrigés (le « pourquoi »)

1. **StyleTags incohérents** — la prod colore les genres Beatport bruts au petit bonheur.
   → **Règle** : la couleur vient de la **FAMILLE** (House/Techno/Trance), pas du genre.
   Les **non-genres** (`DJ Tools / Acape`, `Mainstage`, `Dance / Pop`, `Misc. Tracks`)
   tombent en tag **neutre `.misc`** (surface-2 + ink), jamais une couleur vive.
   → mapping = `GENRE_FAMILY` dans le `<script>` ; à terme centraliser dans `diggy-style-map.js`.
2. **In-lib mal lu** — était rendu comme une croix ✕ (= "supprimer"?).
   → **LibDot** : in = pastille pleine `--pos` + halo `--pos-soft` ; out = anneau pointillé neutre.
   Jamais l'accent pour le statut lib.
3. **Pas de responsive** → container-queries sur `.app` (voir plus bas).
4. **Pas de surface admin** → bloc nav admin "utility" détachable + role-gate.

## Layout

- Grille `232px | 1fr`. Sidebar `--surface`, bordure droite `--line`.
- `page-head` : H1 `--font-ui` 28px + sous-titre **mono** `5563 tracks · 600 in lib`.
  Outils à droite : search (debounce 250ms) + 3 chips toggle (Pas dans RB / Radar ≥2 / In lib).
- Table auto-layout. Header **mono uppercase** `--ink-3`, hover ligne `--surface-2`,
  ligne en lecture = `--accent-wash` + titre en `--accent-ink`.

## Colonnes & types (règle UI vs données)

| Col | Type | Token |
|---|---|---|
| Play | bouton rond, apparaît au hover | `--surface`/`--line-2`, actif `--accent-soft` |
| Track | artwork 38px + titre (ui) + artiste (`--ink-3`) | ellipsis sur les 2 lignes |
| Style | StyleTag (famille) | voir règle #1 |
| BPM / Key / Durée | **mono** | Key en `--accent-ink`, reste `--ink-2`, vide = `—` `--ink-3` |
| Rating | 5 étoiles, remplies = `--accent` | vide = `—` |
| Radar | ScorePill 0–10, **10 ticks** mono | `--accent-soft`/`--accent-ink` |
| In lib | LibDot | voir règle #2 |

## Admin (role-gated — décision D2)

- Section nav `.nav-admin` : séparée par bordure **tiretée** `--line-2`, items sur `--surface-2`,
  badge `ADM` mono. → signal visuel clair « zone utility ».
- **Si `user.role !== 'admin'` → toute la section n'est pas rendue** (pas juste masquée en CSS).
- Sur Catalog il n'y a pas de bloc admin inline ; ils arriveront sur les pages détail (Vague 3).

## Responsive (container-queries sur `.app`, pas media-queries viewport)

| Largeur conteneur | Adaptation |
|---|---|
| ≤ 1160px | colonne **Durée** tombe |
| ≤ 1010px | colonne **Rating** tombe |
| ≤ 900px  | sidebar → **rail 66px** (icônes seules, labels/compteurs masqués) |
| ≤ 760px  | colonne **Radar** tombe ; search passe pleine largeur |
| ≤ 620px  | colonne **Style** tombe ; paddings réduits |

→ ordre de chute = du moins au plus essentiel ; Track + Key + In-lib survivent toujours.

## États à implémenter

- **hover** ligne (surface-2) + bouton play révélé · **playing** (accent-wash).
- **empty** : "Aucun résultat" centré mono `--ink-3` quand search/chips ne renvoient rien.
- **loading** : skeleton rows (barres `--surface-2` shimmer) — à spécifier au besoin.

## À fournir par toi pour affiner

- Confirmer la liste exacte des **genres bruts** réellement présents en prod
  (pour compléter `GENRE_FAMILY` exhaustivement et ne laisser AUCUN genre tomber en Misc par erreur).
- Le **wording exact** des 3 chips de filtre en prod.
