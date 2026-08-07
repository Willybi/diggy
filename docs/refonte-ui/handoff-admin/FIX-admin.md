# FIX — Admin `/admin` · Revue post-implémentation (annoté work_manager)

Round unique Claude Design (07/08). Verdict global : **implémentation fidèle sur la structure** (A1, A2, A5, A8/A9, A10, A12 conformes). 7 écarts + 2 réponses aux questions. Triage ci-dessous : chaque écart **vérifié contre le code** (+ mesures CDP prod pour V1/V4) avant acceptation ; convention repo prime sur le pilote.

## Accepté (lot correctif)

| # | Tag | Écart | Verdict de triage |
|---|---|---|---|
| **V1** | visuel | Cartes « à jour » ne reculent pas assez | **Cause FAUSSE, intention retenue.** Mesuré CDP : `.oc-card--ok = --bg (oklch .198) sans ombre`, `.oc-card--backlog = --surface (oklch .238) + ombre` → A3 déjà codé, le fix « ajouter --bg/no-shadow » est un no-op. MAIS Δluminance 0,04 trop subtil (pire en light). → renforcer la récession des cartes à-jour, vérifier dark+light. |
| **V2** | visuel | Ligne de tête « - » sur cartes de logs Crawl | **Confirmé** (03). Fallback : tête = `cible` si non vide, sinon `task_type` (et on omet la rangée Type) ; jamais « - » en tête. |
| **V3** | visuel | Trou vertical avant le contexte (cartes à-jour) | **Accepté.** `min-height:42px` du slot compteur top-aligné → centrer le contenu à-jour dans le slot. |
| **V4** | visuel | Nombres du contexte « non groupés et non mono » | **PARTIEL.** Groupé = FAUX (mesuré : `"sur 71 359 manquantes"`, U+202F présent). Mono = VRAI (contexte en `Space Grotesk`/--font-ui). → mono sur les seuls nombres du contexte ; NE PAS toucher au regroupement. |
| **V7** | visuel | En-têtes de section coupés au bord droit à 375px (Crawl, Genres) | **Confirmé** (03, 05). Lot 1b a rendu la table responsive mais pas l'en-tête (titre+badge+filtres). → empiler l'en-tête <859px. |
| DLQ null | réponse | Redis injoignable rendu « À jour ✓ » = faux positif | **Accepté** (priorité 1). Régime `unknown` : `—` mono --ink-3 (pas de pastille verte), contexte « Redis injoignable », carte --bg + bordure --line-2, exclu du compte « N chantiers en attente ». |
| Ancrage onglet | réponse | Onglet actif hors-écran non ramené | **Accepté** (priorité basse). Uniquement sur changement **programmatique** (nav depuis une carte Aperçu), pas sur clic direct dans la barre. |

## Rejeté → versé aux reliquats (hors périmètre ou diverge de la convention)

| # | Écart | Motif du rejet |
|---|---|---|
| **V5** | « Rejeter » (set-flags) en variante danger au lieu de neutre | Styling **pré-existant** d'AdminSets (`.btn-reject`), non introduit par le chantier (Lot 1b = responsive-only). Point valable mais = évolution d'un composant existant hors périmètre. → reliquat. |
| **V6** | data-label : filet entre rangées + hybride inline/stacked | La grammaire **répliquée à l'identique d'AdminFlags** (stacked, sans filet, `td{border-bottom:none}`) était la consigne explicite. Ajouter filet+hybride diverge de la référence et créerait une incohérence avec AdminFlags (non touché). → reliquat **transverse** (à traiter sur AdminFlags+Crawl+Genres+Artists ensemble). |
| **S1** | set-flags groupes N-parties : en-tête « N parties » + chips homogènes + insécable % | Le brief était erroné (paire binaire), admis. Les suggestions portent sur le **rendu de contenu existant** d'AdminSets (hors scope responsive-only). Bon backlog produit. → reliquat. |

## Non retenu comme écart
- **V1 cause** : le CSS A3 réclamé est déjà présent (mesuré). Seule l'intention (récession) est renforcée.
- **V4 regroupement** : déjà fait (U+202F mesuré) — non touché.
