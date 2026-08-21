<template>
  <div class="coll-add-wrap">
    <button class="btn-coll" @click="toggleDropdown">
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.7"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <rect x="3" y="5" width="18" height="16" rx="2" />
        <path d="M12 10v6M9 13h6" />
      </svg>
      <span>{{ label }}</span>
    </button>
    <div v-if="showDropdown" class="coll-dropdown">
      <div v-if="collLoading" class="coll-dd-state">Chargement…</div>
      <template v-else>
        <div v-if="!collections.length" class="coll-dd-state">Aucune collection</div>
        <button
          v-for="c in collections"
          :key="c.id"
          class="coll-dd-item"
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
          <button v-else class="coll-dd-add" @click="startNewColl">+ Nouvelle collection</button>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import api from '../utils/api.js'

// Polymorphic "add to a collection" button (C5 v2). Every detail view reuses it:
// an id-bearing entity (track/set/artist/playlist) passes `item-id`; a genre has
// no table row, so it passes `item-name` instead (item-id stays null).
const props = defineProps({
  itemType: { type: String, required: true },
  itemId: { type: Number, default: null },
  itemName: { type: String, default: null },
  label: { type: String, default: 'Collection' },
})

const showDropdown = ref(false)
const collections = ref([])
const collLoading = ref(false)
const creatingNew = ref(false)
const newCollName = ref('')
const newCollInput = ref(null)
const savingColl = ref(false)

// The polymorphic payload expected by POST /collections/{id}/items — carries the
// entity kind + its identifier (id for every type, name for a genre).
function itemPayload() {
  return {
    item_type: props.itemType,
    item_id: props.itemId,
    item_name: props.itemName,
  }
}

async function toggleDropdown() {
  showDropdown.value = !showDropdown.value
  if (showDropdown.value && !collections.value.length) {
    collLoading.value = true
    try {
      const { data } = await api.get('/api/collections/')
      collections.value = data.map((c) => ({ ...c, _added: false }))
    } finally {
      collLoading.value = false
    }
  }
}

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
}
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
.btn-coll:hover {
  color: var(--ink);
  border-color: var(--ink-3);
}
.btn-coll svg {
  width: 16px;
  height: 16px;
}
.coll-dropdown {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  min-width: 200px;
  max-height: 240px;
  overflow-y: auto;
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-md);
  z-index: 50;
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
