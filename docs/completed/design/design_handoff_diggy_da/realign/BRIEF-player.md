# Brief — Lecteur / HeroPlayer (pilote réaligné)

> Maquette : `realign/Lecteur (pilote).html` · Tokens : `realign/diggy-tokens.css`
> Cible Vue 3, composant **global partagé** (Vague 1). La barre sombre en haut + les segments
> **Animation / Volume / Largeur** sont des **outils de revue**, PAS dans le produit.
> Couvre la ligne ROADMAP « HeroPlayer + player audio inline (preview Deezer 30 s) ».

---

## Objectif

Aujourd'hui : clic sur une prévisu → le son part, rien à l'écran.
Cible : un **bandeau lecteur en overlay**, ancré en bas, **toujours visible** quelle que soit
la page, qui apparaît quand une preview démarre et disparaît quand on arrête.
Périmètre figé (cf. questions) : **preview Deezer 30 s, une seule à la fois** — pas de queue,
pas de prev/next. Le composant doit rester extensible mais on ne conçoit QUE ça maintenant.

## Ancrage & overlay

- `position: fixed`, **bas du viewport**, `z-index` au-dessus de tout le contenu routé.
- **Bandeau flottant** : largeur calée sur la carte app (`max-width: --app-mw`), centré,
  `bottom: 18px`, coins `--r-md/--r-lg`, `--shadow-lg`, fond `--surface`, bordure `--line`.
- En prod : un seul `<Player>` monté dans le **shell app**, hors du `<router-view>`,
  donc il **persiste entre les routes** (catalog → genre → artiste…). C'est le « partout ».
- Réserver l'espace : quand le lecteur est visible, ajouter du `padding-bottom` à la zone
  scrollable (≈ `--row-h` + 56px) pour que la dernière ligne ne soit jamais masquée.

## Apparition / disparition

- **Entrée** : slide-up + fade (`transform: translateY(...)` → `0`, `opacity 0→1`),
  `~.34s` cubic-bezier sortie douce. Respecter `prefers-reduced-motion` (fade seul).
- **Sortie** : slide-down + fade au clic sur **✕** (= stop + fermer), retour état vide.
- Le bandeau n'existe dans le DOM/visible **que** s'il y a une track active.

## Anatomie du bandeau (gauche → droite)

| Bloc | Contenu | Type / token |
|---|---|---|
| Play / Pause | bouton rond plein `--accent`, icône `--on-accent` | action principale (seul gros accent) |
| Animation | indicateur « ça joue » (voir § Animation) | `--accent` |
| Identité | **Titre** (ui 600) + **artiste** (ui, `--ink-3`), ellipsis | clamp 1 ligne chacun |
| BPM · Key | 2 micro-stats **mono** : `129`/`BPM`, `3A`/`KEY` | Key en `--accent-ink`, séparateur `--line` |
| Timeline | écoulé `0:11` — barre scrub — restant `-0:19` | timers **mono** tabulaires `--ink-2`/`--ink-3` |
| Volume | bouton + contrôle (voir § Volume) | neutre `--ink-2` |
| Fermer | **✕** ghost | `--ink-3` → `--ink` au hover |

- **Barre de progression scrubbable** : rail `--line-2`, remplissage `--accent`, poignée
  ronde révélée au hover/scrub. Clic + drag (pointer events) ET flèches ←/→ au clavier
  (`role="slider"`, `aria-valuenow`). Durée pleine = **30 s** (preview).
- **Pas d'artwork** dans le bandeau (choix produit) — l'animation tient le rôle d'ancre visuelle.

## Animation « ça joue » — RETENU : `equalizer`

**Validé designer : `equalizer`** (5 fines barres `--accent` à gauche du titre, durées désaccordées = organique, figées hors lecture ; la barre de progression reste la **fine ligne** `--accent`). Les autres modes restent dans la maquette pour référence mais **ne sont pas à implémenter**.

| Mode | Description | Note |
|---|---|---|
| **equalizer** ✅ | 5 fines barres `--accent` qui dansent à gauche du titre (durées désaccordées) ; barre de progression fine conservée | **retenu** |
| waveform | la barre devient une waveform haute | non retenu |
| anneau | anneau de progression autour du Play | non retenu |
| pulse | ondes concentriques autour du Play | non retenu |

→ **À valider** : on garde lequel ? (les 4 cohabitent dans la maquette pour comparer).
Toutes les animations doivent se **figer hors lecture** et respecter `prefers-reduced-motion`.

## Volume — RETENU : `inline`

**Validé designer : `inline`** — icône + slider horizontal **toujours visible** (≈ 84px) à droite de la barre. Les modes popover / toggle restent dans la maquette pour référence mais ne sont pas à implémenter.

| Mode | Description | Note |
|---|---|---|
| **inline** ✅ | icône + slider horizontal toujours visible | **retenu** |
| popover | slider en popover au hover/focus | non retenu |
| toggle | icône seule, clic = mute | non retenu |

- Icône reflète l'état : fort / faible / **mute** (3 variantes).
- Clic sur l'icône = mute/unmute (même en inline).
- Persister le volume (`localStorage`/store) entre sessions.

## États & interactions

- **Clic sur une ligne (ou le bouton play) du tableau** → charge la track, `t=0`, lecture,
  bandeau slide-up. La ligne passe `--accent-wash` + titre `--accent-ink`, son bouton montre **pause**.
- **Clic sur une autre ligne pendant la lecture** → **bascule** (remplace) : nouvelle track, `t=0`.
- **Play/Pause du bandeau** ↔ synchro avec l'icône de la ligne active.
- **Fin des 30 s** → stop auto, l'UI revient sur **play** (re-jouable depuis 0), bandeau conservé.
- **✕** → stop + slide-down + la ligne perd l'état lecture.

## Câblage audio (prod — la maquette SIMULE)

- La maquette anime une horloge JS (rAF) faute d'URL Deezer. En prod :
  - un seul `<audio>` (élément unique réutilisé) ; `src` = **preview 30 s Deezer** (`preview` de l'API track).
  - progression pilotée par l'event **`timeupdate`** (`audio.currentTime` / `audio.duration`),
    pas par un timer maison ; scrub = set `audio.currentTime`.
  - `ended` → état « rejouable ». `volume` slider → `audio.volume` ; mute → `audio.muted`.
  - jouer une nouvelle track = `audio.src = …; audio.play()` (le bandeau ne se démonte pas).
- Garder l'état lecteur dans un **store** (Pinia) : `{ track, playing, t, duration, volume, muted }`
  pour qu'il survive aux changements de route.

## Conventions (rappel CLAUDE.md)

- 100 % `var(--…)`. `--accent` réservé : Play, remplissage progression, Key. Jamais en déco.
- **Mono** pour toute donnée : timers, BPM, Key. **UI** pour titre/artiste/labels.
- Container queries (le bandeau a son propre `container-type` sur un **wrapper interne**,
  ⚠️ pas sur l'élément animé : un container sur l'élément transformé casse sa transition en Chromium).
- Densité : la hauteur du bandeau peut suivre `--row-h` si besoin (la maquette fige ~74px).

## Responsive (container queries, largeur du bandeau)

- `≤ 720c` : masquer le bloc **BPM · Key**.
- `≤ 560c` : masquer les **timers** (la barre + Play/Volume suffisent).
- `≤ 440c` : identité en `flex: auto`, gaps resserrés.

## À valider avec le designer

1. ✅ Animation = **equalizer** (validé).
2. ✅ Volume = **inline** (validé).
3. Le **✕** : ok pour stop+fermer ? (la liste de contenus cochée ne l'incluait pas, mais
   « disparaître quand on n'écoute plus » l'impose — sinon : fermer = quand la preview finit ?).
4. Faut-il un mini-artwork à gauche malgré tout, ou l'animation suffit comme ancre ?
