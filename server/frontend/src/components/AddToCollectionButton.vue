<template>
  <div class="coll-add-wrap" :class="{ 'coll-add-wrap--icon': variant === 'icon' }">
    <!-- Icon variant (compact — cards/rows/player): disc button, glyph only. -->
    <button
      v-if="variant === 'icon'"
      ref="triggerRef"
      class="btn-coll-icon"
      :class="{ 'is-open': showDropdown }"
      type="button"
      :aria-label="title"
      :title="title"
      :aria-expanded="showDropdown ? 'true' : 'false'"
      @click.stop.prevent="toggleDropdown"
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.7"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <rect x="3" y="5" width="18" height="16" rx="2" />
        <path d="M12 10v6M9 13h6" />
      </svg>
    </button>

    <!-- Button variant (default — detail-view hero action bars): labeled. -->
    <button
      v-else
      ref="triggerRef"
      class="btn-coll"
      :class="{ 'is-open': showDropdown }"
      type="button"
      :aria-expanded="showDropdown ? 'true' : 'false'"
      @click.stop.prevent="toggleDropdown"
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.7"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <rect x="3" y="5" width="18" height="16" rx="2" />
        <path d="M12 10v6M9 13h6" />
      </svg>
      <span>{{ label }}</span>
    </button>

    <!-- Dropdown teleported to <body>: cards use overflow:hidden / container-type
         (which establish a containing block clipping an in-flow menu), and the
         PlayerBar is position:fixed at the bottom — a body-level fixed menu,
         positioned from the trigger rect, escapes all of that and can open up. -->
    <Teleport to="body">
      <div v-if="showDropdown" ref="menuRef" class="coll-dropdown" :style="menuStyle" role="menu">
        <div v-if="collLoading" class="coll-dd-state">Chargement…</div>
        <template v-else>
          <div v-if="!collections.length" class="coll-dd-state">Aucune collection</div>
          <button
            v-for="c in collections"
            :key="c.id"
            class="coll-dd-item"
            type="button"
            :disabled="c._added"
            @click="addToCollection(c)"
          >
            {{ c.name }}
            <span v-if="c._added" class="coll-dd-check">✓</span>
          </button>
          <div class="coll-dd-new">
            <input
              v-if="creatingNew"
              ref="newCollInput"
              v-model="newCollName"
              class="coll-dd-input"
              type="text"
              placeholder="Nom de la collection"
              @keydown.enter="createCollection"
              @keydown.esc="cancelNewColl"
              @blur="cancelNewColl"
            />
            <button v-else class="coll-dd-add" type="button" @click="startNewColl">
              + Nouvelle collection
            </button>
          </div>
        </template>
      </div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, nextTick, onBeforeUnmount } from 'vue'
import api from '../utils/api.js'

// Polymorphic "add to a collection" button (C5 v2). Two form factors:
//   variant="button" (default) — labeled, used by the 5 detail-view heroes ;
//   variant="icon"            — compact disc, used inside cards / table rows /
//                               the PlayerBar (hover-revealed by the host).
// An id-bearing entity (track/set/artist/playlist) passes `item-id`; a genre has
// no table row, so it passes `item-name` instead (item-id stays null).
const props = defineProps({
  itemType: { type: String, required: true },
  itemId: { type: Number, default: null },
  itemName: { type: String, default: null },
  variant: {
    type: String,
    default: 'button',
    validator: (v) => v === 'button' || v === 'icon',
  },
  label: { type: String, default: 'Collection' },
  title: { type: String, default: 'Ajouter à une collection' },
})

const showDropdown = ref(false)
const collections = ref([])
const collLoading = ref(false)
const creatingNew = ref(false)
const newCollName = ref('')
const newCollInput = ref(null)
const savingColl = ref(false)

const triggerRef = ref(null)
const menuRef = ref(null)
const menuStyle = ref({})

// Menu box: a definite width lets us clamp against the viewport edge; the height
// is a soft estimate used only to decide the up/down flip.
const MENU_WIDTH = 220
const MENU_MAX_HEIGHT = 264
const MARGIN = 8

// The polymorphic payload expected by POST /collections/{id}/items — carries the
// entity kind + its identifier (id for every type, name for a genre).
function itemPayload() {
  return {
    item_type: props.itemType,
    item_id: props.itemId,
    item_name: props.itemName,
  }
}

// Position the (body-level, fixed) menu from the trigger's viewport rect: flip
// above when there isn't room below, and clamp so it never spills off the right.
function computePosition() {
  const el = triggerRef.value
  if (!el) return
  const r = el.getBoundingClientRect()
  const spaceBelow = window.innerHeight - r.bottom
  const openUp = spaceBelow < MENU_MAX_HEIGHT && r.top > spaceBelow
  const left = Math.min(Math.max(MARGIN, r.left), window.innerWidth - MENU_WIDTH - MARGIN)
  const style = {
    position: 'fixed',
    left: `${Math.round(left)}px`,
    width: `${MENU_WIDTH}px`,
    zIndex: 1200,
  }
  if (openUp) {
    style.bottom = `${Math.round(window.innerHeight - r.top + 6)}px`
    style.maxHeight = `${Math.min(MENU_MAX_HEIGHT, r.top - MARGIN)}px`
  } else {
    style.top = `${Math.round(r.bottom + 6)}px`
    style.maxHeight = `${Math.min(MENU_MAX_HEIGHT, spaceBelow - MARGIN)}px`
  }
  menuStyle.value = style
}

// Any scroll/resize detaches the fixed menu from its trigger → just close it
// (a cheap, predictable behavior; the user re-opens where they are).
function onViewportChange() {
  closeDropdown()
}
function onDocPointerDown(e) {
  if (triggerRef.value?.contains(e.target)) return
  if (menuRef.value?.contains(e.target)) return
  closeDropdown()
}
function onKeydown(e) {
  if (e.key === 'Escape') closeDropdown()
}

function bindGlobal() {
  document.addEventListener('pointerdown', onDocPointerDown, true)
  document.addEventListener('keydown', onKeydown)
  window.addEventListener('scroll', onViewportChange, { capture: true, passive: true })
  window.addEventListener('resize', onViewportChange)
}
function unbindGlobal() {
  document.removeEventListener('pointerdown', onDocPointerDown, true)
  document.removeEventListener('keydown', onKeydown)
  window.removeEventListener('scroll', onViewportChange, { capture: true })
  window.removeEventListener('resize', onViewportChange)
}

async function toggleDropdown() {
  if (showDropdown.value) {
    closeDropdown()
    return
  }
  showDropdown.value = true
  bindGlobal()
  await nextTick()
  computePosition()
  if (!collections.value.length) {
    collLoading.value = true
    try {
      const { data } = await api.get('/api/collections/')
      collections.value = data.map((c) => ({ ...c, _added: false }))
    } finally {
      collLoading.value = false
      await nextTick()
      computePosition()
    }
  }
}

function closeDropdown() {
  showDropdown.value = false
  creatingNew.value = false
  newCollName.value = ''
  unbindGlobal()
}

onBeforeUnmount(unbindGlobal)

async function addToCollection(coll) {
  if (coll._added) return
  try {
    await api.post(`/api/collections/${coll.id}/items`, itemPayload())
    coll._added = true
  } catch (e) {
    if (e.response?.status === 409) coll._added = true
  }
}

// Inline "+ Nouvelle collection" flow inside the dropdown.
function startNewColl() {
  creatingNew.value = true
  newCollName.value = ''
  nextTick(() => newCollInput.value?.focus())
}

function cancelNewColl() {
  creatingNew.value = false
  newCollName.value = ''
}

async function createCollection() {
  const name = newCollName.value.trim()
  if (!name || savingColl.value) return
  savingColl.value = true
  try {
    const { data } = await api.post('/api/collections/', { name })
    await api.post(`/api/collections/${data.id}/items`, itemPayload())
    collections.value.push({ ...data, _added: true })
    cancelNewColl()
    await nextTick()
    computePosition()
  } catch {
    // silent — leave the input open, like the rest of the dropdown
  } finally {
    savingColl.value = false
  }
}
</script>

<style scoped>
/* Collection add button + dropdown */
.coll-add-wrap {
  position: relative;
  display: inline-flex;
}

/* ── Button variant (labeled, detail heroes) ── */
.btn-coll {
  display: inline-flex;
  align-items: center;
  gap: var(--space-15);
  height: 38px;
  padding: 0 var(--space-3);
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 var(--fs-sm) var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
  transition:
    color 0.12s,
    border-color 0.12s;
}
.btn-coll:hover,
.btn-coll.is-open {
  color: var(--ink);
  border-color: var(--ink-3);
}
.btn-coll svg {
  width: 16px;
  height: 16px;
}

/* ── Icon variant (compact disc, cards/rows/player) ── */
.btn-coll-icon {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  padding: 0;
  border-radius: 50%;
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  cursor: pointer;
  transition:
    color 0.12s,
    border-color 0.12s,
    background 0.12s;
}
.btn-coll-icon:hover,
.btn-coll-icon.is-open {
  color: var(--ink);
  border-color: var(--ink-3);
  background: var(--surface-2);
}
.btn-coll-icon.is-open {
  background: var(--accent-soft);
  border-color: var(--accent);
  color: var(--accent-ink);
}
.btn-coll-icon svg {
  width: 16px;
  height: 16px;
}
.btn-coll-icon:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

/* ── Dropdown (teleported to <body>, positioned inline via :style) ── */
.coll-dropdown {
  overflow-y: auto;
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-md);
  padding: var(--space-1);
}
.coll-dd-state {
  padding: var(--space-25) var(--space-3);
  font: 400 var(--fs-sm) var(--font-ui);
  color: var(--ink-3);
}
.coll-dd-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: var(--space-2) var(--space-3);
  border: none;
  background: transparent;
  color: var(--ink);
  font: 500 var(--fs-sm) var(--font-ui);
  cursor: pointer;
  border-radius: var(--r-sm);
  text-align: left;
  transition: background 0.1s;
}
.coll-dd-item:hover:not(:disabled) {
  background: var(--surface-2);
}
.coll-dd-item:disabled {
  color: var(--ink-3);
  cursor: default;
}
.coll-dd-check {
  color: var(--pos-ink);
  font-weight: 600;
}

/* "+ Nouvelle collection" — separated footer that swaps to an inline input */
.coll-dd-new {
  margin-top: var(--space-1);
  padding-top: var(--space-1);
  border-top: 1px solid var(--line);
}
.coll-dd-add {
  display: block;
  width: 100%;
  padding: var(--space-2) var(--space-3);
  border: none;
  background: transparent;
  color: var(--accent-ink);
  font: 500 var(--fs-sm) var(--font-ui);
  cursor: pointer;
  border-radius: var(--r-sm);
  text-align: left;
  transition: background 0.1s;
}
.coll-dd-add:hover {
  background: var(--surface-2);
}
.coll-dd-input {
  width: 100%;
  height: 34px;
  padding: 0 var(--space-3);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  background: var(--bg);
  color: var(--ink);
  font: 500 var(--fs-sm) var(--font-ui);
  outline: none;
  box-sizing: border-box;
}
.coll-dd-input::placeholder {
  color: var(--ink-3);
}
.coll-dd-input:focus {
  border-color: var(--accent);
}
</style>
