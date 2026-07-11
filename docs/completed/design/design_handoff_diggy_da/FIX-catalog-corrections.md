# Fix Catalog — 4 corrections (11 juin 2026)

## 1. Style tags vides — brancher le système de couleurs

La colonne STYLE est vide sur toutes les lignes. Chaque tag doit utiliser `styleTagClass(track.style)` depuis `diggy-style-map.js` et les CSS des familles doivent être chargés (`diggy-tokens.css` + `diggy-components.css`).

Si tu rends les tags en inline style plutôt qu'en classes :
```jsx
<span
  className="tag"
  style={{
    "--th": `var(--h-${slug(track.style)})`,
    "--ts": `var(--s-${slug(track.style)})`
  }}
>
  <span className="tdot" />{track.style}
</span>
```

Avec `slug` = `(n) => n.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")`.
Les vars `--h-*` / `--s-*` sont dans `diggy-tokens.css` pour les 14 styles.

---

## 2. BPM / Key / Durée / Rating tous à `—`

Les données existent en base mais ne s'affichent pas — les noms de champs sont probablement différents. Vérifier le mapping entre l'objet retourné par l'API et les colonnes :

| Colonne | Champ attendu (à adapter au vrai nom en base) |
|---|---|
| BPM | `track.bpm` → entier arrondi (`Math.round()`) |
| Key | `track.key` ou `track.musical_key` |
| Durée | `track.duration` ou `track.length` — format `m:ss`, `—` si null |
| Rating | `track.rating` ou `track.user_rating` (1–5) |

Règle : valeur absente/nulle → afficher `—` en `--ink-3`. **Jamais `0`, `0:00` ou `null`.**

---

## 3. LibDot — pastille sans fond circulaire

Le ✓ s'affiche mais sans le cercle de fond. Ajouter dans le CSS global :

```css
.lib-dot {
  display: inline-grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
}
.lib-dot svg { width: 12px; height: 12px; }
.lib-dot.in  { background: var(--pos-soft);  color: var(--pos-ink); }
.lib-dot.out { background: var(--surface-3); color: var(--ink-3);   }
```

---

## 4. Colonne « IN LI » tronquée

Donner une largeur fixe à la colonne :
```css
.track-table th:last-child,
.track-table td:last-child {
  width: 64px;
  text-align: center;
}
```
