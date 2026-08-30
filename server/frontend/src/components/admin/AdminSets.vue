<template>
  <!-- ── Flags en attente — Archétype C (D11) : cartes de groupes paginées ── -->
  <section class="sf-region">
    <div class="sf-head">
      <h2 class="sf-title">
        Flags en attente
        <span v-if="flagsTotal > 0" class="sf-count">{{ fmtInt(flagsTotal) }}</span>
      </h2>
      <span class="sf-eyebrow">Revue manuelle · 10 par page</span>
    </div>

    <div v-if="flagsLoading" class="sf-state">Chargement…</div>
    <div v-else-if="flagsError && flags.length === 0" class="sf-state sf-state--err">
      {{ flagsError }}
    </div>
    <div v-else-if="flags.length === 0" class="sf-empty">Aucun flag en attente.</div>
    <template v-else>
      <div class="sf-cards">
        <article v-for="flag in flags" :key="flag.id" class="sf-card">
          <div class="sf-card-head">
            <span class="sf-card-type">
              {{ flagTypeLabel(flag.flag_type) }} · {{ memberCount(flag) }} sets
            </span>
            <span v-if="flag.confidence != null" class="sf-card-conf">{{ confPct(flag) }}</span>
          </div>
          <div class="sf-members">
            <div v-for="(m, i) in visibleMembers(flag)" :key="i" class="sf-member">
              <span class="sf-member-pos">p. {{ i + 1 }}</span>
              <span class="sf-member-title">{{ m.title || '—' }}</span>
            </div>
            <button v-if="hiddenCount(flag) > 0" class="sf-more" @click="expandFlag(flag)">
              + {{ hiddenCount(flag) }} parties
            </button>
          </div>
          <div class="sf-foot">
            <div v-if="signalChips(flag).length" class="sf-chips">
              <span v-for="(c, i) in signalChips(flag)" :key="i" class="sf-chip">{{ c }}</span>
            </div>
            <div class="sf-actions">
              <button
                class="btn btn--sm"
                :disabled="flagLoadingIds.has(flag.id)"
                @click="rejectFlag(flag)"
              >
                Rejeter
              </button>
              <button
                class="btn btn--sm btn--accent"
                :disabled="flagLoadingIds.has(flag.id)"
                @click="attachFlag(flag)"
              >
                Attacher
              </button>
            </div>
          </div>
        </article>
      </div>
      <div v-if="flagsPageCount > 1" class="at-pager">
        <button class="btn btn--sm" :disabled="flagsPage <= 1" @click="flagsPrev">Précédent</button>
        <span class="at-pager-count">{{ flagsPage }} / {{ flagsPageCount }}</span>
        <button class="btn btn--sm" :disabled="flagsPage >= flagsPageCount" @click="flagsNext">
          Suivant
        </button>
      </div>
      <div v-if="flagsError" class="sf-state sf-state--err">{{ flagsError }}</div>
    </template>
  </section>

  <!-- ── Sets attachés — même carte C, détache par set ou par groupe ── -->
  <section class="sf-region">
    <div class="sf-head">
      <h2 class="sf-title">
        Sets attachés
        <span v-if="attachedTotal > 0" class="sf-count">{{ fmtInt(attachedTotal) }}</span>
      </h2>
      <span class="sf-eyebrow">Groupes · 10 par page</span>
    </div>

    <div v-if="attachedLoading" class="sf-state">Chargement…</div>
    <div v-else-if="attachedError && attached.length === 0" class="sf-state sf-state--err">
      {{ attachedError }}
    </div>
    <div v-else-if="attached.length === 0" class="sf-empty">Aucun set attaché.</div>
    <template v-else>
      <div class="sf-cards">
        <article v-for="grp in attached" :key="grp.id" class="sf-card">
          <div class="sf-card-head">
            <span class="sf-card-type">Groupe #{{ grp.id }} · {{ grp.sets.length }} parties</span>
            <button
              class="btn btn--sm"
              :disabled="detachGroupLoadingIds.has(grp.id)"
              @click="detachGroup(grp)"
            >
              Détacher le groupe
            </button>
          </div>
          <div class="sf-members">
            <div v-for="s in grp.sets" :key="s.id" class="sf-member attached-set">
              <span class="sf-member-title">{{ s.title || '—' }}</span>
              <button
                class="sf-detach"
                :disabled="detachLoadingIds.has(s.id)"
                title="Détacher"
                aria-label="Détacher"
                @click="detachSet(grp, s)"
              >
                <AdminIcon name="link-off" :size="15" />
              </button>
            </div>
          </div>
        </article>
      </div>
      <div v-if="attachedPageCount > 1" class="at-pager">
        <button class="btn btn--sm" :disabled="attachedPage <= 1" @click="attachedPrev">
          Précédent
        </button>
        <span class="at-pager-count">{{ attachedPage }} / {{ attachedPageCount }}</span>
        <button
          class="btn btn--sm"
          :disabled="attachedPage >= attachedPageCount"
          @click="attachedNext"
        >
          Suivant
        </button>
      </div>
      <div v-if="attachedError" class="sf-state sf-state--err">{{ attachedError }}</div>
    </template>
  </section>

  <!-- ── Artistes des sets — Archétype A (D4) : un job groupé ── -->
  <section class="aj-region">
    <div class="aj-head">
      <h2 class="aj-title">Artistes des sets <span class="aj-count">1</span></h2>
      <span class="aj-eyebrow">Idempotent</span>
    </div>
    <div class="aj-row">
      <div class="aj-body">
        <h3 class="aj-job-title">Lier artistes aux sets</h3>
        <p class="aj-job-desc">
          Parse les titres des sets pour trouver les artistes et les lier. Idempotent.
        </p>
        <p v-if="linkingSets" class="aj-running">
          <AdminIcon name="arc" :size="13" /> Job en cours…
        </p>
        <div v-else-if="linkSetsPairs.length || linkSetsError" class="aj-result">
          <span
            v-for="(p, i) in linkSetsPairs"
            :key="i"
            class="aj-pair"
            :class="`aj-pair--${p.channel}`"
          >
            <AdminIcon :name="channelIcon(p.channel)" :size="13" />
            <span class="aj-num">{{ fmtInt(p.value) }}</span>
            <span class="aj-lbl">{{ p.label }}</span>
          </span>
          <span v-if="linkSetsError" class="aj-fail">
            <AdminIcon name="alert-triangle" :size="13" />
            <span class="aj-fail-word">Échec</span>
            <span class="aj-fail-msg">{{ linkSetsError }}</span>
          </span>
        </div>
      </div>
      <div class="aj-action">
        <button class="btn btn--sm btn--accent" :disabled="linkingSets" @click="runLinkSets">
          {{ linkingSets ? 'En cours…' : 'Lier artistes aux sets' }}
        </button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { onMounted, ref, computed } from 'vue'
import api from '../../utils/api.js'
import { useTaskPoll } from '../../composables/useTaskPoll.js'
import AdminIcon from './AdminIcon.vue'

// Pagination SERVEUR (S1) : l'endpoint set-flags supporte déjà `limit`/`offset`.
// On charge UNE page de 10 à la fois (offset=(page-1)*10) et le badge affiche le
// `total` non paginé — la file au-delà de 50 n'est plus inatteignable.
const PAGE_SIZE = 10

function fmtInt(n) {
  return Number(n).toLocaleString('fr-FR')
}

// ── Ligne de résultat de job (D3) : paires icône/nombre/label, 3 canaux ──
const CHANNEL_ICON = { success: 'check', neutral: 'skip', error: 'alert-triangle' }
function channelIcon(ch) {
  return CHANNEL_ICON[ch]
}
function buildPairs(defs) {
  return defs.filter((d) => d.value != null && d.value !== 0)
}

// --- Flags en attente (Archétype C) ---
const flags = ref([])
const flagsTotal = ref(0)
const flagsLoading = ref(false)
const flagsError = ref('')
const flagLoadingIds = ref(new Set())
// Groupes dépliés (troncature D19 : > 6 membres → 6 rangées + « + N parties »).
const expandedFlagIds = ref(new Set())

function flagTypeLabel(type) {
  if (type === 'duplicate_candidate') return 'Doublon'
  if (type === 'part_candidate') return 'Parties'
  return type
}

// Normalise un flag en liste de membres : groupe (member_titles) sinon paire.
function flagMembers(flag) {
  if (flag.member_set_ids && flag.member_set_ids.length) {
    const titles =
      flag.member_titles && flag.member_titles.length
        ? flag.member_titles
        : flag.member_set_ids.map(() => '')
    return titles.map((title) => ({ title }))
  }
  return [{ title: flag.title_a }, { title: flag.title_b }]
}
function memberCount(flag) {
  return flagMembers(flag).length
}
function visibleMembers(flag) {
  const all = flagMembers(flag)
  if (expandedFlagIds.value.has(flag.id) || all.length <= 6) return all
  return all.slice(0, 6)
}
function hiddenCount(flag) {
  if (expandedFlagIds.value.has(flag.id)) return 0
  return Math.max(0, memberCount(flag) - 6)
}
function expandFlag(flag) {
  expandedFlagIds.value = new Set([...expandedFlagIds.value, flag.id])
}

// Confiance en % avec espace insécable avant le signe (grille d'audit).
function confPct(flag) {
  return `confiance ${Math.round(flag.confidence * 100)}\u00A0%`
}

// Chips de signaux homogènes (D11) : tous rendus de même nature.
function signalChips(flag) {
  const s = flag.signals || {}
  const chips = []
  if (Array.isArray(s.part_numbers) && s.part_numbers.length) {
    chips.push(`parts ${s.part_numbers.join(', ')}`)
  }
  if (typeof s.date_gap_days === 'number') {
    chips.push(`écart ${s.date_gap_days} j`)
  }
  if (typeof s.date_span_days === 'number' && s.date_span_days > 0) {
    chips.push(`plage ${s.date_span_days} j`)
  }
  return chips
}

// Pagination serveur des flags : `flags` EST la page courante (≤10), le nombre
// de pages dérive du `total` autoritaire.
const flagsPage = ref(1)
const flagsPageCount = computed(() => Math.max(1, Math.ceil(flagsTotal.value / PAGE_SIZE)))
function flagsPrev() {
  if (flagsPage.value > 1) {
    flagsPage.value -= 1
    loadFlags()
  }
}
function flagsNext() {
  if (flagsPage.value < flagsPageCount.value) {
    flagsPage.value += 1
    loadFlags()
  }
}

async function loadFlags() {
  flagsLoading.value = true
  flagsError.value = ''
  try {
    const offset = (flagsPage.value - 1) * PAGE_SIZE
    const { data } = await api.get(
      `/api/admin/set-flags?status=pending&limit=${PAGE_SIZE}&offset=${offset}`,
    )
    flags.value = data.items
    flagsTotal.value = data.total
  } catch (e) {
    flagsError.value = e.response?.data?.detail || 'Erreur chargement flags'
  } finally {
    flagsLoading.value = false
  }
}

// Après une action, recharge la page courante ; si elle devient vide (dernier
// item de la dernière page), recule d'une page et recharge.
async function reloadFlagsPage() {
  await loadFlags()
  if (flags.value.length === 0 && flagsPage.value > 1) {
    flagsPage.value -= 1
    await loadFlags()
  }
}

async function attachFlag(flag) {
  flagLoadingIds.value = new Set([...flagLoadingIds.value, flag.id])
  try {
    await api.post(`/api/admin/set-flags/${flag.id}/attach`)
    await reloadFlagsPage()
  } catch (e) {
    flagsError.value = e.response?.data?.detail || 'Erreur attach'
  } finally {
    const next = new Set(flagLoadingIds.value)
    next.delete(flag.id)
    flagLoadingIds.value = next
  }
}

async function rejectFlag(flag) {
  flagLoadingIds.value = new Set([...flagLoadingIds.value, flag.id])
  try {
    await api.post(`/api/admin/set-flags/${flag.id}/reject`)
    await reloadFlagsPage()
  } catch (e) {
    flagsError.value = e.response?.data?.detail || 'Erreur reject'
  } finally {
    const next = new Set(flagLoadingIds.value)
    next.delete(flag.id)
    flagLoadingIds.value = next
  }
}

// --- Sets attachés (détacher) ---
const attached = ref([])
const attachedTotal = ref(0)
const attachedLoading = ref(false)
const attachedError = ref('')
const detachLoadingIds = ref(new Set())
const detachGroupLoadingIds = ref(new Set())

// Pagination serveur des groupes attachés : `attached` EST la page courante.
const attachedPage = ref(1)
const attachedPageCount = computed(() => Math.max(1, Math.ceil(attachedTotal.value / PAGE_SIZE)))
function attachedPrev() {
  if (attachedPage.value > 1) {
    attachedPage.value -= 1
    loadAttached()
  }
}
function attachedNext() {
  if (attachedPage.value < attachedPageCount.value) {
    attachedPage.value += 1
    loadAttached()
  }
}

async function loadAttached() {
  attachedLoading.value = true
  attachedError.value = ''
  try {
    const offset = (attachedPage.value - 1) * PAGE_SIZE
    const { data } = await api.get(
      `/api/admin/set-flags?status=attached&limit=${PAGE_SIZE}&offset=${offset}`,
    )
    attachedTotal.value = data.total
    attached.value = data.items.map((flag) => ({
      id: flag.id,
      sets: (flag.member_set_ids
        ? flag.member_set_ids.map((id, i) => ({ id, title: flag.member_titles?.[i] || '' }))
        : [
            { id: flag.set_id_a, title: flag.title_a },
            { id: flag.set_id_b, title: flag.title_b },
          ]
      ).filter((s) => s.id != null),
    }))
  } catch (e) {
    attachedError.value = e.response?.data?.detail || 'Erreur chargement sets attachés'
  } finally {
    attachedLoading.value = false
  }
}

// Après un détachement, recharge la page courante ; si elle devient vide (dernier
// groupe de la dernière page), recule d'une page et recharge.
async function reloadAttachedPage() {
  await loadAttached()
  if (attached.value.length === 0 && attachedPage.value > 1) {
    attachedPage.value -= 1
    await loadAttached()
  }
}

async function detachSet(grp, s) {
  detachLoadingIds.value = new Set([...detachLoadingIds.value, s.id])
  try {
    await api.post(`/api/admin/sets/${s.id}/detach`)
    await reloadAttachedPage()
  } catch (e) {
    attachedError.value = e.response?.data?.detail || 'Erreur détachement'
  } finally {
    const next = new Set(detachLoadingIds.value)
    next.delete(s.id)
    detachLoadingIds.value = next
  }
}

// Détacher le groupe entier = détacher chaque membre via l'endpoint existant
// (aucun nouvel endpoint : le back est inchangé). Séquentiel, s'arrête au 1er
// échec en laissant le reste du groupe intact (invariant #4).
async function detachGroup(grp) {
  detachGroupLoadingIds.value = new Set([...detachGroupLoadingIds.value, grp.id])
  attachedError.value = ''
  // Détachement séquentiel : on compte les succès pour distinguer un échec
  // partiel (la boucle s'interrompt) d'un échec total, et le rapporter clairement.
  const total = grp.sets.length
  let detached = 0
  try {
    for (const s of [...grp.sets]) {
      await api.post(`/api/admin/sets/${s.id}/detach`)
      detached += 1
    }
  } catch (e) {
    // Échec partiel : les N premiers sont bien détachés (état persisté côté back),
    // seul le reste échoue — on nomme le compte au lieu d'un « échec » muet.
    const plural = detached > 1 ? 's' : ''
    attachedError.value = `${detached} détaché${plural} sur ${total} — réessayez (${
      e.response?.data?.detail || 'erreur détachement du groupe'
    })`
  } finally {
    const next = new Set(detachGroupLoadingIds.value)
    next.delete(grp.id)
    detachGroupLoadingIds.value = next
  }
  // Reflète l'état serveur (succès total OU partiel) sur la page courante.
  await reloadAttachedPage()
}

onMounted(() => {
  loadFlags()
  loadAttached()
})

// --- Lier artistes aux sets (Archétype A) ---
const linkingSets = ref(false)
const linkSetsResult = ref(null)
const linkSetsError = ref('')

const linkSetsPairs = computed(() => {
  const r = linkSetsResult.value
  if (!r) return []
  return buildPairs([
    { value: r.linked, label: 'liés', channel: 'success' },
    { value: r.skipped, label: 'déjà liés', channel: 'neutral' },
  ])
})

const linkSetsPoll = useTaskPoll((taskId) => `/api/admin/tasks/${taskId}`, {
  intervalMs: 2000,
  maxAttempts: 150,
  onData(st, { stop }) {
    if (st.status === 'done') {
      linkSetsResult.value = st.result
      linkingSets.value = false
      stop()
    } else if (st.status === 'error') {
      linkSetsError.value = st.error || 'Erreur'
      linkingSets.value = false
      stop()
    }
  },
  onError(err) {
    linkSetsError.value = 'Erreur polling: ' + (err.message || 'inconnue')
    linkingSets.value = false
  },
  onMaxAttempts() {
    linkSetsError.value = 'Timeout'
    linkingSets.value = false
  },
})

async function runLinkSets() {
  linkingSets.value = true
  linkSetsResult.value = null
  linkSetsError.value = ''
  try {
    const { data } = await api.post('/api/admin/sets/link-artists')
    linkSetsPoll.start(data.task_id)
  } catch (e) {
    linkSetsError.value = e.response?.data?.detail || 'Erreur'
    linkingSets.value = false
  }
}
</script>

<style scoped>
.sf-region,
.aj-region {
  container-type: inline-size;
}

/* ── Archétype C — région de cartes de groupes (D11) : cadre à bordure. ── */
.sf-region {
  margin-bottom: var(--space-8);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  overflow: hidden;
}
.sf-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  flex-wrap: wrap;
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--line);
}
.sf-title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font: 600 var(--fs-title)/1.2 var(--font-ui);
  color: var(--ink);
}
.sf-count {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--space-2);
  border-radius: var(--r-pill);
  background: var(--surface-3);
  color: var(--ink-2);
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.04em;
}
.sf-eyebrow {
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-3);
}

/* États (D17) : une ligne, à gauche, dans la région. */
.sf-state {
  padding: var(--space-4);
  font-size: var(--fs-sm);
  color: var(--ink-3);
}
.sf-state--err {
  color: var(--neg-ink);
}
.sf-empty {
  padding: var(--space-6);
  font-size: var(--fs-sm);
  color: var(--ink-3);
}

/* Pile de cartes. */
.sf-cards {
  padding: var(--space-3) var(--space-4);
}
.sf-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  overflow: hidden;
}
.sf-card + .sf-card {
  margin-top: var(--space-25);
}

/* En-tête de carte : type · N sets à gauche, confiance / action à droite. */
.sf-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  flex-wrap: wrap;
  padding: var(--space-2) var(--space-3);
  border-bottom: 1px solid var(--line);
}
.sf-card-type {
  font: 600 var(--fs-nano)/1.3 var(--font-mono);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.sf-card-conf {
  font: 500 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-2);
  white-space: nowrap;
}

/* Membres : rangées p. N + titre, filet entre membres. */
.sf-members {
  display: flex;
  flex-direction: column;
}
.sf-member {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
}
.sf-member + .sf-member,
.sf-more {
  border-top: 1px solid var(--line);
}
.sf-member-pos {
  flex: none;
  width: 34px;
  font: 500 var(--fs-xs)/1.3 var(--font-mono);
  color: var(--ink-3);
}
.sf-member-title {
  flex: 1;
  min-width: 0;
  font: 500 var(--fs-sm)/1.3 var(--font-ui);
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* Bouton-icône détacher : révélé au survol, --neg-ink au hover (D11). */
.sf-detach {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: 1px solid var(--line-2);
  background: var(--surface);
  border-radius: var(--r-xs);
  color: var(--ink-3);
  cursor: pointer;
  opacity: 0;
  transition:
    opacity 0.1s,
    color 0.12s,
    border-color 0.12s;
}
.sf-member:hover .sf-detach,
.sf-member:focus-within .sf-detach {
  opacity: 1;
}
.sf-detach:hover {
  color: var(--neg-ink);
  border-color: var(--neg-ink);
}
.sf-detach:disabled {
  cursor: default;
}
/* Rangée « + N parties » (troncature D19) : déplie le groupe sur place. */
.sf-more {
  width: 100%;
  padding: var(--space-2) var(--space-3);
  background: transparent;
  border-left: 0;
  border-right: 0;
  border-bottom: 0;
  text-align: left;
  font: 500 var(--fs-xs)/1.3 var(--font-mono);
  color: var(--ink-3);
  cursor: pointer;
}
.sf-more:hover {
  color: var(--ink);
}

/* Pied de carte : chips de signaux + actions. */
.sf-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  flex-wrap: wrap;
  padding: var(--space-25) var(--space-3);
  border-top: 1px solid var(--line);
}
.sf-chips {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
  min-width: 0;
}
.sf-chip {
  padding: 2px var(--space-15);
  background: var(--surface-2);
  border: 1px solid var(--line);
  border-radius: var(--r-xs);
  font: 500 var(--fs-xs)/1.3 var(--font-mono);
  color: var(--ink-2);
  white-space: nowrap;
}
.sf-actions {
  flex: none;
  display: flex;
  gap: var(--space-2);
}

/* ── Archétype A — région de job groupé (D4) : carte à bordure, sans ombre. ── */
.aj-region {
  margin-bottom: var(--space-8);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  overflow: hidden;
}
.aj-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-bottom: 1px solid var(--line);
}
.aj-title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font: 600 var(--fs-title)/1.2 var(--font-ui);
  color: var(--ink);
}
.aj-count {
  display: inline-flex;
  align-items: center;
  padding: 2px var(--space-2);
  border-radius: var(--r-pill);
  background: var(--surface-3);
  color: var(--ink-2);
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.04em;
}
.aj-eyebrow {
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--ink-3);
}
.aj-row {
  display: flex;
  align-items: flex-start;
  gap: var(--space-5);
  padding: var(--space-4);
}
.aj-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}
.aj-job-title {
  font: 600 var(--fs-title)/1.2 var(--font-ui);
  color: var(--ink);
}
.aj-job-desc {
  font: 400 var(--fs-sm)/1.4 var(--font-ui);
  color: var(--ink-2);
  text-wrap: pretty;
  max-width: 76ch;
}
.aj-action {
  flex: none;
}
.aj-running {
  display: flex;
  align-items: center;
  gap: var(--space-15);
  margin-top: var(--space-1);
  font: 400 var(--fs-xs)/1 var(--font-mono);
  color: var(--accent-ink);
}
.aj-result {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-3);
  margin-top: var(--space-15);
}
.aj-pair {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
}
.aj-pair--success {
  color: var(--pos-ink);
}
.aj-pair--neutral {
  color: var(--ink-2);
}
.aj-pair--error {
  color: var(--neg-ink);
}
.aj-num {
  font: 600 var(--fs-xs)/1 var(--font-mono);
}
.aj-lbl {
  font: 400 var(--fs-xs)/1 var(--font-ui);
  color: var(--ink-3);
}
.aj-fail {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  color: var(--neg-ink);
}
.aj-fail-word {
  font: 600 var(--fs-xs)/1 var(--font-ui);
}
.aj-fail-msg {
  font: 400 var(--fs-xs)/1.3 var(--font-mono);
  color: var(--ink-2);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  max-width: 340px;
}

.btn:disabled {
  opacity: 0.5;
  cursor: default;
}

/* ── Responsive — palier unique 859 px (D14/D18). ── */
@container (max-width: 859px) {
  /* En-têtes de région en pile. */
  .sf-head,
  .aj-head {
    flex-direction: column;
    align-items: stretch;
  }

  /* Pied de carte en pile, actions en column-reverse (Attacher au-dessus). */
  .sf-foot {
    flex-direction: column;
    align-items: stretch;
  }
  .sf-actions {
    flex-direction: column-reverse;
    width: 100%;
  }
  .sf-actions .btn {
    width: 100%;
    min-height: var(--touch-min);
    justify-content: center;
  }
  /* Détacher : cible tactile toujours visible. */
  .sf-detach {
    opacity: 1;
    width: var(--touch-min);
    height: var(--touch-min);
  }
  .sf-card-head .btn {
    min-height: var(--touch-min);
    justify-content: center;
  }

  /* Job en pile, bouton pleine largeur 44 px. */
  .aj-row {
    flex-direction: column;
    gap: var(--space-3);
  }
  .aj-action {
    width: 100%;
  }
  .aj-action .btn {
    width: 100%;
    min-height: var(--touch-min);
    justify-content: center;
  }
  .aj-fail-msg {
    max-width: none;
  }
}
</style>
