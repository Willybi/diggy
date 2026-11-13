# Données indésirables : inventaire (2026-11-11)

**But.** Faire la liste de ce qui ne devrait pas se trouver dans la base Diggy (catalogue + artistes), avec des exemples réels, un volume et la porte d'entrée de chaque catégorie. On décidera **plus tard** comment les détecter et quoi en faire (masquer, exclure du scoring, supprimer, bloquer à l'entrée).

**Méthode.** Requêtes `SELECT` en lecture seule sur la prod, le 2026-11-11. Base : 1 138 249 lignes `catalog`, dont 369 172 créées depuis le 2026-10-01. Les volumes sont des **ordres de grandeur** : les motifs regex se recouvrent et ont des faux positifs (signalés plus bas). Rien n'a été écrit.

**Règle produit (William, 2026-11-11).** On ne garde que de la **musique**.
- Indésirable : émissions et podcasts, mixes continus, IA de masse, musique fonctionnelle (sommeil, spa, bruit), bruit non musical, faux artistes (label, genre, lieu, événement, émission, mot générique).
- Conservé : les reprises et hommages, et la musique hors genre club (classique, jazz, chanson, rap…).

---

## 1. Ce qui est en cause : trois portes d'entrée

L'essentiel du bruit ne vient pas de l'ingestion des sets ou des playlists, mais de **l'expansion par artiste**. Trois mécanismes s'enchaînent :

1. **Liaison set → artiste (C13.c)**. L'extracteur prend pour un DJ un mot du titre du set qui n'en est pas un : événement, lieu, émission, mot générique (cf. §3.1). Cet « artiste » accumule des sets, donc il entre dans la cohorte T1 (≥3 sets sur 12 mois).
2. **Backfill discographie (C14.a Ph2, `enrich_priority = 10`)**. Pour chaque artiste de la cohorte, on a aspiré **toute** la discographie de l'id Deezer associé. Or, sur un nom générique, l'id Deezer est souvent un **fourre-tout d'homonymes** : Deezer regroupe sous un même artiste des dizaines de vrais artistes différents qui portent le même nom, plus des fermes IA. Sur 155 919 titres issus du backfill, environ **52 800** appartiennent à des artistes d'un seul mot dont moins de 2 % des titres apparaissent dans un set.
3. **Veille des sorties (C14.a, `check_followed_artists` → `artist_activity`)**. Elle importe environ **22 000 titres par semaine**, à peu près tous liés à une ligne du catalogue. Elle s'auto-alimente : le seuil T2 est « ≥10 titres au catalogue », et ces titres viennent justement de la veille. Un artiste entré une fois grandit donc chaque semaine. Sur 30 jours, le haut du classement de la veille est fait de fermes de sommeil/BGM, de compositeurs classiques réédités en masse, de funk brésilien en singles et de fermes IA :

| Artiste (veille, 30 j) | Tier | Titres importés |
|---|---|---|
| Deep Sleep Music | 2 | 2 196 |
| Sleep-inducing BGM that will make you fall asleep… | 2 | 1 875 |
| Sleep recommended background music… | 2 | 1 846 |
| SLEEPY NUTS | 2 | 1 760 |
| Buzz BGM Lab | 2 | 988 |
| soul of NEKO Recommended Jazz | 2 | 772 |
| Lucy (ferme IA) | 2 | 576 |
| Olivia / Clara / Amal (fermes IA) | 1 | 491 / 302 / 300 |

Cohorte actuelle : 4 083 T1, 24 599 T2.

> **Conséquence.** Tant que les portes 1 à 3 restent ouvertes, tout nettoyage ponctuel se remplit à nouveau. Le traitement devra fermer l'entrée **et** nettoyer l'existant.

---

## 2. Catalogue : titres indésirables

### 2.1 Épisodes d'émissions radio et podcasts

Il s'agit d'épisodes d'émissions publiés sur Deezer comme des albums. Ils contiennent les morceaux diffusés **et** des segments parlés de 30 à 50 s : « Intro », « Coming Up », « Shout Outs », « Track Recap », « Radio News », « Welcome To Episode N ».

- **Cas Armin van Buuren** : 2 270 titres. 1 443 (64 %) viennent d'albums « ASOT NNN - A State Of Trance Episode NNN », et 1 166 durent moins de 90 s. Exemples : `A State Of Trance (ASOT 974) (Coming Up, Pt. 1)` (40 s), `A State Of Trance (ASOT 1003) (Shout Outs, Pt. 2)` (35 s), `Que Pasa (ASOT 977) [Tune Of The Week]`.
- **Ce n'est pas propre à Armin.** Séries trouvées dans les albums :

| Série | Albums | Titres |
|---|---|---|
| ASOT (+ Year Mix, Ibiza, Radio Top) | ~136 | ~2 920 |
| Defected Radio / Defected In The House Radio Show | ~159 | ~1 570 |
| FSOE (Future Sound of Egypt) | 13 | 277 |
| Toolroom Radio | 14 | 264 |
| Get Physical Radio | ~70 | ~660 |
| Group Therapy, FYH, Interplay Radio, Suanda Music, Uncharted Worlds, Glitterbox Radio, Rave! Code Radio, The Self Within… | — | ~1 300 |

- **Volume** : environ **7 100 titres** dans ~690 albums d'épisodes, selon le titre de l'album. C'est une borne basse, car le motif ne voit pas toutes les séries.
- **Nuance** : un épisode contient aussi de vrais morceaux, mais ce sont des **versions d'émission** (« (ASOT 977) », souvent tronquées ou mixées), pas l'enregistrement original.

### 2.2 Mixes continus et extraits « (Mixed) »

Il s'agit d'albums mixés (« Mixed by… », « Year Mix », « Live at Tomorrowland (Highlights) », Global Underground, In Search Of Sunrise…). Chaque piste est un **extrait** du mix, et non le morceau jouable.

- Exemples : `Song I Sing (Mixed)` (104 s), `Divino (Live) (Mixed)` (57 s), `Offshore (Mixed) (Interlude)` (45 s).
- **Volume** : ~4 600 titres dans ~740 albums mixés ; ~7 800 titres ont « (Mixed) » dans le titre, dont ~1 350 de moins de 2 min 30.
- **À discuter** : est-ce qu'un extrait mixé de durée normale reste acceptable comme doublon d'enregistrement ? Le §2.1 et le §2.2 se recouvrent largement.

### 2.3 Musique fonctionnelle

Sommeil, spa, méditation, bruit blanc, sons de nature, BGM « study/focus », berceuses.

- Exemples d'albums : `40 Soothing Melodies for Sleep & Relaxation`, `25 Relaxing Sounds of Nature - Relax & Relax, Healing Music…`, `50 Beautiful Tracks for Spa Relaxation`, `Lofi Vibes`.
- **Volume** : ~18 500 titres par motif sur le titre d'album (faux positifs possibles sur « chill out », « lofi », « study ») ; ~4 300 par motif sur le titre de piste ; ~530 « artistes » au nom fonctionnel (~5 400 titres).
- **En croissance** : c'est la catégorie qui grossit le plus vite via la veille (§1).

### 2.4 Compilations commerciales génériques

Par exemple `Rave Trance Dance Top 100 Best Selling Chart Hits`, `Psychedelic Trance EDM Top 100…`, `Workout…`. Ce sont souvent les mêmes morceaux, recompilés par des faux artistes de genre (§3.3).

- **Volume** : ~1 800 titres par motif « top 100 / best selling / chart hits / workout ».

### 2.5 Bruit non musical

- Intros, outros, interludes et skits de moins de 2 min : ~2 300.
- Segments parlés (« interview », « shout out », « track recap », « coming up », « voice over ») : ~870, dont la plupart sont en §2.1.
- Titres de remplissage (`Untitled`, `Track 1`, `ID`, `Unknown`…) : ~580.
- Effets sonores et sonneries : ~45.
- Livres audio ou chapitres (`Chapter N`, `Kapitel N`, `Teil N`) : ~600. **À vérifier**, car « Teil N » peut être un vrai morceau en plusieurs parties.
- Durée < 60 s, toutes causes : ~6 400. Durée > 20 min : ~1 350, en général des mixes entiers.

### 2.6 IA générée en masse

Elle se voit surtout au niveau de l'artiste (§3.4). Côté titres, les signes sont des albums de **25 pistes** publiés à la chaîne depuis fin août 2026, sans label, aux titres « mood » génériques (`I Want to Wake up Smiling`, `I See You in Every Crowd`, `Midnight Desire - Dark Romantic Trance`), ou en coréen pour Amal (`우리의 조용한 사랑의 온도`…).

---

## 3. Artistes indésirables (faux artistes)

### 3.1 Faux DJ extraits des titres de sets

L'extracteur C13.c a pris un mot du titre du set pour un DJ. Exemples (artiste → nombre de sets liés → exemple de titre) :

| Type | Artiste | Sets | Exemple de titre |
|---|---|---|---|
| Événement / festival | Thunderdome | 256 | `Thunderdome 2025 \| Slaughterhouse` |
| | Tomorrowland | 73 | `Tomorrowland 2026 \| Salvatore Ganacci` |
| Soirée / lieu | Section | 144 | `FJAAK - SECTION. - 20/05/26` |
| | Barcelona / BCN / Argentina / Miami | 40 / 29 / 32 / 28 | `Barcelona 13.05.26` |
| Émission | Breakfast | 102 | `Breakfast with Felix Joy - 14 October 2026` |
| | Patterns, Human, Trømmel, Jolene, EGE, Seven, Utopia, Paradise, Rewind | 29 à 54 | `Patterns 715`, `Human Mix 007 - DJ Bruce Lee`, `Utopia Presents with D'Cruz` |
| Mot générique | Channel, STUDIO, full, Summer, Time, Space, Bass, Arts, Fusion | 27 à 112 | `Studio Session \| BRUNA`, `[Cocoon] … (full recording)` |
| Lettre / sigle | A, S, A.T., Re, JK | 28 à 54 | `KHIDI Podcast 204: Ne/Re/A` |
| Genre | House Music | 111 | `House Music With Soul` |

- **Nuance** : certains sont de **vrais** artistes mal liés. Par exemple « Channel », lié aux sets « Behind The Iron Curtain With UMEK », ou « Antidote », lié à « Bruecke Invites ». À l'inverse, certaines émissions portent le nom de leur DJ (FLO, Macca, Moxie, Slam, Sasha, Gettoblaster) : le lien est alors juste. **Le nom seul ne suffit pas pour trancher.**
- **Effet secondaire** : ces faux DJ sont entrés en cohorte, et le backfill a aspiré l'homonyme Deezer correspondant. Exemples : Paradise 544 titres, Utopia 514, BCN 263, Breakfast 250, Summer 213, full 140.

### 3.2 Fourre-tout d'homonymes Deezer (le plus gros volume)

Ce sont des noms génériques ou des prénoms dont l'id Deezer regroupe des dizaines d'artistes distincts. Le backfill les a aspirés en entier.

- **Exemples** : Truth (1 257 titres), Frost (1 204 : métal suédois + house + BO de film), Paradox (1 135), Daniel (1 122), Tuesday (1 141 : albums `New Vol.2` à `New Vol.34`), Vertigo (1 115), HD (981 : rap US), Peter, Drop, Vito, More, Sanctuary, Signal, Glitch, Nocturne, Daydream, Vega, Komorebi, Null, -M-, T, Mamba…
- **Nora** (975) en est l'exemple le plus parlant : albums arabes, serbes, russes, japonais, indonésiens, afro, **et** des albums IA, sous un seul artiste.
- **Signature mesurable** : la plupart des titres sont arrivés après le 2026-10-01 via `enrich_priority = 10`, une part quasi nulle apparaît dans un set, et le nom est souvent d'un seul mot. Environ 52 800 titres du backfill correspondent à « un mot + <2 % en sets ».
- **Nuance importante** : le vrai artiste existe parfois et il faut le garder. Elle a 20 titres sur le label Annulled, Lucy 10 sur Stroboscopic Artefacts (vrai producteur techno). C'est **l'id Deezer** qui est pollué, pas forcément la ligne artiste.

### 3.3 Labels, genres et émissions enregistrés comme artistes

| Catégorie | Artistes | Titres | Exemples |
|---|---|---|---|
| Genre | 17 | ~5 700 | Chill Out (2 850), House Music (1 446), Phonk (424), Phonk Montagem (354), Deep House (339), Edm, House, Brazilian Phonk, Dance |
| Label / maison de prod | ~540 | ~5 650 | Authentic Records (790), Game Records (433), SoundMusic Original (426), Next Records, Club Marconex Records, Dynamic Music (997, musique d'illustration) |
| Fonctionnel | ~530 | ~5 400 | SLEEPY NUTS, Deep Sleep Music, Sounds of Nature Relaxation, Meditation Spa, Spa Music Collective |
| Émission | quelques dizaines | ~1 000+ | Get Physical Radio (661), Defected Radio (152), Aly & Fila FSOE Radio |
| Placeholder | 3 | 173 | Anonymous (114), ID (55), Traditional |

- **Faux positifs déjà repérés avec les motifs de nom** : Lil Baby et Baby Keem (motif « baby »), Radio Slave, Session Victim, The Radio Dept. et Swedish Radio Symphony Orchestra (motif « radio/session »). Ce sont de vrais artistes à garder.

### 3.4 Fermes IA

Ce sont des prénoms ou mots courts qui publient des dizaines d'albums de ~25 pistes par mois depuis fin août 2026, sans label, et qui sont entrés par la veille des sorties (`artist_activity`), pas par le backfill.

| Artiste | Titres | Albums récents | Porte d'entrée |
|---|---|---|---|
| Lucy | 1 467 | 76 en ~2 mois | veille (1 425) |
| Amal | 1 471 | 60 (titres coréens) | veille (1 458) |
| Clara | 1 155 | 52 | veille (1 152) |
| Isabella | 992 | 48 | veille |
| Olivia | 631 | 40 | veille |
| Azure | 571 | 51 | veille |
| Heaven | 327 | 41 | veille |
| Arya / Elle / Nora | 750 / 769 / 975 | 300 à 470 « albums » | mixte : backfill + veille, et fourre-tout d'homonymes |

- **Signature** : rafale d'albums très récents, ~25 pistes par album, pas de label, titres « mood » en anglais ou coréen, aucun lien de set réel, présence en T1/T2 due uniquement aux titres que la veille a elle-même importés.
- **Limite** : `albums.release_date` est vide pour 41 % des albums (renseigné surtout par l'enrichissement récent). Une mesure de cadence fondée sur ce champ n'est donc qu'indicative.

### 3.5 Fermes de singles de funk brésilien (à arbitrer)

MC GW (1 056 « albums » pour 1 314 titres), Mc Magrinho, Mc MN, Mc Vuk Vuk, Iraqui ZL, Tropa da W&S, Conexão do Funk et des dizaines d'autres : chacun ~150 à 1 000 singles d'environ 1 titre, publiés récemment en rafale, entrés par la veille.

- C'est **de la musique réelle**, mais publiée comme du spam : souvent des variantes d'un même morceau, avec des labels-fermes (Authentic Records, Game Records, SoundMusic Original…).
- **À arbitrer** : est-ce que c'est hors cible ? Selon la règle « on garde le hors genre », non, mais le volume est disproportionné.

---

## 4. Ce qui n'est PAS indésirable (à protéger)

- Les **vraies discographies profondes** d'artistes légitimes : Miles Davis (2 093), Dolly Parton (984), Louie Vega, Tiësto, David Morales, Björk, Cerrone… Ces titres apparaissent dans des sets et dans les bibliothèques.
- Le **classique** (Bach, Mozart, Beethoven, Chopin, Berliner Philharmoniker) : hors genre mais conservé. En revanche, la veille en importe beaucoup (rééditions en masse), ce qui pose une question de volume, pas d'appartenance.
- Les **reprises et hommages**.
- Le vrai artiste caché derrière un id Deezer pollué (Lucy, Elle…).

---

## 5. Pistes de signaux pour la phase « identifier » (non décidé)

Liste brute, à évaluer plus tard. Aucun signal n'est sûr seul : il faudra les combiner et vérifier par échantillon (invariant #4, mieux vaut séparer que corrompre).

- **Album** : titre d'album qui matche une émission, un épisode ou un mix ; ~25 pistes ; pas de label ; `record_type`.
- **Piste** : durée < 60 à 90 s, durée > 20 min, mots-clés de segment parlé, « (Mixed) », « (ASOT NNN) ».
- **Artiste** : ratio titres en sets / titres totaux ; part venue de `enrich_priority = 10` ou de `artist_activity` ; nom d'un seul mot ou prénom ; rafale d'albums récents ; diversité de langues des titres (fourre-tout d'homonymes) ; nom de label, genre ou émission (avec liste d'exceptions).
- **Deezer** : nombre de fans et nombre d'albums de l'id (non stocké aujourd'hui) ; flag « contenu IA » si l'API en expose un (à vérifier).
- **Porte d'entrée** : provenance de la ligne (backfill disco, veille, set, radar, bibliothèque). Un titre présent dans une bibliothèque ou un set est protégé par construction.

## 6. Questions ouvertes pour la suite

1. Pour un fourre-tout d'homonymes, faut-il dé-lier l'id Deezer, ne garder que les titres corroborés (set, bibliothèque, label connu), ou supprimer les titres orphelins ?
2. Les épisodes et extraits mixés : les masquer, les supprimer, ou les rattacher à l'enregistrement original ?
3. La veille des sorties : resserrer le critère T2 (ne pas compter les titres qu'elle a importés elle-même) ou ajouter un filtre à l'entrée ?
4. Les faux DJ extraits des titres : étendre la denylist média de C13 (`set_artist_media_denylist`) avec événements, lieux et mots génériques ?
5. Le funk brésilien en singles et le classique réédité en masse : hors cible ou simple plafond de volume ?

---

## 7. Pistes d'identification testées (2026-11-11)

Tests en lecture seule : requêtes `SELECT` sur la prod et API publique Deezer (`/artist`, `/album`). Rien n'a été écrit. « Corroboré » = titre présent dans un set **ou** une bibliothèque. Beatport **ne corrobore pas** : les fermes IA y ont aussi des correspondances (Amal 330, Lucy 377).

### 7.1 Résultat principal : un seul détecteur d'artiste couvre la plupart des catégories

Les fermes IA, les labels-fermes, le fonctionnel, les genres pris pour artistes, le funk en singles et les fourre-tout d'homonymes ont la même signature :
- presque rien de corroboré ;
- très peu de fans Deezer par album (`nb_fan / nb_album`, un appel `/artist` par artiste).

| Artiste | Fans / album | Corroborés |
|---|---|---|
| Miles Davis | 3 000 | 230 / 2 093 |
| Armin van Buuren | 4 500 | 220 / 2 261 |
| Nora | 2,8 | 1 / 975 |
| Elle | 1,4 | 35 / 769 |
| Amal | 8,6 | 11 / 1 471 |

**Batch complet** : tous les artistes avec ≥ 20 titres et < 5 % corroborés (1 605 artistes, ~162 000 titres). Récupérer les fans Deezer prend environ 7 minutes.

| Classe | Règle | Artistes | Titres | Lecture d'échantillon |
|---|---|---|---|---|
| Fort | fans/album < 5 | 966 | 76 400 | ~90 % indésirables ; faux positifs = classique |
| Fourre-tout | 5 à 100, dispersion ISRC ≥ 13 déclarants pour 100 titres | 276 | 42 100 | ~90 % ; rares faux positifs (PUFFY…) |
| Ferme veille | 5 à 100, ≥ 80 % des titres venus de la veille | 92 | 12 200 | la moitié est du **classique** (Sibelius, Mahler, orchestres) |
| À revoir | 5 à 100, autres cas | 137 | 19 600 | mixte (André Popp, House Music, Spa, Gallimard Jeunesse) |
| À revoir | 100 à 300 | 60 | 5 400 | mixte (Crescendo, SEGA, Pamela vs Tieum, Rachel Portman) |
| Légitime | ≥ 300 | 62 | 6 300 | légitime (In Flames, Mouloudji, Bach, Argerich) |

**Seuil sûr** : < 5 fans par album. Les artistes underground légitimes sont tous au-dessus de 10 (Optimo, Tom Furse, Harris Jayaraj). Les vrais DJ peu suivis mais corroborés (Gettoblaster, DJ Dextro, Demuir) ne sont jamais concernés, car la corroboration les protège.

**Garde-fou classique (obligatoire)** : un interprète classique a peu de fans par album sur Deezer. Le genre Deezer majoritaire de ses albums (`/artist/{id}/albums`, `genre_id = 98`) les repère : environ 5 % des artistes signalés sur un échantillon de 150. Au passage, `genre_id = 75` (musique brésilienne) étiquette le funk en singles, utile pour arbitrer cette catégorie.

**Signal de dispersion ISRC** : nombre de déclarants distincts (5 premiers caractères de l'ISRC) pour 100 titres. Il sépare bien un fourre-tout (Elle 28, Nora 19, Paradise 18, Truth 14) d'un vrai artiste (Armin 0,7, Miles Davis 1,8, André Popp 5). Les fermes ont au contraire une dispersion **faible** : un distributeur unique.

### 7.2 Au niveau du titre : retrouver le vrai artiste sous un id pollué

Pour un artiste signalé, on prend les **déclarants ISRC de ses titres corroborés** (« déclarants ancrés »). Ses titres sous d'autres déclarants sont suspects.

- **Amal** : 11 titres club en sets, tous chez `USYBL`, sont gardés ; les 1 460 titres de la ferme sont suspects. Même chose pour Lucy (37 gardés sur 1 467), Elle (49 sur 769), Nora (1 sur 975).
- **À n'appliquer qu'aux artistes signalés en 7.1.** Sur un vrai artiste, ça sort des rééditions légitimes : Miles Davis à 30 % de suspects, Armin à 1 %.

**Blocs ISRC 100 % ferme** : `GXLE*`/`GXLF*` = 9 609 titres, 0 en set, tous arrivés depuis le 23/09, répartis sur ~150 « artistes » (Amal, Lucy, Clara, Isabella, Olivia, G.Q., AMARA…). `KRB92` est du même type. Ce sont des candidats à un **blocage à l'entrée par préfixe ISRC**.
- Les autres blocs DIY (`QT*`, `QZ*`) hébergent aussi de vrais artistes (Surgeon, Teebs) : **pas utilisables**.

**Marqueur IA Deezer** : l'API publique n'en expose **aucun** (vérifié sur des albums de fermes : label `Independent`, 0 fan).

### 7.3 Épisodes d'émissions

| Piste | Résultat |
|---|---|
| Motif sur le titre d'album seul | ❌ ~25 % de faux positifs (« The Next Episode », « Episode 8 EP », « Live at Radio City Music Hall », BO HBO) |
| Série récurrente seule (même préfixe + numéro, ≥ 5 albums) | ❌ attrape surtout de **vraies séries de labels** à protéger (Speicher, Little Helpers, Whities, Klockworks, Compost Black Label) |
| **Série récurrente (≥ 3 albums) + vocabulaire d'émission dans le titre** | ✅ ~40 séries, **~7 600 titres**, aucun faux positif en lecture une fois les séries d'un seul album exclues (ASOT, Defected Radio, FSOE, Toolroom Radio, Group Therapy, FYH, Interplay, Suanda, Get Physical Radio, Glitterbox Radio…) |
| Segments parlés ASOT (`(ASOT nnn) (Coming Up / Track Recap / Shout Outs / Radio News / Interview…)`) | ✅ ~100 % |

### 7.4 Extraits mixés

- Le marqueur `(Mixed)` / `[Mixed]` / `(Mixed - <mois>)` dans le titre est fiable comme marqueur : **7 731 titres**.
- **Mais 1 966 sont dans des tracklists de sets** (TrackID les a identifiés sous cette version) : les supprimer casserait des sets.
- 46 % ont un **jumeau non mixé** chez le même artiste. La piste naturelle est de les rattacher à ce jumeau plutôt que de les supprimer.

### 7.5 Bruit non musical

| Piste | Résultat |
|---|---|
| Segments d'émission | ✅ (cf. 7.3) |
| `Untitled` / `Track N` / `ID` | ❌ **à abandonner** : ce sont surtout de vrais morceaux (Maria Somerville, Alan Fitzpatrick, Biscits ; 400 sur 578 sont en sets) |
| Durée < 45 s seule | ❌ **à abandonner** : beat tapes, interludes réels (Pink Siifu, Swarvy, Kalkbrenner, préludes de Chopin) |
| `Chapitre N` / `Kapitel N` | ⚠️ ~70 % de livres audio, presque tous chez des fourre-tout (Coop, Null, Jonathan) : déjà couverts par 7.1 + 7.2 |
| Mots-clés « skit » / « interview » hors émission | ⚠️ des interludes de vrais albums rap, à exclure du motif |

### 7.6 Faux DJ extraits des titres de sets

Test sur les 300 artistes liés à ≥ 20 sets. Deux signaux :
- **own %** : part de ses sets où il joue au moins un de ses propres titres ;
- **co-lien** : part de ses sets où un autre DJ est aussi lié.

| Piste | Résultat |
|---|---|
| Co-lien seul | ❌ un vrai hôte d'émission est co-lié à ses invités (Umek 97 %, Adam Beyer 90 %) |
| own % ≈ 0 seul | ⚠️ ~50 % : beaucoup de vrais DJ sans productions (Gilles Peterson, Palms Trax, Ivan Smagghe, Karotte, Moxie, FLO, Macca) |
| **own % < 3 et co-lien ≥ 70 %** | ✅ 63 candidats, ~90 % de faux (Channel, Thunderdome, Time, Patterns, Section, Tomorrowland, Barcelona, Miami, Tokyo, STUDIO, House Music, Glitterbox Radio…). Faux positifs : Bill Brewster, Mike Servito, Jim Hopkins, Yasmin, Melvo Baptiste |

- **Pour trancher** : le tri structurel produit une liste courte, mais la décision finale demande de reconnaître le mot. Une liste fixe de villes, jours et saisons, genres et événements en couvre la moitié (Barcelona, Miami, Tokyo, New York, Sunday, FRIDAY, Summer, NYE, Jazz, ebm, Future Disco, Tomorrowland, Time Warp, Festival). Le reste passe par une classification LLM + web, sur le modèle de la denylist média de C13 (invariant #5 respecté : le LLM classe, il n'écrit pas en base).
- **Trouvaille annexe** : « Adam Beyer » existe en **deux lignes artiste** distinctes (92 et 87 sets). C'est un doublon à fusionner.

### 7.7 Pistes écartées

- **Nom = label** (le nom de l'artiste est un label utilisé par ≥ 5 autres artistes) : ❌. Beaucoup de vrais artistes ont leur propre label (Kerri Chandler, Justice, Fjaak, Amotik, Seb Wildblood, Edit Select, Matador). Les labels-fermes (Authentic Records, Club Marconex, OCD F42) sont déjà pris par 7.1.
- **Nom = genre** (correspondance avec le graphe de genres) : ⚠️ 53 artistes / 3 600 titres, mais un faux positif net (Kraftwerk), et la règle rate Chill Out, Phonk et Dance Music (absents du graphe). Elle n'est utile que comme **étiquette** après 7.1.
- **Mots-clés fonctionnels** (sleep, relax, spa, focus, lofi…) dans le nom d'artiste ou d'album : ❌ beaucoup de faux positifs (Sub Focus, Sleep D, sleeparchive, Doc Sleep, albums « Sleepless » ou « Focus EP »). Utile seulement comme **étiquette** après 7.1.

### 7.8 Porte 3 : l'emballement de la veille, mesuré

Sur 24 393 artistes T2 sans surcharge admin, 17 469 y sont uniquement grâce au critère « ≥ 10 titres au catalogue ». **4 416** d'entre eux retombent sous 10 si l'on ne compte pas les titres importés par la veille ou par le backfill discographie. Ne compter que les titres « organiques » (sets, playlists, bibliothèque, enrichissement de tracklist) fermerait la boucle sans toucher aux artistes réellement présents dans l'écosystème DJ.

### 7.9 Synthèse

| Catégorie | Piste retenue | Précision observée | Volume |
|---|---|---|---|
| Fermes IA, labels-fermes, fonctionnel, genres, funk singles, fourre-tout | 7.1 artiste (corroboration < 5 % + fans/album) + garde-fou classique | ~90 % | ~1 300 artistes / ~130 000 titres, plus ~200 artistes à revoir |
| Vrai artiste sous id pollué | 7.2 déclarants ISRC ancrés | bonne sur les cas connus | — |
| Ferme de distributeur | blocs ISRC `GXLE*`/`GXLF*`/`KRB92` | 100 % (0 en set) | ~10 000 titres |
| Épisodes radio | 7.3 série récurrente + vocabulaire | ~100 % en lecture | ~7 600 titres |
| Extraits mixés | 7.4 marqueur `(Mixed)` → rattacher au jumeau | 100 % (marqueur) | 7 700 titres, dont 2 000 en sets |
| Faux DJ | 7.6 structurel → liste de mots + LLM | ~90 % sur la liste courte | ~60 à 130 artistes |
| Porte 3 (veille) | ne compter que les titres organiques dans T2 | — | 4 416 artistes T2 |

**Pour la phase « qu'en faire »** :
- La classe « fort » et les blocs ISRC sont assez sûrs pour une action **réversible** (masquer ou exclure du scoring), après relecture d'un échantillon.
- Les classes « à revoir » et les faux DJ demandent une relecture humaine ou LLM.
- Aucune piste n'est assez sûre pour une suppression aveugle (invariant #4).

## 8. Filtre « fort » appliqué en lecture seule (2026-11-11)

Le filtre « moins de 5 % de titres corroborés et moins de 5 fans Deezer par album » donne **966 artistes**, soit **62 021 titres distincts**. Ce n'est qu'un calcul : rien n'a été écrit en base, car aucun mécanisme de masquage n'existe encore.

La liste complète est dans `filtre-fort-966.tsv`. Colonnes : id, nom, deezer_id, titres, corroborés, veille, backfill, tier cohorte, fans/album, genre Deezer majoritaire, part de ce genre.

### 8.1 Découpage du filtre en sous-ensembles

Le filtre global ne doit pas recevoir un traitement unique. Il se découpe en 5 sous-ensembles :

| Sous-ensemble | Artistes | Titres | Traitement proposé |
|---|---|---|---|
| Tier 1 de la cohorte (fourre-tout homonymes : Komorebi, Tunnel, Es, Coop, MIchi…) | 148 | 34 490 | Traitement **au titre**, pas à l'artiste : garder les titres des déclarants ancrés (§7.2), écarter le reste |
| Funk brésilien (genres Deezer 169 Soul & Funk + 75) | 278 | 16 842 | Ta décision. De la vraie musique, mais une masse hors cible (88 titres corroborés) |
| Classique (98) | 26 | 1 005 | **Garde-fou** : sortir du filtre (musique hors genre conservée) |
| Jazz (129) | 16 | 1 055 | **Garde-fou** : vrais musiciens (Joe Morris, Mat Maneri, Taylor Ho Bynum) mêlés à du piano d'ambiance, à relire |
| Reste net (électro, rap, pop, ambiance, fonctionnel…) | 500 | 23 566 | Action réversible directe après échantillon |

Le tier 1 porte la moitié des titres du filtre. Ces artistes sont en tier 1 parce que l'extracteur C13 a lié leur nom générique à au moins 3 sets (faux DJ, §7.6). C'est le même effet boule de neige : on ne peut pas les masquer en tant qu'artistes sans masquer aussi leurs quelques titres légitimes.

### 8.2 Protections au titre, à appliquer dans tous les cas

Sur les 62 021 titres :
- **695** sont dans une tracklist de set et **11** dans une bibliothèque. On les garde toujours, même si l'artiste est signalé : la corroboration les protège.
- Aucun n'a d'avis, aucun n'est dans une collection.
- 26 953 sont co-crédités avec un artiste hors filtre, mais **ces co-artistes sont surtout du même bois** : « Chill Out » (1 634 titres en commun), « Phonk », « House Music », « Deep House », « Dance Music », des MC brésiliens. C'est une deuxième vague à attraper, pas une protection. Quelques vrais co-artistes existent (ex. King Tubby, 88 titres corroborés, 109 en commun) : un titre co-crédité avec un artiste ayant au moins 3 titres corroborés mérite une vérification (≈ 9 300 titres, dont la moitié en funk brésilien).

### 8.3 Ce qui reste hors du filtre artiste

- Bloc ISRC `GXLE`/`GXLF`/`KRB92` : 10 571 titres, dont seulement 1 883 dans le filtre. **Environ 8 700 titres en plus**, complémentaires.
- Les artistes au nom de genre (« Chill Out » 2 850 titres, « House Music » 1 446, « Phonk », « Deep House »…) : pas attrapés, car leur id Deezer est un fourre-tout qui a des fans. On les attrape en combinant le co-crédit avec le filtre (deuxième vague) et le tag nom = genre (§7.7).
- Épisodes (§7.3), « (Mixed) » (§7.4), faux DJ (§7.6) : règles indépendantes, inchangées.

## 9. Décisions et conception du masquage (2026-11-11)

**Décisions de William :**
- Le filtre « fort » s'applique, garde-fous classique et jazz inclus.
- Le funk brésilien attrapé par le filtre (278 artistes, 16 842 titres, 98 % entrés par la veille, médiane 0,09 fan par album) est traité **comme le reste**. Le funk corroboré n'est pas concerné.
- L'action retenue est un indicateur **réversible** « masqué », pas une suppression.

### 9.1 Modèle (une migration)

- `catalog.hidden_reason` (String, nullable ; NULL = visible) + `catalog.hidden_at`. Le motif porte l'identifiant de la règle (`farm_fort`, `isrc_block`, `episode`…), ce qui permet d'annuler règle par règle.
- `artists.hidden_reason` + `artists.hidden_at`, mêmes conventions.
- Le masquage est posé **titre par titre**, jamais déduit de l'artiste. Cela permet de traiter le tier 1 (fourre-tout homonymes) : l'artiste reste visible avec ses seuls titres légitimes.
- Règle unique pour tous les groupes (arbitrée au découpage, 2026-11-12, remplace le traitement propre au tier 1) : on masque les titres non corroborés dont le déclarant ISRC n'est pas ancré. Un titre co-crédité avec un artiste hors liste qui a au moins 3 titres corroborés est protégé. Un artiste de la liste ne protège jamais un autre artiste de la liste : on a mesuré 1 248 titres que cette protection aurait sinon laissé passer. L'artiste n'est masqué que s'il ne lui reste aucun titre visible, tier 1 compris. Le jazz (129) rejoint le classique (98) parmi les garde-fous.

### 9.2 Où l'exclusion s'applique

- **Lecture** : ajout de `hidden_reason IS NULL` dans `catalog_visible` / `catalog_visible_sql`, sauf si le lecteur possède le titre dans sa bibliothèque. Une seule modification couvre les ~17 chemins de lecture qui l'utilisent déjà (listes, recherche, détails, similarité, reco, radar).
- **Scoring hors prédicat** : `compute_trends` n'utilise pas `catalog_visible`, donc il faut y ajouter l'exclusion explicitement. À recenser au moment du code : les comptes agrégés, la co-occurrence de `similarity_service` et le pool des embeddings.
- **Artistes** : listes, recherche et détail d'artiste.
- **Cohorte de veille** : un artiste masqué n'est jamais candidat. Sa ligne de cohorte est supprimée au recalcul, comme un artiste qui sort sur signal pur, sauf si elle porte un override admin. `select_due_cohort_ids` l'ignore dans tous les cas. Le champ `artist_cohort.excluded` n'est **pas** utilisé : il reste réservé à l'admin (implémentation, 2026-11-12).

### 9.3 Couper l'effet boule de neige (prévention)

- Le signal `nb_catalog` de la cohorte ne compte plus les titres importés par la veille (`artist_activity.catalog_id`) ni par le backfill (`enrich_priority=10`) (§7.8 : 4 416 artistes T2 sortent).
- Bloc ISRC `GXLE`/`GXLF`/`KRB92` refusé à l'entrée (crawl de sorties et enrichissement), avec une liste de préfixes en configuration.
- Les drains d'enrichissement (Beatport, BPM, embeddings) ignorent les titres masqués, pour ne plus dépenser de CPU dessus.

### 9.4 Application

- Script OPS `scripts/quarantine_undesirables.py --rule <règle>`, lecture seule par défaut. Il affiche les compteurs et un échantillon. `--apply` écrit, après une sauvegarde de la base. Il peut être relancé sans effet de bord, et `--revert --rule <règle>` annule.
- Protections systématiques : un titre présent dans un set, une bibliothèque, un avis ou une collection n'est jamais masqué.
- Ordre de déploiement : migration + exclusions → script en lecture seule → relecture d'un échantillon → `--apply` par règle, en commençant par `farm_fort`.
