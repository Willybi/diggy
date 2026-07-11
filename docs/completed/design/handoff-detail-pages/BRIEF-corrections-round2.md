# Corrections pages détail — Round 2 (vérifié contre le code GitHub)

> Relu directement dans `server/frontend/src` (commit `5813eaad`). Distingue les **vrais bugs**
> des **faux positifs** (blocs conditionnels sans data sur le set/playlist testés).
> Réf. maquette à jour : `Pages détail (pilote).html` + `pages-detail.css` + `pages-detail-data.js`.
> ⭐ = vrai correctif · 🅳 = c'était un problème de DATA, pas de code.

---

## ✅ Déjà correct dans le code (ne rien faire — c'était de la data manquante)

Mon premier audit a signalé le Set comme « incomplet ». **Faux** : les blocs sont rendus en
`v-if` et le set testé (*PART TIME KILLER*) n'a pas les champs en base.

- 🅳 **Set — sous-titre** : `heroSub` construit déjà `artistes (B2B) · event · venue`. Vide car ce set n'a **aucun artiste lié + pas d'event/venue** en base. → problème data, pas front.
- 🅳 **Set — Description / Artistes / StyleTags genres** : les 3 blocs existent (`v-if djSet.description`, `v-if artists.length > 1`, `v-if djSet.genres?.length`). Vides faute de data sur ce set. Le backend `genres[]` est **déjà exposé** (S6 fait).
- 🅳 **Set — play au hover** : présent (`v-if t.has_preview && !t.is_id`).
- 🅳 **Playlist — « Dans cette playlist »** : bloc top_artists / top_genres **déjà codé** (`v-if`). Vide car l'API ne renvoie pas encore `top_artists`/`top_genres`. → reste ⚙ backend.
- 🅳 **Playlist — lien externe / SourceBadge** : corrects (`externalUrl` par source, `SourceBadge`).

👉 Pour valider ces écrans, il faut les tester sur un set/playlist **riches en data** (artistes liés, description, genres, agrégats). Ça n'est pas un chantier front.

---

## ⭐ Vrais correctifs

### Genre — like/dislike (le gros morceau)

1. **Collision in-lib ↔ like/dislike sur `GenreCard.vue`** : `.gc-lib` (badge « en bib ») et `.gc-acts` (LikeDislike) sont **tous deux** en `top:10px; right:10px` → ils se superposent. Fix :
   - `.gc-lib` → **haut-GAUCHE** (`top:10px; left:10px`).
   - `.gc-acts` (like/dislike) → reste **haut-DROITE**, mais **révélé au hover** (comme `.gc-play`) pour ne pas surcharger la carte au repos.
2. **Genre Detail : like/dislike absent**. La carte permet de liker un **genre** (`opinions.set('genre', name)`), mais la page `/style/:genre` n'a **aucun** contrôle d'avis. → Ajouter le `LikeDislike` **genre-level** dans le hero de `GenreDetailView.vue` (à côté de « Écouter un aperçu »), lié au même store `opinions('genre', genre.name)`.
3. **Cohérence track-level** : le like/dislike **track** existe sur Track Detail (hero) ✓. Il n'est **pas** sur les lignes de track (`GenreTrackRow`, tables playlist/set/artist). Décision produit à trancher : si on veut liker une track depuis une liste, ajouter `LikeDislike` dans la zone d'actions au hover (près du play). Sinon on laisse l'avis track uniquement sur la page track. **→ me confirmer l'intention avant de généraliser.**

### Genre — espacement

4. **Manque de marge entre la rangée de boutons (« Écouter un aperçu » / « Tout filtrer ») et la StatStrip** — elles se touchent. Ajouter ~`14–16px` (`margin-top` sur la StatStrip du hero, ou `margin-bottom` sur `.gh-actions`).

### Track

5. **« Apparaît dans » déborde / mal cropé** (confirmé William). La ligne (titre long + timecode + date + chevron) sort de la carte. Fix : conteneur `min-width:0`, titre `text-overflow:ellipsis` sur 1 ligne, timecode+date en 2ᵉ ligne. Jamais laisser le contenu élargir la colonne.
6. **« Du même artiste » : trop d'espace vide** (irritant récurrent). C'est une **mini-table** qui étire le titre et pousse BPM/KEY/RATING/LIB tout à droite. → passer en **grille 2 colonnes** de lignes compactes (voir `.mini-grid` / `.mini-row` dans la maquette) : cover + titre/artiste + cluster data collé, 2 par rangée, 1 colonne sous 720px.

### Artist

7. **Titre illisible sur la bannière** (fond mosaïque = couleur aléatoire). Solution maquette :
   - Seul le **titre** est sur la bannière → **blanc** + **text-shadow**, scrim renforcé (dégradé bas + gauche).
   - Sous-titre / StyleTags / boutons **descendent SOUS la bannière** (`--ink` normal).
   - Avatar en **position absolue** pour ne pas remonter le corps.
   - Réf : `.hb-name` / `.hb-scrim` / `.hero--banner` dans `pages-detail.css`.

### Playlist

8. **Doublon « TIDAL »** : `heroSub = playlist.owner`, et pour cette playlist l'`owner` **vaut littéralement « TIDAL »** → il double le `SourceBadge`. Fix : masquer le sous-titre quand `owner` (insensible à la casse) == le label de la source. Sinon garder l'owner (nom du curateur) — c'est utile quand ce n'en est pas un doublon.
9. **LibDot en 1ʳᵉ colonne (creux, façon case à cocher)** — `.mt-lib` est la colonne la plus à gauche. Le déplacer en **colonne de droite** (comme les autres tables) pour lever l'ambiguïté visuelle. *(préférence, pas bloquant)*

### Admin (transverse)

10. **Carte admin `variant="warn"` en bordure PLEINE** (`1px solid var(--warn-ink)`) sur Track & Set, alors que la carte admin par défaut est **tiretée** (`dashed line-2`, conv. D2). → passer le `.warn` en **tireté** aussi (garder la teinte warn sur le tiret) pour rester cohérent avec D2.

---

## Récap checklist Claude Code

- [ ] `GenreCard` : in-lib → haut-gauche, like/dislike → haut-droite **au hover** (fin de la collision)
- [ ] `GenreDetailView` : ajouter like/dislike **genre-level** dans le hero
- [ ] `GenreDetailView` : marge boutons ↔ StatStrip
- [ ] Track : « Apparaît dans » clampé (ellipsis, pas de débord)
- [ ] Track : « Du même artiste » mini-table → **grille 2 colonnes**
- [ ] Artist : titre blanc+ombre sur bannière, reste sous la bannière
- [ ] Playlist : masquer sous-titre si `owner == source`
- [ ] Playlist : LibDot en colonne droite *(optionnel)*
- [ ] Admin `.warn` : bordure tiretée (D2)
- [ ] À trancher : like/dislike **track-level** sur les lignes de liste ? (attendre confirmation)

## Toujours ⚙ backend (rappel)

- API playlist : renvoyer `top_artists` + `top_genres` (agrégats) → débloque « Dans cette playlist ».
- API set : idem si on veut un « Dans ce set » (optionnel, cf. brief initial).
- Pagination tracks artiste (au-delà de 50).
