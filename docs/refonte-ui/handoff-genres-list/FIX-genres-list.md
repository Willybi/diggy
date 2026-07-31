# FIX — Genres (liste) `/genres` (D6 p.7)

> Round de revue design UNIQUE (Claude Design) sur le commit `b6b8a4f`. Implémentation
> jugée fidèle sur tout le structurant. 6 correctifs, 2 fichiers (`GenresView.vue`,
> `GenreCard.vue`), aucun composant partagé, aucun back. **Triage work-manager ci-dessous :
> les 6 sont ACCEPTÉS après vérification sur pièces (0 rejet).**

## Triage (verdict par écart)

| # | Écart | Tag | Verdict | Vérification faite |
|---|---|---|---|---|
| 1 | Compteur de page faux en facette d'avis (« 75 / 75 » sur écran vide) | [spec] bloquant | **ACCEPTÉ** | Confirmé : `total` (75) reste le membre gauche en facette `liked`/`disliked` (filtrage client dans `displayItems`). `shownCount` = `displayItems.length` en facette, `total` sinon. |
| 2 | Copy empty « Disliked » dit « pouce » alors que le glyphe est un cœur barré | [spec] bloquant | **ACCEPTÉ** | Incohérence réelle : l'agent avait corrigé l'icône (cœur barré) mais pas le texte (héritage de l'hypothèse « pouce » du brief). |
| 3 | Avis épinglé estompé par `opacity:.45` de la card disliked | [visuel] bloquant | **ACCEPTÉ** | Vrai : `opacity` d'un ancêtre ne peut être annulée par un descendant → la faire descendre sur `.gc-tile/.gc-scrim/.gc-avatars/.gc-body`, **jamais** sur `.gc-acts`/`.gc-play`. |
| 4 | Signature tronquée en cours d'unité (« 70–145 B… ») en 2-col mobile | [visuel] | **ACCEPTÉ** | C'était le point ouvert soumis à la revue. Repli 2 lignes sous 219px (pilier / `70–145 BPM`), séparateur masqué. `row-gap` en `var(--space-05)` (= 2px) plutôt qu'un hardcode. |
| 5 | `.btn-admin` réinvente un bouton (34px hors-échelle + hover `--accent`) | [spec] | **ACCEPTÉ** | `.btn` partagé est **neutre** (`--surface`/`--ink-2`/`--line-2`, hover `--surface-2` sans accent) ; `.btn--sm` = 32px on-scale. Préserver le `:disabled{opacity:.5}` (absent de `.btn`) en scopé + retarget du repli mobile sur `.admin-block .btn`. |
| 6a | `.sub` `--ink-2` → `--ink-3` | [spec] | **ACCEPTÉ** | Le brief head donnait le compteur en `--ink-3` (métadonnée de 2ᵉ plan). Token existant. |
| 6b | `.admin-label` `border-radius: 4px` → `--r-xs` | [spec] | **ACCEPTÉ** | 4px hors échelle ; `--r-xs` = 6px (plus petit rayon de l'échelle). Changement mineur 4→6px. |
| 6c | `.titles h1` `600 --fs-xl` → `700 --fs-lg` | [spec] | **ACCEPTÉ (convention repo confirmée)** | Vérifié : Sets/Playlists/Explorer/Radar = `700 --fs-lg` ; Artists = `600 --fs-xl` (**outlier pré-existant**, hors périmètre). `--fs-lg` (22px) est commenté « view titles » dans les tokens. Genres s'aligne sur la **majorité**, pas sur Artists. |
| 6d | `.more` (+N) `--overlay-soft` → `--overlay-modal`, padding `--space-15` | [visuel] | **ACCEPTÉ** | `--overlay-soft` (0.42) sur scrim 0.76 ne détache pas la pastille (constaté capture 06 : « +4 052 » flotte). `--overlay-modal` (0.72) la détache. Tokens existants. |

**Aucun rejet.** FIX propre et bien argumenté. Restylage `:deep()` depuis `.gc-acts`, cibles 30px, glyphe cœur barré, segments teintés `--pos`/`--neg`, body en `--pad` : **validés par la revue**, ne pas toucher.

## Résidus notés (hors périmètre de ce lot)
- **ArtistsView** titre en `600 --fs-xl` = outlier vs le reste des listes (`700 --fs-lg`) → à aligner lors d'un futur passage sur `/artists`, pas ici.
- Cible tactile 30px des boutons d'avis (`LikeDislike` partagé) + `title` par segment (`SegFilter` partagé) : limites de composants partagés, à traiter au niveau du composant, notées dans TRANSVERSE.
