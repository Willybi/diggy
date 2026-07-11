# Brief — Hub de recherche / Accueil `/` (pilote réaligné)

> Maquette : `realign/Hub de recherche (pilote).html` · Tokens : `realign/diggy-tokens.css` · Mapping : `realign/diggy-style-map.js`
> Cible Vue 3. Barre sombre en haut = **outil de revue** (Direction / État / thème / densité / largeur), **PAS dans le produit**.
> Page = **landing** de Diggy ET **seule page accessible en non-connecté**. Rôle = **HUB** : chercher dans tout, écouter des aperçus, sans pouvoir deep-dive.

---

## Intention (décidé avec willi)

Une grande **barre de recherche par mot-clé** qui cherche dans **tout** (tracks, sets, artistes, playlists, genres),
avec un **dropdown de scope** pour préciser. C'est le point d'entrée de l'app. En **visiteur** (non-connecté) on peut
chercher et écouter quelques aperçus 30s, mais le **deep-dive est verrouillé** (ouvrir une fiche, actions bib, tri/filtres,
résultats au-delà des premiers). Une fois **connecté**, c'est **la même page déverrouillée** (résultats cliquables,
actions bib actives, tri/filtres) + la sidebar réapparaît.

## 3 directions à départager (toggle « Direction » dans la barre de revue)

| Dir | Nom | Parti-pris |
|---|---|---|
| **A** | **Spotlight** | Moteur épuré, **centré** verticalement façon page d'accueil de moteur. Gros wordmark + barre en pill + genres populaires + suggestions de requêtes. Le plus calme / grand public. |
| **B** | **Command palette** | Barre haute pleine largeur, **mono-forward**, dense. Accès rapide (récents), légende clavier (↑↓ / ↵ / esc). Le plus « power tool / pro DJ ». |
| **C** | **Vitrine** | Barre en haut + **showcase de découverte** en état vide (cartes genres mosaïque, artistes en vue, sets récents). Le plus « marketing / donne envie » pour un visiteur. |

→ **À trancher par willi** : on en garde **une**. Le moteur de recherche, le gating et les lignes de résultats sont **identiques** entre les 3 — seuls le layout d'**état vide** et la peau de la barre/résultats changent. Choisir A, B ou C n'impacte pas le backend.

---

## Comportement — recherche

- **Input** (debounce ~120 ms) + **dropdown de scope** : `Tout · Tracks · Artistes · Sets · Playlists · Genres`. Défaut = **Tout**.
  ⚠️ willi n'avait coché que « Tout » au cadrage, mais la demande initiale = un dropdown pour préciser → le dropdown contient **tous les types**, défaut Tout. À confirmer.
- **Résultats = liste unique mélangée**, triée par **pertinence**, chaque ligne préfixée d'un **badge de type** (icône + label mono).
  - Pertinence (maquette) : exact > startsWith > word-boundary > includes, tie-break par popularité (nb tracks). À refaire **côté serveur** (voir backend).
  - **Surlignage** du terme recherché dans le titre/sous-titre (`<mark>` → `--accent-soft`/`--accent-ink`).
- **Ligne résultat** selon le type :
  - **track** : badge · artwork (play au hover) · titre + artiste · `BPM` `Key` `durée` (mono) · zone bib.
  - **artist** : badge · avatar rond (initiales sur fond teinté famille, ou PP) · nom · `N tracks` · zone bib · play (aperçu top track).
  - **set** : badge · artwork teinté · titre (clamp 1) · `date · N tracks`.
  - **playlist** : badge · cover · nom · **badge source** (DEEZER `--accent-soft` / SPOTIFY `--pos-soft` / TIDAL `--surface-3`).
  - **genre** : badge · pastille couleur famille · nom (couleur famille, neutre si Misc) · `N tracks · N artistes · BPM`. Clic → `/style/:genre`.
- **Liens fiches** : track→`/catalog/:id`, artist→`/artist/:id`, set→`/set/:id`, playlist→`/playlists/:id`, genre→`/style/:genre`.

## Comportement — gating (visiteur vs connecté)

| | Visiteur | Connecté |
|---|---|---|
| Chercher | ✅ | ✅ |
| Écouter l'aperçu 30s | ✅ **illimité** (via le PlayerBar global déjà implémenté) | ✅ |
| Voir les résultats | **cappé** aux `GUEST_CAP` premiers (maquette = 6) puis **lock row** « Connecte-toi pour voir les N autres » | **tous** |
| Ouvrir une fiche | ❌ → **toast** de relance contextuelle « Connecte-toi pour ouvrir cette fiche » | ✅ navigue |
| Actions bib (ajout, like/dislike) | ❌ (zone bib masquée) | ✅ |
| Tri & filtres (BPM, A–Z…) | ❌ (chip verrouillé « Tri & filtres — connecte-toi ») | ✅ |
| Sidebar | masquée (hub plein cadre) | visible |
| Coin haut-droite | **Se connecter** (+ Créer un compte ghost) | chip user `willi` |

- **CTA login** = haut-droite **discret** + **relances contextuelles** (toast au clic sur une fiche, bouton dans le lock row).
- L'aperçu reste **généreux** (illimité) : c'est l'hameçon. On bride le **deep-dive**, pas l'écoute.
- Dans la maquette, « Se connecter » bascule en mode connecté (démo) pour voir l'état déverrouillé.

## États
- **Vide** (pas de requête) : état d'accueil par direction (A : chips genres + suggestions ; B : accès rapide + clavier ; C : vitrine).
- **Résultats** : liste + compteur « N résultats pour « … » ».
- **Aucun résultat** : « Aucun résultat. Essaie un autre mot-clé. » (mono `--ink-3`).
- **Aperçu en cours** : player bar bas (artwork, titre/artiste, equalizer `--accent`, scrub, « aperçu Deezer », fermer). Reduced-motion → equalizer figé.

## Responsive (container-queries sur `.app`)
- ≤ 900px : sidebar (connecté) → rail 66px.
- ≤ 680px : paddings 18px, scope en icône, durée masquée, badge type en icône seule.
- ≤ 540px : wordmark hero réduit, BPM masqué.

---

## 🛑 Backend — à vérifier AVANT le front

- [ ] **Endpoint de recherche unifié** `GET /api/search?q=&scope=all|track|artist|set|playlist|genre&limit=&cursor=`.
      Renvoie une liste **typée** triée par pertinence serveur. Champs par item = ceux des lignes ci-dessus (+ `id` pour les liens).
      Pertinence : full-text (titre/artiste/nom) ; pondérer par popularité (nb tracks) en tie-break.
- [ ] **Scope `all`** : fusion multi-entités triée par score commun — définir la normalisation des scores entre types.
- [ ] **Accès public (non authentifié)** : la route `/search` doit répondre **sans session**. Le **cap visiteur** (`GUEST_CAP`)
      et le masquage des champs bib (`inLib`, `liked`) se décident **côté serveur** selon l'état d'auth (ne pas fuiter le total exact ? → renvoyer `total` pour afficher « N autres »).
- [ ] **Aperçus** : `previewUrl` (Deezer 30s) dispo pour tracks **et** pour l'« aperçu top track » d'un artiste. Réutilise le **store audio** du PlayerBar déjà en place.
- [ ] **Routing** : `/` = hub. Si non-connecté → toutes les routes profondes redirigent vers `/` (ou affichent le toast). À cadrer avec le garde de route Vue.
- [ ] **Genre key** : lien genre = nom brut URL-encodé (même contrat que Genre Detail : `/style/Dance%20%2F%20Pop`).

## Conventions (rappel — voir CLAUDE.md)
- 100% tokens `var(--…)`. Mono = **données** (BPM, key, durée, compteurs, dates) ; UI = titres/labels/boutons.
- `--accent` réservé action/key/CTA/surlignage ; **bib = `--pos` uniquement** ; couleurs genre via `diggy-style-map.js`.
- Densité `--row-h`/`--pad` ; formes `--r-*` / `--shadow-*`.

## À trancher par willi
- **Direction A / B / C** (le choix principal).
- **Scope par défaut** = Tout, dropdown complet — OK ?
- **`GUEST_CAP`** : combien de résultats visibles avant le lock (maquette = 6).
- **Total visible au visiteur** : on affiche « N autres résultats » (révèle le volume) ou un libellé flou ?
- **Aperçu artiste** : lit la top track ? ou désactivé pour les artistes ?
