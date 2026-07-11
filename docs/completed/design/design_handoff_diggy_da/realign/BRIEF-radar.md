# Brief — Radar (pilote réaligné)

> Maquette : `realign/Radar (pilote).html` · Tokens : `realign/diggy-tokens.css`
> Cible Vue 3. ⚠️ **Refonte du modèle d'interaction**, pas qu'un réalignement visuel.

---

## Ce qui change vs la prod actuelle (décidé avec willi)

| Avant | Après | Raison |
|---|---|---|
| Onglets New / Seen / Added / Ignored | **Tous · New · Liked · Disliked** | Objectif = **reco**. « Seen » supprimé (pas pertinent). |
| « Added » | **Liked** | Signal positif pour la reco future |
| « Ignored » | **Disliked** | Signal négatif pour la reco future |
| Genre en texte brut qui wrap | **StyleTag DA** (palette bornée) | Cohérence avec Catalog |
| — | **Colonne Source** (playlist / set d'origine) | Voir d'où vient la track |
| — | **Colonne Détecté** (date relative) | Quand on l'a repérée |
| — | **Actions like / dislike** par ligne | Cœur du triage reco |

## Les onglets — MÀJ (validé avec willi sur l'implémentation)

- **Tous · Liked · Disliked** — l'onglet « New » est **supprimé**.
- Le filtre de récence **`24 h · 7 j · 30 j · 90 j · Tout`** (« Détecté depuis ») devient **global**
  (toujours visible, plus rattaché à un onglet) — il remplace l'intention « New ».
- ⚠️ **Tri par défaut = Détecté ↓** (plus récent en haut) : c'est lui qui porte l'idée « nouveautés »
  maintenant qu'il n'y a plus d'onglet New. À respecter.
- Tab actif : `--accent-soft`/`--accent-ink` ; Liked (`--pos-*`), Disliked (`--neg-*`). Compteur mono.

## Colonnes (table-layout fixed, comme Catalog)

| Col | Contenu | Notes |
|---|---|---|
| Play | bouton rond au hover | idem Catalog |
| Track | artwork + titre + artiste | ellipsis |
| Style | StyleTag (palette bornée) | **réutilise `diggy-style-map.js`** — mêmes couleurs que Catalog |
| Source | icône (playlist/set) + nom + label `PLAYLIST`/`SET` mono | `title` = nom complet, ellipsis. Icône en `--ink-2` (lisible), colonne 224px |
| Détecté | date relative **mono** (« il y a 2 h »), **tri par défaut desc** | porte l'intention « New » |
| BPM / Key | mono | **Key en `--accent-ink`** — gardé volontairement comme sur Catalog (cohérence inter-pages). Ne pas neutraliser sur Radar seul. |
| Avis | actions **dislike + like** | voir ci-dessous |

## Actions like / dislike (la mécanique reco)

- 2 boutons ronds par ligne, **révélés au hover** ; restent **visibles si engagés**.
- **Exclusifs** : liker retire le dislike et vice-versa ; re-cliquer annule (retour neutre).
- États de ligne : **liked** → fond `--pos` très léger (6%) ; **disliked** → ligne **estompée** (opacity .42).
- Couleurs : like = `--pos` / `--pos-soft` / `--pos-ink` ; dislike = `--neg-*`.

### 🔴 Lacune DA à formaliser — token `--neg`
La DA Wildflower **n'a aucune couleur négative**. J'ai dérivé en oklch un trio harmonisé
(hue 28, terracotta chaud, cohérent avec la prairie Wildflower), défini en haut du `<style>` de la maquette,
light + dark. **À valider par willi puis à intégrer dans `diggy-tokens.css`** comme `--neg / --neg-soft / --neg-ink`
(ça resservira partout : suppressions, erreurs, dislike).

## Responsive (container-queries sur `.app`)

| Largeur | Adaptation |
|---|---|
| ≤ 1180px | **Détecté** tombe |
| ≤ 1040px | **Key** tombe |
| ≤ 900px  | sidebar → rail 66px |
| ≤ 780px  | **BPM** tombe ; search pleine largeur |
| ≤ 640px  | **Source** tombe |
| ≤ 520px  | **Style** tombe ; compteurs d'onglets masqués |

→ Track + Avis survivent toujours (triage possible quelle que soit la taille).

## À fournir par willi
- **Liste exhaustive des genres prod** (`SELECT DISTINCT`) — finalise le mapping famille (commun à toutes les pages à StyleTags).
- Confirmer le **wording** : « Liked / Disliked » en anglais, ou « Aimés / Rejetés » en FR ? (reste de l'UI est FR)
- Le **tri par défaut** de chaque onglet (Détecté desc supposé).
- Valider le **token `--neg`**.
