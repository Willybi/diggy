# Brief — Artistes `/artists` v2 (pilote réaligné)

> Maquette : `realign/Artistes v2 (pilote).html` · Tokens : `realign/diggy-tokens.css` · Mapping : `realign/diggy-style-map.js`
> Cible Vue 3. La barre sombre en haut est un **outil de revue**, PAS dans le produit.
> ⚠️ On **abandonne la liste/table** actuelle (jugée trop impersonnelle). Nouvelle direction = **grille de cartes portrait**, dans l'esprit de la page Genres.

---

## Intention (décidé avec willi)

La liste actuelle est plate et froide : on n'y retrouve pas « l'essence » des artistes.
Nouvelle direction = **cartes portrait** centrées sur l'artiste :
- avatar grand et central dans une zone teintée **par famille musicale** (placeholder élégant tant que les vraies PP ne sont pas synchro) ;
- les **signaux clés visibles d'un coup d'œil** : rating, in-lib, liked ;
- chips famille + tri, **mêmes conventions que Genres** (cohérence cross-page).

Objectif = donner envie de cliquer sur un artiste, pas dérouler un tableau.

---

## 🛑 À FAIRE AVANT TOUT — check backend

**N'attaque pas le front avant d'avoir vérifié que la donnée existe.** Mets ces points en to-do, vérifie chacun, **signale ce qui manque** avant de planifier l'UI.

- [ ] **Endpoint liste artistes** — `GET /api/artists` renvoyant **par artiste** :
      `id`, `name`, `genres[]` (genres bruts à mapper côté front via `diggy-style-map.js`),
      `catalogCount` (tracks rattachées), `inLibCount` (tracks synchro Rekordbox, scopé user),
      `likedCount` (tracks likées dans Radar, scopé user), `rating` (nullable — feature roadmap),
      `imageUrl` (PP artiste, nullable). → existe ? à étendre ?
- [ ] **Pagination serveur** (cursor/offset + limit) pour le **scroll infini**, ET le **tri**, le **filtre famille** et la **recherche `q`** appliqués **côté serveur** (sinon pagination incohérente).
      Param : `?sort=catalog&family=House&q=&cursor=…&limit=24`.
- [ ] **Compteurs par famille** (badges des chips) — agrégat **indépendant de la pagination** (total réel par famille sur l'ensemble filtré). Idéalement en `meta` de la réponse.
- [ ] **Sémantique des deux compteurs user** (ne PAS les confondre — ce sont deux signaux distincts) :
      - **In Lib** = tracks de l'artiste **présentes dans la bib Rekordbox** de l'user (synchro).
      - **Liked** = tracks de l'artiste **likées dans Radar** (découverte). Indépendant de la bib.
- [ ] **Rating** = **feature roadmap, pas encore réelle**. L'API peut renvoyer `null` aujourd'hui →
      le front dégrade proprement (badge masqué, stat `—`). Ne pas bloquer le lot là-dessus.
- [ ] **PP artistes** — les photos sont-elles synchronisées et servables ? (cf. Vague 5 « sync artistes »).
      **Fallback prévu** : initiales sur fond teinté famille (déjà dans la maquette) — acceptable au lancement.
- [ ] **Mapping genre → famille** — partagé avec Genres ; tout genre non mappé tombe en **Misc** (neutre), jamais une couleur au pif.
- [ ] **Perf** — `catalogCount` / `inLibCount` / `likedCount` distincts sur toute la base peuvent coûter cher et grossiront. Prévoir agrégats cachés plutôt qu'un calcul live à chaque hit.

> Tant que ces points ne sont pas tranchés, ne « devine » pas le contrat d'API : remonte la liste à willi.

---

## Anatomie d'une carte (`.artist-card`)

| Zone | Contenu | Notes |
|---|---|---|
| **Artwork** (h ~132px) | zone teintée **par famille** (placeholder) ; pattern diagonal subtil + scrim bas | accueille la PP plein cadre quand dispo (`object-fit:cover`) |
| **Avatar** | rond 84px centré, bordure `--surface`, ombre portée | PP artiste si dispo, sinon **initiales** sur fond teinté famille |
| Badge **rating** | **haut-droite** : étoile `--accent` + valeur mono | `--surface`+`--line`+`--shadow-sm` ; **masqué si null** |
| Badge **in-lib** | **bas-gauche** : pastille `--pos` + `N en bib` | **masqué si 0** |
| **Play** | bouton rond `--accent`, **révélé au hover**, bas-droite | lance une preview rapide |
| **Nom** | `--font-ui` 15px semibold, ellipsis 1 ligne | |
| **Genres** | 2 StyleTags max | voir règle ci-dessous ⚠️ |
| **Stats** | 3 colonnes séparées par `--line` : **Catalog · In Lib · Liked** | valeurs **mono** ; Liked avec cœur `--pos` ; `—` si 0/null |

- Grille : `repeat(auto-fill, minmax(208px, 1fr))`, gap 16px.
- Hover carte : `translateY(-2px)` + `--shadow-md` + bordure `--line-2` ; avatar `scale(1.07)`.

## ⚠️ Genres affichés — choisir les 2 plus pertinents (PAS les 2 premiers)

Un artiste peut avoir **>2 genres**. La maquette tronque naïvement (`slice(0,2)` sur l'ordre du tableau) — **à ne PAS reproduire tel quel**.
Côté Vue : afficher **les 2 genres les plus représentatifs** de l'artiste, déterminés par une vraie pondération, p.ex. :
1. genre avec le **plus de tracks** de l'artiste, puis
2. 2e genre distinct le plus fréquent.
→ Idéalement l'API renvoie `genres[]` **déjà trié par poids décroissant** (nb de tracks). Sinon, trier côté front sur un `genreWeights`.
La **teinte de famille de la carte** suit le **genre principal** (le 1er après pondération).

## Discipline couleur (rappel conventions)

- **`--accent`** réservé : rating + sélection de contrôle (chip/segment actifs) + bouton play. Jamais en déco.
- **`--pos`** (vert) : in-lib **et** liked (les deux sont des signaux « positifs » user). Le cœur Liked et la pastille In-Lib partagent `--pos`.
- StyleTags : **toujours** via `diggy-style-map.js`. Familles bornées : House (violet) · Techno (fuschia) · Trance (rose) · Other (ambre) · Misc (neutre).
- Données (rating, compteurs) en **`--font-mono`** ; nom/labels en **`--font-ui`**.

## Recherche + tri

- **Search** (debounce ~250ms) sur le nom d'artiste. Sous-titre mono : `500 artistes` ; si filtre/recherche actif → `12 / 500 artistes`.
- **Tri** segmenté : **Catalog** (défaut, desc) · **Liked** (desc) · **Rating** (desc, nulls en bas) · **A–Z**.
  Appliqué **serveur** (pagination cohérente).
- Chip actif + segment de tri actif = `--accent-soft`/`--accent-ink`.

## Chips de filtre par famille

- Rang au-dessus de la grille : **`Tous · House · Techno · Trance · Autre`**, chacun avec **compteur mono** + pastille de couleur famille (sauf `Tous`).
- Un seul actif à la fois. Filtre **appliqué serveur** (voir check backend).

## Scroll infini (reveal progressif)

- Batch initial **~24** cartes, puis **IntersectionObserver** sur un **sentinel** bas de grille (`rootMargin` ~360px pour préfetch).
- Sentinel = ligne centrée mono `--ink-3` + spinner `--accent` (désactivé en `prefers-reduced-motion`), masqué quand tout est chargé.
- Reset du `shown` à chaque changement recherche / tri / famille.
- **Côté Vue** : brancher sur la pagination serveur (cursor) — la maquette simule en client.

## États à implémenter

- **hover** carte (élévation + avatar scale) + play révélé.
- **empty** : « Aucun artiste ne correspond. » centré mono `--ink-3`.
- **loading** : skeleton de cartes (artwork + avatar + barres `--surface-2` shimmer) pour le 1er chargement et la tranche suivante.
- **PP absente** → initiales (déjà géré) ; **rating null** → badge masqué + stat `—` ; **lib/liked = 0** → `—`.

## Responsive (container-queries sur `.app`, pas media-queries viewport)

| Largeur conteneur | Adaptation |
|---|---|
| ≤ 900px | sidebar → **rail 66px** (icônes seules) |
| ≤ 820px | search pleine largeur, outils repliés |
| ≤ 680px | paddings réduits (18px) |
| ≤ 560px | grille **2 colonnes** |
| ≤ 380px | grille **1 colonne** |

→ La carte reste lisible à toute taille (avatar + nom + stats ne se cassent jamais).

## Route

- Page = **`/artists`**. Item de nav = **« Artistes »**.
- **Clic carte → `/artist/:id`** (lot suivant : Artist Detail, Vague 3).

## À fournir / trancher par willi

- Les points du **check backend** (le plus urgent : contrat de l'endpoint + pagination + les deux compteurs In Lib / Liked).
- Confirmer la **pondération genres** côté API (`genres[]` trié par nb de tracks) ou à faire côté front.
- Disponibilité réelle des **PP artistes** (sinon on lance avec le fallback initiales).
- Garder les **3 stats** (Catalog / In Lib / Liked) tel quel — validé.

---

## État DA — décisions de cette itération

- Direction **carte portrait** retenue (vs liste). Inspirée de Genres pour la cohérence.
- **Rating dédupliqué** : un seul, badge haut-droite avec étoile. (Avant : doublon badge + stat.)
- **Stat bas = Catalog / In Lib / Liked.** In-Lib et Liked sont **deux signaux distincts** (Rekordbox vs Radar) → on garde les trois.
- **Tri Liked** ajouté.
- Itérations encore ouvertes (non tranchées) : grille éditoriale top-artistes, fond mosaïque type Genres, stats enrichies (sets / dernier titre / BPM moyen). À explorer avec willi avant figeage.
