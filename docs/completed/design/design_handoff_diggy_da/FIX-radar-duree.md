# Fix Catalog — Radar + Durée (round 2)

## 1. RADAR — régression : plus qu'une seule ligne a un score

Avant les corrections précédentes, le Radar s'affichait sur toutes les tracks scorées.
Maintenant une seule ligne l'affiche. Le nom du champ a probablement été changé/cassé pendant le fix.

**À faire :**
Retrouve le nom exact du champ radar dans l'objet track retourné par l'API
(ex. `track.radar_score`, `track.radarScore`, `track.score`, `track.radar`…)
et rebranche-le. Le composant `ScorePill` attend un entier 1–10.

Règle d'affichage :
```js
// score présent et > 0 → ScorePill
// score absent, null, ou 0 → '—' en --ink-3
score && score > 0 ? <ScorePill score={score} /> : <span className="nd">—</span>
```

---

## 2. DURÉE — affiche `0:00` au lieu de `—`

La durée n'est pas nulle en base, elle vaut `0` (entier) ou `"0:00"` (string).
La condition `dur ?? '—'` ne catch pas les zéros.

**Fix :**
```js
// Remplacer :
{track.duration ?? '—'}

// Par :
{track.duration && track.duration !== '0:00' && track.duration !== 0
  ? track.duration
  : '—'}
```

Ou via une helper :
```js
const fmt = (v) => (!v || v === '0:00' || v === 0) ? '—' : v;
// utilisation : fmt(track.duration)
```

Règle générale : toute valeur falsy, zéro ou `"0:00"` → afficher `—` en `--ink-3`.
