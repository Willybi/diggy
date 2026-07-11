# FIX round 5 — Catalog (retours QA sur l'implémentation Vue)

> Comparé : `/catalog` en dev ↔ maquette `realign/Catalog (pilote).html` (mise à jour).
> 3 problèmes, du plus grave au plus léger. La maquette montre désormais la cible
> avec la **vraie taxonomie messy** de la prod.

---

## 🔴 1. Bug d'encodage Unicode (CRITIQUE — bloquant)

**Symptôme :** des séquences d'échappement s'affichent en texte brut partout :
- search → `Artiste ou titre\u2026` (doit être `Artiste ou titre…`)
- chip → `Radar \u2265 2` (doit être `Radar ≥ 2`)
- en-tête → `DUR\u00e9E` (doit être `Durée`)
- cellules vides → `\u2014` (doit être `—`)

**Cause probable :** un `\uXXXX` littéral stocké dans une string (double-échappement),
soit côté données (API/JSON sérialisé deux fois), soit côté template Vue
(ex. `'Artiste ou titre\\u2026'` au lieu du vrai caractère).

**Fix :**
- Écris les **vrais caractères** dans le source (`…`, `—`, `≥`, `é`) — fichiers en **UTF-8**.
- Pour les cellules vides, une seule constante : `const EMPTY = '—'` et affiche `value ?? EMPTY`.
- Si ça vient de l'API : c'est une **double-sérialisation JSON** à corriger côté back,
  PAS à patcher au rendu avec un `.replace(/\\u/…)`.
- Vérifie le `<meta charset="utf-8">` et l'encodage réel des fichiers `.vue`.

---

## 🟠 2. StyleTags qui débordent sur BPM (le « largeur de colonne »)

**Symptôme :** `Hard Dance / Hardcore / Neo Rave` et `Breaks / Breakbeat / UK Bass`
sortent du tag et chevauchent la colonne BPM.

**Cause :** tag en `white-space: nowrap` sans borne de largeur + colonne Style sans cap.

**Fix (voir maquette) :**
- StyleTag : **label court = 1er segment avant `/`** → `genre.split('/')[0].trim()`.
  `Hard Dance / Hardcore / Neo Rave` → **`Hard Dance`**. Genre complet en `title=""` (tooltip).
- Filet de sécurité CSS : `.style-tag { max-width:100%; }` + `.lbl { overflow:hidden; text-overflow:ellipsis; }`.
- Colonne Style en largeur fixe via `<colgroup>` (168px dans la maquette).

---

## 🟠 3. Le rainbow est revenu — palette à reborner

**Symptôme :** ~10 couleurs de tags (Electronica teal, Drum&Bass vert, Rock violet…),
plus une **incohérence** : `Nu Disco / Disco` en **orange** mais `Nu-Disco` en **rose**
(même genre, 2 orthographes, 2 couleurs).

**Cause :** arbitrage « garder une couleur par genre » → c'est exactement la dérive
qu'on réaligne. Et pas de normalisation des variants orthographiques.

**Fix (voir maquette — `styleTag()` + `SLUG_FAMILY`) :** palette **bornée à 5 tons** :

| Ton | Hue | Contenu |
|---|---|---|
| **House** | 268 (violet) | House, Deep/Tech/Afro House, Nu Disco, French Touch, UK House/Garage, Minimal/Deep Tech, Downtempo |
| **Techno** | 312 (magenta) | Hard Techno, Trance Techno, Melodic, Electro brut, Classic/Min., Hard/Dark |
| **Trance** | 352 (rose) | Psytrance, Psy-Trance, Trance (Main Floor), Hard Dance/Hardcore/Neo Rave |
| **Other** | 042 (ambre) | vrais genres hors-piste : Drum & Bass, Breaks/Breakbeat/UK Bass, Electronica, Rock |
| **Misc** | neutre gris | non-genres / bruit : DJ Tools, Mainstage, Dance / Pop, Misc. Tracks |

- **Normalisation par slug** : `slug('Nu-Disco') === slug('Nu Disco / Disco')` → même famille.
  Plus jamais 2 couleurs pour 1 genre.
- Idéalement, **centralise dans `diggy-style-map.js`** (déjà prévu pour ça) : ajoute la famille
  `Other` (ambre 42) et complète `FAMILY_MEMBERS` avec TOUS les genres prod.

### ⚠️ Décision à confirmer (willi)
Le bucketing de quelques genres limites est un choix : actuellement
**Hard Dance/Hardcore/Neo Rave → Trance (rose)** et **Trance Techno → Techno (magenta)**.
👉 Confirme ou corrige ces affectations limites, et **envoie la liste EXHAUSTIVE des genres prod**
pour qu'aucun ne tombe en gris « Misc » par défaut faute d'être mappé.

---

## ✅ Reste OK (ne pas toucher)
- Arbitrages de Claude Code validés : pagination conservée, debounce 250ms,
  `display:none` sur `<col>` ET `<th>/<td>`, pas de skeleton (texte mono OK pour l'instant).
- Sidebar rail 66px @900px, chute de colonnes, dark mode : conformes.

## Checklist de re-vérif
- [ ] Plus aucun `\u…` visible (search, chips, header, cellules vides) en light ET dark.
- [ ] Aucun StyleTag ne déborde sur BPM, même genre le plus long.
- [ ] Max 5 tons de tags ; `Nu Disco / Disco` == `Nu-Disco` (même couleur).
- [ ] Liste genres prod complète mappée (0 tag gris non-voulu).
