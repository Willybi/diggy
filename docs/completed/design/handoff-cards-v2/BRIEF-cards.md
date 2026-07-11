# BRIEF — Cards v2 (Genre + Artist)

> **Statut** : validé sur pilote.
> **Pilote de référence** : `Cards v2 (pilote).html` (toggles Thème · Corps · Fond artiste dans la barre).
> **Dépend de** : refonte couleurs genres v2 (`--hue-*`, `data-fam`, `--d`).

---

## Deux évolutions

1. **Corps bas teinté famille** (Genre **et** Artist) — la zone basse (nom + stats) prend la couleur du style au lieu du blanc neutre. L'identité famille n'est plus seulement dans le nom.
2. **Fond Artist = mosaïque de covers** des tracks de l'artiste (comme les Genres), avatar rond devant, voile famille. Fallback aplat coloré quand pas de pochettes.

---

## Tokens — ✅ déjà ajoutés dans `diggy-tokens.css`

```css
/* :root (light) */            /* [data-theme="dark"] */
--ct-l: 0.965; --ct-c: 0.030;  --ct-l: 0.268; --ct-c: 0.044;
--ct-line: oklch(0.30 0.02 70 / 0.10);   --ct-line: oklch(1 0 0 / 0.07);
```
Corps teinté = `background: oklch(var(--ct-l) var(--ct-c) var(--th));`
`Autres` (`data-fam="autres"`) force `--ct-c:0` → corps gris (déjà géré par le sélecteur famille).

---

## 1. Corps teinté — `GenreCard.vue` & `ArtistCard.vue`

```css
.card-body { background: oklch(var(--ct-l) var(--ct-c) var(--th)); }
/* séparateur intra-corps sur fond teinté */
.cb-stats, .a-stats { border-top: 1px solid var(--ct-line); }
```
- Le `--th` est déjà posé par `data-fam` sur la carte (système couleurs v2).
- Stats en `--ink` / `--ink-3`, label famille en `oklch(var(--tag-fg-l) var(--tag-fg-c) var(--th))`. Contraste AA vérifié light+dark (chroma corps basse exprès).
- **Genre** : la mosaïque de covers du haut reste **brute / inchangée**. Seul le corps change.

---

## 2. Artist art — mosaïque covers + avatar + voile

Zone haute (`.a-art`, hauteur ~186px) :
```
.a-art
 ├─ .mosaic  (4 covers tracks de l'artiste — réutilise le composant Genre)
 ├─ .scrim   (voile : radial sombre haut + linéaire vers --th en bas)
 └─ .a-avatar (photo ronde 92px, centrée, ring var(--surface))
```
Voile (garde lisibilité avatar + fond vers la couleur famille pour fondre dans le corps) :
```css
.a-art .scrim {
  background:
    radial-gradient(120% 92% at 50% 22%, transparent 0%, oklch(0.12 0.02 262 / .34) 100%),
    linear-gradient(to bottom, transparent 30%, oklch(var(--ct-l) calc(var(--ct-c) * 4.2) var(--th) / .96) 100%);
}
```

### Fallback (pas de covers)
`tracks_with_artwork < 1` → classe `.fallback` sur `.a-art` : aplat famille (= comportement actuel), mosaïque + scrim masqués.
```css
.a-art.fallback { background: linear-gradient(155deg,
  oklch(var(--fb-l1) var(--fb-c1) var(--th)) 0%,
  oklch(var(--fb-l2) var(--fb-c2) var(--th)) 100%); }
/* light */  --fb-l1:.92; --fb-c1:.07; --fb-l2:.97; --fb-c2:.03;
/* dark  */  --fb-l1:.36; --fb-c1:.085; --fb-l2:.24; --fb-c2:.05;
/* autres */ --fb-c1:0; --fb-c2:0;
```

### Avatar (rappel A6)
- `has_artwork` → photo de profil.
- sinon → **initiales** sur fond teinté famille `oklch(var(--tag-bg-l) calc(var(--tag-bg-c)*.9) var(--th))`, `Autres` → `--surface-3` / `--ink-2`.

---

## Données attendues (API)

Par artiste, pour alimenter la carte :
- **4 covers de tracks** (les plus représentatives / récentes) avec artwork → mosaïque. Champ type `top_track_artworks[]`.
- `tracks_with_artwork` (count) → décide fallback.
- `has_artwork` (photo de profil) → avatar photo vs initiales.
- famille (déjà via taxonomy v2), `catalog`, `in_lib`, `liked`, `rating`, `in_bib`.

---

## Checklist
- [ ] Corps teinté Genre + Artist (light + dark, `Autres` = gris)
- [ ] Mosaïque covers Artist + voile + avatar centré
- [ ] Fallback aplat famille si pas de covers
- [ ] Avatar photo / initiales (A6)
- [ ] Séparateur stats en `--ct-line`
- [ ] Contraste stats AA sur teinte
- [ ] Hover carte (translateY + shadow-md) conservé
- [ ] Badges en-bib / rating / like inchangés
