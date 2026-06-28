# Brief Design — Genres Diggy

## Contexte

Diggy est une webapp DJ (dark mode, OKLCH, tokens CSS). On a maintenant une **taxonomie hiérarchique** de 540 genres avec des relations parent/enfant issues de Wikidata + GenreGenealogy.

**Problème actuel** : le système de couleurs est basé sur 4 "familles" hardcodées (house=violet, techno=magenta, trance=rose, other=amber) avec un mapping manuel flou. Les sous-genres prennent juste la teinte de leur famille sans différenciation.

**Objectif** : refaire le système de couleurs en s'appuyant sur la vraie taxonomie pour que chaque branche ait une identité visuelle cohérente, avec des dégradés naturels du parent vers les sous-genres.

---

## Architecture de la taxonomie

### Les 8 piliers électroniques (genres racines principaux)

Ce sont les grands genres à partir desquels tout descend. Chacun devrait avoir sa **teinte principale (hue)**.

| Genre racine | Sous-genres directs | Total descendants | Vibe / Identité |
|---|---|---|---|
| **House** | 66 | ~120+ | Groovy, chaud, club, disco roots |
| **Techno** | 32 | ~80+ | Brut, industriel, hypnotique |
| **Trance** | 22 | ~50+ | Euphorique, psyché, éthéré |
| **Drum & Bass** | 29 | ~45+ | Rapide, jungle, sombre/liquide |
| **Hardcore** | 29 | ~50+ | Dur, rapide, gabber, distorsion |
| **Dubstep** | 10 | ~25+ | Basse, sombre, wobble |
| **Breakbeat** | 13 | ~20+ | Cassé, funky, rave |
| **Disco** | 11 | ~30+ | Funky, rétro, dancefloor |
| **UK Garage** | 8 | ~20+ | 2-step, speed, grime |
| **Hard Dance** | 15 | ~30+ | Hardstyle, jumpstyle, happy |
| **Autres genres** | — | — | Fourre-tout non-électronique (Rock, Jazz, Pop...) |

### Arbre détaillé des sous-genres

#### House (hue actuel : 260 violet)
```
house music
├── deep house
│   ├── Lo-Fi House
│   ├── melodic house
│   ├── organic house
│   ├── lo-fi house
│   ├── UK garage (→ branche séparée)
│   └── future garage
├── tech house
│   ├── deep tech
│   ├── minimal house
│   ├── rominimal
│   ├── Latin tech
│   └── microhouse
├── progressive house
│   ├── dark progressive house
│   ├── progressive electro house
│   ├── festival progressive house
│   └── melodic house
├── Chicago house
│   ├── acid house
│   ├── deep house
│   ├── garage house → New Jersey sound
│   ├── tribal house → guaracha
│   ├── microhouse
│   └── Detroit techno (→ branche techno)
├── electro house
│   ├── complextro
│   ├── Dutch house
│   ├── fidget house
│   ├── French electro
│   ├── Melbourne bounce
│   └── progressive electro house
├── Afro house
│   ├── Afro tech
│   └── 3-step
├── future house
│   ├── slap house
│   └── future bounce
├── bass house → speed house
├── French house → electro house
├── Amapiano → Afropiano
├── gqom (9 sub-genres)
├── ghetto house → juke, ghettotech
├── soulful house
├── funky house
├── jackin' house
├── vocal house
├── disco house
├── piano house
├── acid house
├── hard house → pumping house, scouse house, poky
├── tropical house
├── big room house
├── kwaito → bacardi
└── ~20 autres (Italo house, hip house, club house...)
```

#### Techno (hue actuel : 320 magenta)
```
techno
├── Detroit techno
│   ├── Berlin techno → Hypnotic Techno
│   ├── minimal techno
│   │   ├── melodic techno
│   │   ├── industrial techno → Birmingham sound
│   │   ├── Hypnotic Techno
│   │   └── dub techno
│   ├── acid techno → acid techno variants
│   ├── ambient techno → deep techno
│   ├── dub techno
│   └── bleep techno
├── hard techno
│   ├── Schranz
│   ├── free tekno → tribe
│   ├── mákina
│   └── meme techno
├── peak time techno
├── raw techno
├── deep techno
│   ├── ambient techno
│   └── dub techno
├── electro-techno
├── hardgroove techno
├── progressive techno
├── techno-tribal
├── wonky techno
├── experimental techno
├── trance (→ branche séparée)
├── hardcore (→ branche séparée)
├── tech house (→ aussi sous house)
└── progressive house (→ aussi sous house)
```

#### Trance (hue actuel : 352 rose)
```
trance
├── psychedelic trance
│   ├── Goa trance → nitzhonot
│   ├── dark psytrance → hi-tech psytrance, psycore
│   ├── progressive psytrance → zenonesque
│   ├── full-on → twilight, morning, uplifting psy
│   ├── classic psytrance
│   ├── forest psytrance
│   ├── tribal psytrance
│   ├── offbeat psytrance
│   ├── suomisaundi
│   └── minimal psytrance
├── progressive trance → melodic trance
├── Eurotrance
│   ├── hands up → buchiage trance
│   ├── symphonic trance
│   └── anthem trance
├── uplifting trance
├── vocal trance
├── Hard trance
├── acid trance
├── tech trance
├── classic trance
├── deep trance
├── dream trance → dream folk
├── big room trance
├── Balearic trance
├── raw trance
├── hypnotic trance
├── trance 2.0
└── neo trance
```

#### Drum & Bass
```
drum and bass
├── Liquid DnB
│   ├── Deep DnB
│   ├── Mainstream DnB
│   └── autonomic
├── jungle
│   ├── ragga jungle
│   ├── experimental jungle
│   ├── UK garage (→ branche séparée)
│   └── footwork jungle
├── neurofunk
├── jump-up
│   ├── clownstep
│   └── 170bpm Revival
├── techstep → darkstep → skullstep, crossbreed
├── intelligent drum and bass
│   ├── atmospheric drum and bass
│   ├── artcore drum and bass
│   └── jazzstep
├── halftime
├── drumstep
├── minimal drum and bass → autonomic, microfunk
├── deep drum and bass
├── dancefloor drum and bass
├── industrial drum and bass
├── Rollers
├── drumfunk
├── hardstep
└── sambass
```

#### Hardcore
```
hardcore
├── gabber
│   ├── mainstream hardcore
│   ├── early hardcore
│   ├── gabberpop
│   ├── gabber punk
│   └── gabber metal
├── happy hardcore
│   ├── UK hardcore → future core, powerstomp
│   └── bouncy techno
├── breakbeat hardcore
│   ├── jungle (→ branche DnB)
│   ├── darkcore
│   ├── 4-beat
│   └── hardcore breaks
├── breakcore
│   ├── mashcore
│   ├── raggacore
│   └── lolicore
├── speedcore
│   ├── splittercore
│   ├── extratone
│   ├── hypertone
│   └── supertone
├── Frenchcore
├── industrial hardcore
├── digital hardcore
├── crossbreed
├── doomcore
├── acidcore
├── Schranz
├── artcore
├── frapcore
└── trancecore
```

#### Dubstep
```
dubstep
├── brostep
│   ├── deathstep → minatory
│   ├── briddim
│   ├── tearout brostep
│   ├── colour bass
│   ├── drumstep (→ aussi DnB)
│   └── riddim → future riddim, liquid riddim
├── UK bass
├── melodic dubstep
├── chillstep
├── dungeon sound
├── tearout dubstep
├── purple sound
├── nightstep
└── reggaestep
```

#### UK Garage
```
UK garage
├── 2-step garage
├── grime
│   ├── neo-grime
│   ├── sinogrime
│   ├── Finnish grime
│   ├── weightless
│   ├── rhythm & grime
│   └── grindie
├── dubstep (→ branche séparée)
├── bassline
├── future garage
├── dark garage
├── breakstep
└── speed garage
```

#### Hard Dance
```
hard dance
├── hardstyle
│   ├── rawstyle → xtra raw, rawphoric
│   ├── euphoric hardstyle
│   ├── early hardstyle
│   ├── dubstyle
│   ├── psystyle
│   └── nustyle
├── hardtek
│   ├── raggatek
│   └── pumpcore
├── UK hardcore
│   ├── future core
│   └── powerstomp
├── hands up → buchiage trance
├── jumpstyle
├── Hard trance
├── hard NRG
├── neo rave
├── speed house
├── dancecore
├── lento violento
├── mainstream hardcore
└── mákina
```

---

## Système de couleurs actuel (à refaire)

### Tokens CSS actuels (OKLCH)
```css
--family-house:  260;   /* violet */
--family-techno: 320;   /* magenta */
--family-trance: 352;   /* rose */
--family-misc:   42;    /* amber (fourre-tout) */
```

### Composants utilisant les couleurs de genre
- **StyleTag.vue** — chip/pill avec dot coloré (hue famille + shade offset)
- **GenreCard.vue** — carte 2x2 mosaïque avec tuiles teintées (4 lightness offsets)
- **GenreDetailView.vue** — hero 3x2 mosaïque (6 lightness offsets)
- **diggy-tokens.css** — tokens tag-bg-l, tag-fg-l, tag-dot-l en OKLCH

### Comment ça marche
La fonction `styleTone(genreName)` retourne `{ family, hue, shade }`.
Le hue est appliqué en CSS via `--th` (theme hue) sur les composants.
Les variations de lightness créent les dégradés dans les mosaïques.
Le shade (toujours 0 aujourd'hui) est prévu pour différencier les sous-genres.

---

## Mappings actuels (noms bruts → taxonomie)

Les noms bruts viennent de Beatport et Deezer. Voici la correspondance :

| Nom brut (Beatport/Deezer) | Nœud taxonomique |
|---|---|
| House | house music |
| Deep House | deep house |
| Tech House | tech house |
| Progressive House | progressive house |
| Afro House | Afro house |
| Bass House | bass house |
| Organic House | organic house |
| Funky House | funky house |
| Jackin House | jackin' house |
| Melodic House & Techno | melodic techno |
| Minimal / Deep Tech | deep tech |
| Nu Disco / Disco | nu-disco |
| Disco | disco |
| Indie Dance | indie dance |
| Electro | electro |
| Electro (Classic / Detroit / Modern) | electro |
| Electronica | electronica |
| Techno (Peak Time / Driving) | peak time techno |
| Techno (Raw / Deep / Hypnotic) | deep techno |
| Techno/House | techno |
| Hard Techno | hard techno |
| Trance | trance |
| Trance (Main Floor) | trance |
| Trance (Raw / Deep / Hypnotic) | trance |
| Psy-Trance | psychedelic trance |
| Drum & Bass | drum and bass |
| Dubstep | dubstep |
| 140 / Deep Dubstep / Grime | dubstep |
| Grime | grime |
| Hard Dance / Hardcore / Neo Rave | hard dance |
| Breaks / Breakbeat / UK Bass | breakbeat |
| UK Garage / Bassline | UK garage |
| Trap / Future Bass | future bass |
| Bass / Club | bass |
| Hip-Hop | hip-hop |
| Ambient / Experimental | electronica |
| Tout le reste (Rock, Jazz, Pop...) | Autres genres |

---

## Ce qu'on attend du design

### 1. Palette de hues pour les 8-10 piliers
Attribuer un hue OKLCH distinct à chaque grande famille, en s'assurant qu'ils sont suffisamment espacés sur le cercle chromatique. Les piliers :

- **House** (~66 sous-genres) — actuellement 260 (violet)
- **Techno** (~32 sous-genres) — actuellement 320 (magenta)
- **Trance** (~22 sous-genres) — actuellement 352 (rose)
- **Drum & Bass** (~29 sous-genres) — pas de hue dédié
- **Hardcore** (~29 sous-genres) — pas de hue dédié
- **Dubstep** (~10 sous-genres) — pas de hue dédié
- **Breakbeat** (~13 sous-genres) — pas de hue dédié
- **Disco** (~11 sous-genres) — pas de hue dédié
- **UK Garage** (~8 sous-genres) — pas de hue dédié
- **Hard Dance** (~15 sous-genres) — pas de hue dédié
- **Autres genres** — gris neutre

### 2. Dégradés par profondeur
Utiliser le shade/lightness pour différencier les niveaux :
- Genre racine = teinte pure
- Sous-genre niveau 1 = léger décalage lightness ou chroma
- Sous-genre niveau 2+ = décalage plus marqué

### 3. Tags et cartes
- **StyleTag** : dot coloré + fond teinté selon le hue du pilier ancêtre
- **GenreCard** : mosaïque teintée avec les variations de lightness
- **GenreDetail hero** : même principe, plus grand

### 4. Contraintes techniques
- Tout en **OKLCH** (perceptuellement uniforme)
- Zéro couleur hardcodée — tout via `var(--...)`
- Doit fonctionner en **light + dark mode**
- Les tokens sont dans `diggy-tokens.css`
- La logique est dans `diggy-style-map.js` (fonction `styleTone()`)

---

## API taxonomy disponible

```
GET /api/taxonomy/stats                    → compteurs globaux
GET /api/taxonomy/roots                    → genres racines (72)
GET /api/taxonomy/nodes?q=house            → recherche par label
GET /api/taxonomy/nodes/{id}/children      → sous-genres directs
GET /api/taxonomy/nodes/{id}/parents       → parents directs
GET /api/taxonomy/nodes/{id}/ancestors     → chemin vers la racine
GET /api/taxonomy/nodes/{id}/descendants   → tous les descendants
GET /api/taxonomy/mappings                 → correspondance noms bruts → nœuds
```
