# R1-ST1 — Tokens responsive

Tu dois ajouter les tokens responsive dans le design system de Diggy. C'est la fondation pour tout le chantier mobile R1.

Lis `CLAUDE.md` a la racine pour les conventions du projet.

---

## Contexte

L'app est desktop-only. On ajoute le responsive mobile (breakpoint principal 640px). Avant de toucher les composants, il faut poser les tokens CSS qui seront consommes par tout le reste.

Le brief designer est dans `_design/handoff-mobile/BRIEF-mobile.md`. Les decisions DA sont figees.

---

## Ce qui existe deja

**Fichier** : `server/frontend/src/styles/diggy-tokens.css`

Tokens layout existants (`:root`, lignes 119-126) :
```css
/* ---- density (table row height + base padding) ---- */
--row-h: 56px;
--pad: 16px;

/* ---- layout constraints ---- */
--page-max-w: 1400px;
--detail-max-w: 1080px;
--sidebar-w: 232px;
```

Il n'y a **aucun token responsive** : pas de breakpoints, pas de padding mobile, pas de hauteur bottom nav, pas de taille min tactile.

Le meta viewport est deja correct dans `server/frontend/index.html` :
```html
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
```

---

## Tache

Ajouter un bloc de tokens responsive dans `:root` de `diggy-tokens.css`, apres le bloc layout constraints existant (ligne 126).

### Tokens a ajouter

```css
/* ---- responsive (mobile) ---- */
--bottom-nav-h: 56px;
--page-px: 30px;
--page-px-mobile: 16px;
--touch-min: 44px;
```

Explication :
- `--bottom-nav-h` : hauteur de la BottomNav mobile (56px, cf. brief §a)
- `--page-px` : padding horizontal des pages (30px, valeur deja utilisee en dur partout — on l'explicite)
- `--page-px-mobile` : padding horizontal sur mobile (16px, cf. brief §g)
- `--touch-min` : taille minimale des cibles tactiles (44px, cf. brief §f)

### Regles

- Ajouter les tokens **dans `:root`** uniquement (pas de variation dark/density)
- Ne pas modifier les tokens existants
- Ne pas toucher aux overrides `[data-theme='dark']` ni `[data-density]`
- Garder le commentaire de section clair et court

---

## Definition of Done

```bash
# Le fichier diggy-tokens.css contient les 4 nouveaux tokens
# Les tokens existants sont inchanges
# Le theme dark et les variantes density ne sont pas modifies
# Lint frontend passe :
cd server/frontend && npm run lint
```

## Commit

```
feat(frontend): add responsive tokens for mobile (R1-ST1)
```

Ne pousse PAS sur master — je review avant.
