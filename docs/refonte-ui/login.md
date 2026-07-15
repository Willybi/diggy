# Login — `/login`

Statut : ✅ figé — **laissée telle quelle**  |  Vue : `views/LoginView.vue`

## Décision
Page simple et saine : brand glyph « D » + « Diggy », titre « Connexion », bouton **Se connecter avec Google**, gestion d'erreur. Tokens respectés.

**On n'y touche pas** : le flow OAuth est **sensible** (Safari iOS / CSP `script-src 'self'` / cookie `auth_callback`) — cf. CLAUDE.md. Le risque d'une refonte dépasse le gain.

## Notes
- Les couleurs du **logo Google** (`#4285F4`…) sont hardcodées **volontairement** : asset de marque officiel → exception légitime à « zéro couleur hardcodée ».
- Le **glyph « D »** se mettra à jour avec le **logo global** (`<BrandLogo>`, [TRANSVERSE.md](TRANSVERSE.md) § Brand) — pas une refonte de cette page.
