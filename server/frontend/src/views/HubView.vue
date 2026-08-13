<template>
  <div class="hub-page" :class="{ 'is-guest': !auth.isAuthenticated }">
    <!-- top bar -->
    <div class="hub-top">
      <span class="top-word" :class="{ hidden: isEmpty }"> <span class="glyph">D</span>Diggy </span>
      <div class="top-right">
        <template v-if="!auth.isAuthenticated">
          <button class="btn-login ghost" @click="$router.push('/login')">Créer un compte</button>
          <button class="btn-login" @click="$router.push('/login')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
              <path d="M10 17l5-5-5-5M15 12H3" stroke-linecap="round" stroke-linejoin="round" />
              <path d="M14 4h5a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-5" stroke-linecap="round" />
            </svg>
            Se connecter
          </button>
        </template>
        <span v-else class="top-user">
          <span class="av">{{ userInitial }}</span
          >{{ auth.user?.username }}
        </span>
      </div>
    </div>

    <!-- hub content -->
    <div class="hub" :class="{ 'is-empty': isEmpty }">
      <!-- hero (empty state) -->
      <div v-if="isEmpty" class="hub-hero">
        <div class="big-word"><span class="glyph">D</span><span class="w">Diggy</span></div>
        <div class="tag">
          Cherche un track, un set, un artiste, une playlist ou un genre — et écoute l'aperçu.
        </div>
      </div>

      <!-- search bar -->
      <div class="searchwrap" :class="{ focused: inputFocused }">
        <div class="scope" :class="{ open: scopeOpen }" v-click-outside="() => (scopeOpen = false)">
          <button class="scope-btn" @click="scopeOpen = !scopeOpen">
            <span class="scope-ic" v-html="currentScopeIconSvg"></span>
            <span class="lbl lbl-long">{{ currentScopeLabel }}</span>
            <svg
              class="chev"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M6 9l6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </button>
          <div class="scope-menu">
            <button
              v-for="s in scopes"
              :key="s.value"
              :class="{ on: scope === s.value }"
              @click="selectScope(s.value)"
            >
              <span class="ic" v-html="scopeIcons[s.value]"></span>
              <span class="ml">{{ s.label }}</span>
              <span v-if="!isEmpty" class="cnt">{{ scopeCount(s.value) }}</span>
            </button>
          </div>
        </div>
        <div class="search-field">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9">
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.2-3.2" stroke-linecap="round" />
          </svg>
          <input
            ref="inputEl"
            type="text"
            v-model="query"
            placeholder="Rechercher dans tout Diggy…"
            autocomplete="off"
            @focus="inputFocused = true"
            @blur="inputFocused = false"
          />
          <button
            v-if="query"
            class="clear-q"
            aria-label="Effacer la recherche"
            @click="clearSearch"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M6 6l12 12M18 6L6 18" stroke-linecap="round" />
            </svg>
          </button>
        </div>
      </div>

      <!-- essaie: search primers, right under the search bar (empty state) -->
      <div v-if="isEmpty" class="extras">
        <div class="ex-section">
          <div class="ex-label">Essaie</div>
          <div class="qsugs">
            <button v-for="s in suggestions" :key="s" class="qsug" @click="searchSuggestion(s)">
              <svg
                class="qsug-arrow"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                stroke-linecap="round"
                stroke-linejoin="round"
                aria-hidden="true"
              >
                <path d="M6 5v6.5a2 2 0 0 0 2 2h10" />
                <path d="M14 9.5l4 4-4 4" />
              </svg>
              {{ s }}
            </button>
          </div>
        </div>
      </div>

      <!-- discover shelves (below the fold): lazy-loaded so they leave the main
           chunk. Kept mounted but hidden during search (v-show → display:contents)
           so returning to the empty state shows the already-fetched shelves without
           a refetch. Guests never mount the auth-only reco/activity sections, so
           those never hit the network. -->
      <div v-show="isEmpty" class="hub-discover">
        <HubTrendsSection />
        <HubRecoSection v-if="auth.isAuthenticated" />
        <HubActivitySection v-if="auth.isAuthenticated" />
      </div>

      <!-- results (search state): lazy-loaded. HubView owns the search state and
           feeds the raw items in; the section owns the display sort + rendering. -->
      <HubSearchResults
        v-if="!isEmpty"
        :items="items"
        :total="total"
        :query="query"
        :loading="loading"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, defineAsyncComponent } from 'vue'
import api from '../utils/api.js'
import { useAuthStore } from '../stores/auth'
import { fmtNum } from '../utils/format.js'
import { scopes, scopeIcons } from '../components/hub/scopeIcons.js'
import ShelfSkeleton from '../components/hub/ShelfSkeleton.vue'

// Below-the-fold sections are lazy-loaded to keep the heavy shelf components
// (DiscoveryCard/ActivityAlbumCard/FamilyChips/SegFilter + Artwork) out of the
// main chunk that every entry route pays for. The lightweight ShelfSkeleton
// (main chunk) fills the space gracefully while a section chunk downloads.
const HubTrendsSection = defineAsyncComponent({
  loader: () => import('../components/hub/HubTrendsSection.vue'),
  loadingComponent: ShelfSkeleton,
})
const HubRecoSection = defineAsyncComponent({
  loader: () => import('../components/hub/HubRecoSection.vue'),
  loadingComponent: ShelfSkeleton,
})
const HubActivitySection = defineAsyncComponent({
  loader: () => import('../components/hub/HubActivitySection.vue'),
  loadingComponent: ShelfSkeleton,
})
const HubSearchResults = defineAsyncComponent(
  () => import('../components/hub/HubSearchResults.vue'),
)

const auth = useAuthStore()

// ── state ──
const query = ref('')
const scope = ref('all')
const scopeOpen = ref(false)
const inputFocused = ref(false)
const inputEl = ref(null)
const loading = ref(false)

const items = ref([])
const total = ref(0)
const totals = ref({})

// ── static data ──
const suggestions = ['house', 'disclosure', 'boiler room', 'techno', 'trance', 'deep house']

// ── computed ──
const isEmpty = computed(() => !query.value.trim())
const currentScopeLabel = computed(
  () => scopes.find((s) => s.value === scope.value)?.label || 'Tout',
)
const currentScopeIconSvg = computed(() => scopeIcons[scope.value] || scopeIcons.all)

// Per-scope result counts for the dropdown (search state only). `totals` carries
// track/artist/set/playlist/genre; « Tout » = their sum (already exposed as `total`).
function scopeCount(value) {
  return value === 'all' ? fmtNum(total.value) : fmtNum(totals.value?.[value] || 0)
}
const userInitial = computed(() => (auth.user?.username || '?')[0].toUpperCase())

// ── search ──
let debounceTimer = null

watch([query, scope], () => {
  clearTimeout(debounceTimer)
  if (!query.value.trim()) {
    items.value = []
    total.value = 0
    totals.value = {}
    return
  }
  debounceTimer = setTimeout(doSearch, 150)
})

async function doSearch() {
  const q = query.value.trim()
  if (!q) return
  loading.value = true
  try {
    const { data } = await api.get('/api/search', {
      params: { q, scope: scope.value, limit: 50 },
    })
    items.value = data.items || []
    total.value = data.total || 0
    totals.value = data.totals || {}
  } catch {
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

// ── helpers ──
function clearSearch() {
  query.value = ''
  nextTick(() => inputEl.value?.focus())
}
function focusInput() {
  nextTick(() => inputEl.value?.focus())
}
function selectScope(value) {
  scope.value = value
  scopeOpen.value = false
  focusInput()
}
function searchSuggestion(s) {
  scope.value = 'all'
  query.value = s
}

// ── click outside directive ──
const vClickOutside = {
  mounted(el, binding) {
    el.__clickOutside = (e) => {
      if (!el.contains(e.target)) binding.value()
    }
    document.addEventListener('click', el.__clickOutside)
  },
  unmounted(el) {
    document.removeEventListener('click', el.__clickOutside)
  },
}
</script>

<style scoped>
.hub-page {
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

/* ── top bar ── */
.hub-top {
  position: sticky;
  top: 0;
  z-index: 30;
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4) var(--page-px);
  background: color-mix(in oklab, var(--bg) 86%, transparent);
  backdrop-filter: blur(8px);
}
.top-word {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-weight: 600;
  font-size: var(--fs-md);
  letter-spacing: 0.2px;
  color: var(--ink);
  transition: opacity 0.2s;
}
.top-word.hidden {
  opacity: 0;
  pointer-events: none;
}
.top-word .glyph {
  width: 26px;
  height: 26px;
  border-radius: 8px;
  background: var(--accent);
  color: var(--on-accent);
  display: grid;
  place-items: center;
  font-weight: 700;
  font-size: var(--fs-base);
}
.top-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--space-25);
}

.btn-login {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  height: 38px;
  padding: 0 var(--space-4);
  border-radius: var(--r-sm);
  border: 0;
  background: var(--accent);
  color: var(--on-accent);
  font: 600 var(--fs-sm) var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
}
.btn-login:hover {
  background: var(--accent-hover);
}
.btn-login svg {
  width: 16px;
  height: 16px;
}
.btn-login.ghost {
  background: var(--surface);
  color: var(--ink-2);
  border: 1px solid var(--line-2);
}
.btn-login.ghost:hover {
  border-color: var(--ink-3);
  color: var(--ink);
}

.top-user {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  height: 38px;
  padding: 0 var(--space-15) 0 var(--space-3);
  border-radius: var(--r-pill);
  border: 1px solid var(--line);
  background: var(--surface);
  font: 500 var(--fs-sm) var(--font-ui);
  color: var(--ink-2);
}
.top-user .av {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--accent-soft);
  color: var(--accent-ink);
  display: grid;
  place-items: center;
  font: 600 var(--fs-xs) var(--font-mono);
}

/* ── hub ── */
.hub {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 0 var(--page-px) var(--space-10);
}
.hub.is-empty {
  justify-content: flex-start;
}
/* Transparent wrapper: when visible it collapses (display:contents) so the lazy
   discover sections behave as direct flex children of .hub, exactly like before
   the split; v-show toggles it to display:none during search. */
.hub-discover {
  display: contents;
}

/* ── hero ── */
.hub-hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: var(--space-25);
  padding: var(--space-15x) 0 var(--space-8);
}
.big-word {
  display: inline-flex;
  align-items: center;
  gap: var(--space-4);
}
.big-word .glyph {
  width: 54px;
  height: 54px;
  border-radius: 15px;
  background: var(--accent);
  color: var(--on-accent);
  display: grid;
  place-items: center;
  font-weight: 700;
  font-size: var(--fs-xl);
  box-shadow: var(--shadow-md);
}
.big-word .w {
  font: 600 var(--fs-hero)/1 var(--font-ui);
  letter-spacing: -1.2px;
}
.hub-hero .tag {
  font: 500 var(--fs-base)/1.5 var(--font-mono);
  color: var(--ink-3);
  max-width: 420px;
}

/* ── search bar ── */
.searchwrap {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  max-width: 720px;
  margin: 0 auto;
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-pill);
  box-shadow: var(--shadow-md);
  padding: var(--space-15) var(--space-2) var(--space-15) var(--space-15);
  transition:
    box-shadow 0.16s,
    border-color 0.16s;
}
.searchwrap.focused {
  border-color: var(--accent);
  box-shadow:
    var(--shadow-md),
    0 0 0 4px var(--accent-soft);
}

/* scope dropdown */
.scope {
  position: relative;
  flex: none;
}
.scope-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  height: 46px;
  padding: 0 var(--space-3) 0 var(--space-3);
  border-radius: var(--r-pill);
  border: 0;
  background: var(--surface-2);
  color: var(--ink-2);
  font: 600 var(--fs-sm) var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
}
.scope-btn:hover {
  background: var(--surface-3);
  color: var(--ink);
}
.scope-btn .chev {
  width: 14px;
  height: 14px;
  transition: transform 0.16s;
  color: var(--ink-3);
}
.scope.open .scope-btn .chev {
  transform: rotate(180deg);
}
.scope-btn .scope-ic {
  display: inline-flex;
  width: 16px;
  height: 16px;
  flex: none;
  color: var(--ink-2);
}
.scope-btn .scope-ic :deep(svg) {
  width: 100%;
  height: 100%;
}

.scope-menu {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  z-index: 40;
  min-width: 180px;
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-lg);
  padding: var(--space-15);
  display: none;
}
.scope.open .scope-menu {
  display: block;
}
.scope-menu button {
  display: flex;
  align-items: center;
  gap: var(--space-25);
  width: 100%;
  text-align: left;
  border: 0;
  background: transparent;
  color: var(--ink-2);
  font: 500 var(--fs-sm) var(--font-ui);
  padding: var(--space-2) var(--space-25);
  border-radius: var(--r-sm);
  cursor: pointer;
}
.scope-menu button:hover {
  background: var(--surface-2);
  color: var(--ink);
}
.scope-menu button.on {
  background: var(--accent-soft);
  color: var(--accent-ink);
}
.scope-menu button .ic {
  display: inline-flex;
  width: 18px;
  height: 18px;
  flex: none;
  color: var(--ink-3);
}
.scope-menu button .ic :deep(svg) {
  width: 100%;
  height: 100%;
}
.scope-menu button.on .ic {
  color: var(--accent-ink);
}
.scope-menu button .ml {
  flex: 1;
}
.scope-menu button.on .ml {
  font-weight: 600;
}
.scope-menu button .cnt {
  flex: none;
  font: 500 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-3);
}
.scope-menu button.on .cnt {
  color: var(--accent-ink);
}

/* search field */
.search-field {
  flex: 1;
  display: flex;
  align-items: center;
  gap: var(--space-25);
  padding: 0 var(--space-2);
  min-width: 0;
}
.search-field > svg {
  width: 20px;
  height: 20px;
  color: var(--ink-3);
  flex: none;
}
.search-field input {
  flex: 1;
  min-width: 0;
  border: 0;
  background: transparent;
  outline: none;
  font: 400 var(--fs-input) var(--font-ui);
  color: var(--ink);
}
.search-field input::placeholder {
  color: var(--ink-3);
}
.clear-q {
  flex: none;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  border: 0;
  background: transparent;
  color: var(--ink-3);
  cursor: pointer;
  display: grid;
  place-items: center;
}
.clear-q svg {
  width: 16px;
  height: 16px;
}
.clear-q:hover {
  background: var(--surface-2);
  color: var(--ink);
}

/* ── extras ── */
.extras {
  width: 100%;
  max-width: 720px;
  margin: var(--space-6) auto 0;
}
.ex-section {
  margin-bottom: var(--space-6);
}
.ex-label {
  font: 500 var(--fs-xs)/1 var(--font-mono);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-3);
  margin: 0 0 var(--space-3);
}

/* suggestions (Essaie) — pill with an inline « entrée » arrow glyph */
.qsugs {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-15);
}
.qsug {
  display: inline-flex;
  align-items: center;
  gap: var(--space-15);
  font: 500 var(--fs-sm) var(--font-mono);
  color: var(--ink-2);
  background: var(--surface-2);
  border: 0;
  border-radius: var(--r-pill);
  padding: var(--space-15) var(--space-3);
  cursor: pointer;
  transition:
    background 0.14s,
    color 0.14s;
}
.qsug:hover {
  background: var(--surface-3);
  color: var(--ink);
}
.qsug-arrow {
  width: 14px;
  height: 14px;
  flex: none;
  color: var(--accent-ink);
}

/* ── responsive — container queries ── */
@container app (max-width: 640px) {
  .hub,
  .hub-top {
    padding-left: var(--page-px-mobile);
    padding-right: var(--page-px-mobile);
  }
  .searchwrap,
  .extras {
    max-width: 100%;
  }
  .scope-btn .lbl-long {
    display: none;
  }
  .big-word .w {
    font-size: var(--fs-display);
  }
}
</style>
