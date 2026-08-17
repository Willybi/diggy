// D9.c — préchargement du CHUNK JS d'une route au survol / focus de la nav, pour
// qu'au clic la vue soit déjà (ou presque) chargée. Fabrique un prefetcher borné :
// chaque loader lazy `() => import()` n'est invoqué qu'UNE seule fois (dédup via un
// Set de chemins). Un échec ne remonte jamais (catch silencieux, cohérent avec la
// garde stale-chunk de `router.onError`) et libère la clé pour un futur essai.
//
// NB : on ne précharge QUE le chunk JS — aucune donnée, aucun appel API ici.
export function createChunkPrefetcher(loaderByPath) {
  const attempted = new Set()
  return function prefetchChunk(path) {
    const loader = loaderByPath.get(path)
    // Path inconnu / vue chargée en dur (pas de loader lazy) ou déjà tenté : no-op.
    if (!loader || attempted.has(path)) return
    attempted.add(path)
    Promise.resolve()
      .then(loader)
      .catch(() => {
        // La navigation réelle relancera le loader (et passera par la garde
        // stale-chunk) — on libère la clé pour ne pas bloquer un futur essai.
        attempted.delete(path)
      })
  }
}
