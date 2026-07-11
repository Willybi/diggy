# Handoff — Hub de recherche / Accueil `/`

Page d'accueil de Diggy = **hub de recherche transverse**, et **seule page accessible en non-connecté**.
Visiteur : cherche + écoute les aperçus 30s, sans deep-dive. Connecté : la même page déverrouillée + sidebar.

## Contenu
| Fichier | Rôle |
|---|---|
| `Hub de recherche (pilote).html` | **Maquette vivante.** Ouvre dans un navigateur. Barre de revue en haut : **Direction** (A retenue), **État** Visiteur/Connecté, thème, densité, largeur. |
| `BRIEF-hub.md` | Spec complète : moteur, gating, états, responsive, check backend. |
| `PROMPT-claude-code-hub.md` | **À coller à Claude Code.** Ancré sur le vrai code (`router.js`, `App.vue`, `auth.js`, `audioPlayer.js`, `dependencies.py`). |
| `diggy-tokens.css` / `diggy-style-map.js` | Tokens + mapping famille (la maquette les lit). |

## Décisions figées
- **Direction A « Spotlight »** (gros logo + barre centrée). B/C = exploration, **à ne pas coder**.
- Recherche transverse (tracks/artistes/sets/playlists/genres), liste mélangée + badge de type, scope par défaut = Tout.
- Gating visiteur : cap 6 résultats + lock row, clic fiche → `/login`, bib & tri masqués, **aperçu illimité**.
- Backend : nouvel endpoint **`/api/search` public** (`get_current_user_optional`), aucune migration.

## Comment lancer
1. Ouvre `Hub de recherche (pilote).html`, valide avec willi (toggles Direction / État).
2. Colle `PROMPT-claude-code-hub.md` à Claude Code dans `Willybi/diggy@master`.
3. Aller-retour si une question de design surgit.
