# Prompt Claude Code — Lecteur **round 2** (correctifs revue)

> Copie-colle ce bloc à Claude Code dans le repo **Willybi/diggy** (FastAPI + Vue 3, branche `master`).
> Suite du lot Lecteur **déjà implémenté** (`PlayerBar.vue` + `stores/audioPlayer.js` + montage `App.vue`).
> **Correctifs ciblés, pas une refonte.** Ne touche pas au contrat du store ni au montage existant.

---

Revue de l'implémentation du lecteur : 5 points. **1 → 3 à faire** (vrais défauts), **4 → 5 recommandés** (robustesse / finition). Respecte les conventions CLAUDE.md (100 % tokens, mono pour les données, accent discipliné, light + dark, reduced-motion).

## 1. 🔴 Icône play/pause des rows = état réel (`isCurrent && playing`)
- Fichiers : `components/TrackTable.vue` **et tout autre composant de ligne** qui déclenche le play (`GenreTrackRow.vue`, `ShelfCard.vue`, listes des vues détail si elles ont leur propre row).
- **Constat** : l'icône ⏸ (et le `--playing`) se basent sur `player.isCurrent(track.catalog_id)` **seul** → une track **mise en pause** garde l'icône ⏸ (laisse croire que ça joue).
- **Fix** : helper `isRowPlaying(track) = player.isCurrent(track.catalog_id) && player.playing`.
  - **Icône** : ⏸ si `isRowPlaying`, sinon ▶ (donc track courante **en pause** → ▶ pour reprendre).
  - La **teinte de ligne** `is-playing` : tu peux la garder sur `isCurrent` seul (la track active reste surlignée même en pause, façon Spotify) — au minimum **corrige l'icône**.
- Référence déjà correcte dans le repo : `HeroPlayer.vue` utilise `isCurrent && playing` → aligne les rows dessus.

## 2. 🔴 Seek clavier sur le rail (accessibilité)
- Fichier : `components/PlayerBar.vue`, élément `.pl-rail` (il a déjà `role="slider"` + `aria-valuenow/min/max` mais **aucun** `tabindex` ni `keydown`).
- **Fix** : ajouter `tabindex="0"` + `@keydown` :
  - `ArrowLeft` / `ArrowRight` → `player.seek(clamp(player.currentTime ∓ 1, 0, player.duration))`
  - `Home` / `End` → `0` / `player.duration` (option)
  - `e.preventDefault()` sur les touches gérées.
- Style focus visible sur `.pl-rail:focus-visible` (anneau `--accent-soft`).

## 3. 🔴 Gérer l'échec de preview (plus de `catch {}` muet)
- Fichier : `stores/audioPlayer.js`, action `play()` (le `try/catch` autour du fetch `/preview-url` + `el.play()`).
- **Constat** : `catch {}` avale tout → si l'extrait échoue (URL nulle, 404, lecture rejetée), le bandeau s'affiche **sans rien jouer et sans feedback** (bandeau « fantôme »).
- **Fix** :
  - exposer un `error` (ref `string | null`) dans le store, remis à `null` à chaque `play()`.
  - sur échec : `error.value = 'Aperçu indisponible'`, `loading = false`, et **soit** `close()` (fermeture propre) **soit** garder le bandeau avec le message — tranche pour `close()` si tu veux le plus simple.
  - garder un `console.warn(e)` pour le debug (ne pas avaler silencieusement).
- (Le flag `has_preview` désactive déjà le play côté row — ce correctif couvre le cas où l'URL casse **malgré** `has_preview = true`.)

## 4. 🟡 Largeur de sidebar en token (pas en dur) — recommandé
- `PlayerBar.vue` positionne via `left: calc(232px + 24px)` et `@media (max-width:900px){ left: calc(66px + 24px) }` — valeurs **dupliquées** du layout (`App.vue` : `grid-template-columns: 232px 1fr` / `66px 1fr`).
- **Fix** : définir `--sidebar-w` (232px ; 66px sous 900px) sur `.app-shell` (ou `:root` + override en média-query), puis :
  - `App.vue` : `grid-template-columns: var(--sidebar-w) 1fr`
  - `PlayerBar.vue` : `left: calc(var(--sidebar-w) + 24px)`
  - une seule source de vérité ⇒ plus de désalignement si la sidebar change.

## 5. 🟡 Finitions — recommandé
- **Mute visuel** : quand `muted`, refléter le slider à 0 sans perdre la valeur (`:value="muted ? 0 : volume"`), un clic sur l'icône restaure le volume mémorisé.
- **Thumb pendant le drag** : aujourd'hui le thumb n'apparaît qu'au `:hover`/`:active`. Ajouter une classe `.scrubbing` sur `.pl-rail` au `pointerdown` (retirée au `pointerup`) et `.pl-rail.scrubbing .pl-thumb { transform: translateY(-50%) scale(1) }` pour qu'il reste visible pendant le scrub capturé.
- **Equalizer plus organique** (option) : remplacer l'`animation: eq-dance … alternate` (2 étapes) par la keyframe **5 étapes** de la maquette `realign/Lecteur (pilote).html` (`@keyframes eq { 0/20/40/60/80/100% }`, `transform: scaleY`) — moins « métronome ».

## Clôture
- Rien d'autre ne bouge : **contrat du store inchangé**, montage `App.vue` inchangé, conventions tokens/mono/accent respectées.
- Light **et** dark vérifiés ; `prefers-reduced-motion` conservé.
- Signale à willi si un point soulève une question (notamment le choix `close()` vs message d'erreur au point 3).
