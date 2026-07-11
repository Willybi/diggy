# Prompt Claude Code — Lecteur / Player bar (composant global)

> Copie-colle ce bloc à Claude Code dans le repo **Willybi/diggy** (FastAPI + Vue 3, branche `master`).
> Les chemins design (`design/...`) correspondent au handoff Diggy ; vérifie leur emplacement réel dans ton repo.

---

Tu implémentes le lot **Lecteur / Player bar** (Vague 1 du kit partagé : « HeroPlayer + player audio inline, preview Deezer 30 s ») en réalignant sur la DA Wildflower (tokens = frontière). Ce n'est **pas une page/route** : c'est un **bandeau global** monté une seule fois dans le shell, qui apparaît quand une preview démarre et persiste entre les routes.

## 0. À lire avant de coder
- `design/CLAUDE.md` + `design/ROADMAP-realign.md` — conventions **non-négociables** (tout via `var(--…)`, mono pour les données, `--accent` discipliné, in-lib = `--pos`, container-queries, densité, UTF-8 strict).
- **Maquette de référence** : `design/realign/Lecteur (pilote).html` (la barre sombre du haut + les segments Animation/Volume/Largeur sont l'**outil de revue, hors-produit**).
- **Brief détaillé** : `design/realign/BRIEF-player.md`.
- **🔒 Décisions figées (validées willi)** — n'implémente QUE ça :
  - **Animation = `equalizer`** (5 fines barres `--accent`, durées désaccordées, figées hors lecture).
  - **Volume = `inline`** (icône + slider horizontal toujours visible).
  - Les autres modes du toolbar (waveform / anneau / pulse · popover / toggle) ne servaient qu'à comparer → **ne pas les coder**.
- Code existant à réutiliser / aligner :
  - Front : `server/frontend/src/stores/audioPlayer.js` (existe — **à aligner sur le contrat ci-dessous**), `components/HeroPlayer.vue` (= le bandeau ; **à (ré)écrire** selon la maquette), le composant track-row / `TrackTable.vue`, le shell/layout (`App.vue` ou `layouts/…` où vit `SidebarNav`), `utils/format.js` (helper `mm:ss`), `styles/diggy-tokens.css`.
  - Backend : schémas track (`server/api/schemas.py`) — voir §1.

## 1. 🛑 BACKEND — minimal, juste vérifier `preview_url`

Aucun nouvel endpoint. **Vérifie que le champ `preview_url`** (l'extrait Deezer 30 s, mp3) **est exposé sur TOUTES les listes de tracks** que le front rend (catalog, genre `…/{name}/tracks`, set, playlist, artist, radar). C'est lui qui alimente l'`<audio>`.
- S'il manque sur un schéma, ajoute-le (il vient de l'ingest Deezer — vérifie la colonne en base, ne réinvente pas la source).
- Si `preview_url` est `null` pour une track (pas de match Deezer), le front doit **désactiver** le play de cette ligne (voir §4). Ne renvoie pas de placeholder.

> Si la donnée est ambiguë (colonne, nullabilité), **remonte-le à willi avant de coder** — ne devine pas le contrat.

## 2. Store `stores/audioPlayer.js` (Pinia) — source de vérité

Un **seul** `HTMLAudioElement` partagé (créé en lazy, réutilisé) ⇒ garantit « une seule preview à la fois ».

- **state** : `{ track: null, playing: false, currentTime: 0, duration: 30, volume: 0.8, muted: false }`
  - `volume` **persisté** (`localStorage`) ; relu à l'init.
- **getters** : `isCurrent(trackId)`, `progress` (= currentTime / duration), `visible` (= `track !== null`).
- **actions** :
  - `play(track)` : si `isCurrent(track.id)` → `toggle()` ; sinon charge (`audio.src = track.preview_url; audio.play()`), set `track`, affiche le bandeau, `currentTime = 0`.
  - `toggle()` (play/pause) · `seek(t)` (→ `audio.currentTime = t`) · `setVolume(v)` (→ `audio.volume`, persiste) · `toggleMute()` (→ `audio.muted`) · `close()` (pause + `track = null` ⇒ le bandeau se cache).
  - branche les events audio : `timeupdate` → `currentTime` · `loadedmetadata` → `duration` (≈ 30 mais lis la vraie valeur) · `ended` → `playing = false` (état « rejouable » depuis 0).
- **La progression vient de l'`<audio>` (`timeupdate`), PAS d'un timer maison.** (La maquette simule avec un rAF faute d'URL ; en prod c'est l'audio qui pilote.)

## 3. Front — `components/HeroPlayer.vue` (le bandeau) selon la maquette

Anatomie (gauche → droite) — reproduis la maquette à l'identique :
- **Play / Pause** rond plein `--accent` (icône `--on-accent`).
- **Equalizer** : 5 fines barres `--accent` (largeur ~3px), à gauche du titre, qui dansent quand `playing` (durées désaccordées 0.85→1.55s = organique, `transform: scaleY`), **figées** sinon.
- **Identité** : titre (`--font-ui` 600) + artiste (`--ink-3`), ellipsis 1 ligne chacun.
- **BPM · Key** : 2 micro-stats **mono** (`129`/`BPM`, `3A`/`KEY` ; Key en `--accent-ink`), séparateur `--line`.
- **Timeline** : écoulé (mono `--ink-2`) — **barre de progression fine scrubbable** (rail `--line-2`, remplissage `--accent`, poignée révélée au hover/scrub) — restant (mono `--ink-3`, format `-0:19`). Durée pleine = `duration` (≈ 30 s).
- **Volume inline** : icône + **slider horizontal toujours visible** (~84px). L'icône reflète fort / faible / **mute** ; clic sur l'icône = mute/unmute. Slider → `setVolume`.
- **✕** ghost (`--ink-3` → `--ink`) = stop + fermer (slide-down). _(Pas de mini-artwork : l'equalizer fait l'ancre visuelle — choix produit ; à rouvrir avec willi seulement s'il le redemande.)_

Ancrage & shell :
- **Monté une seule fois dans le shell** (`App.vue`/layout), **hors `<router-view>`** ⇒ persiste entre les routes. `v-if="player.visible"`.
- `position: fixed`, **bandeau flottant** : largeur calée sur la carte app (`max-width`), centré, `bottom: 18px`, `--r-lg`, `--shadow-lg`, fond `--surface`, bordure `--line`, `z-index` au-dessus de tout.
- ⚠️ **`container-type` sur un wrapper INTERNE** (`.pl-shell`), **jamais sur l'élément animé** (`.player`) : un query-container sur l'élément transformé casse sa transition d'entrée en Chromium (constaté en maquette).
- **Entrée** slide-up + fade (~.34s cubic-bezier) ; **sortie** slide-down au ✕. `prefers-reduced-motion` ⇒ fade seul + equalizer figé.
- **Réserver l'espace** : quand le bandeau est visible, ajoute du `padding-bottom` à la zone scrollable (≈ `--row-h` + 56px) pour que la dernière ligne ne soit jamais masquée.
- **Scrub** : pointer events (down/move/up + `setPointerCapture`) **et** clavier ←/→ ; `role="slider"` + `aria-valuenow` ; `seek()` sur le store.

## 4. Brancher les track-rows partout

- Tout **bouton play / clic de ligne** (Catalog, Genre Detail, Set/Artist/Playlist detail, Radar…) appelle `audioPlayer.play(track)` avec `{ id, title, artist, bpm, key, preview_url }`.
- La ligne reflète l'état du store : classe **playing** (`--accent-wash` + titre `--accent-ink` + bouton **pause**) si `audioPlayer.isCurrent(track.id) && playing`. Le bouton repasse **play** sinon.
- Si `preview_url` est absent ⇒ play **désactivé** (bouton inerte/atténué, pas d'action).
- Cliquer une autre ligne pendant la lecture ⇒ **bascule** (remplace) la track en cours (géré par `play()`).

## 5. Conventions & clôture
- 100 % tokens ; **mono** pour toutes les données (timers, BPM, Key) ; `--accent` réservé à l'action (Play), au remplissage de progression et à la Key ; volume = neutre `--ink-2`.
- **Light + dark** vérifiés ; **densité** (`--row-h`) cohérente.
- Responsive (container-queries sur le wrapper du bandeau) : `≤720` masque **BPM · Key** · `≤560` masque les **timers** · `≤440` gaps resserrés.
- À la fin : **coche** la ligne « HeroPlayer + player audio inline » dans `design/ROADMAP-realign.md` (Vague 1) et signale à willi tout écart `preview_url` côté backend.
