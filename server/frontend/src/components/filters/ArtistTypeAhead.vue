<template>
  <div class="ata" :class="{ 'ata--drawer': variant === 'drawer' }">
    <div class="ata-field" @click="focusInput">
      <span v-for="artist in modelValue" :key="artist.id" class="ata-chip">
        {{ artist.name }}
        <button
          type="button"
          class="ata-x"
          :aria-label="`Retirer ${artist.name}`"
          @click.stop="removeArtist(artist)"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true">
            <path d="M18 6 6 18M6 6l12 12" stroke-linecap="round" />
          </svg>
        </button>
      </span>
      <input
        ref="inputEl"
        v-model="query"
        class="ata-input"
        type="text"
        :placeholder="modelValue.length ? '' : placeholder"
        role="combobox"
        aria-autocomplete="list"
        :aria-expanded="open"
        @input="onInput"
        @keydown="onKeydown"
        @blur="onBlur"
      />
    </div>

    <div v-if="open" class="ata-drop" role="listbox">
      <button
        v-for="(artist, i) in results"
        :key="artist.id"
        type="button"
        class="ata-item"
        :class="{ hl: i === highlight }"
        role="option"
        :aria-selected="i === highlight"
        @click="select(artist)"
      >
        <span class="ata-ava">
          <img
            v-if="artist.has_artwork"
            :src="`/storage/artist-artworks/${artist.id}.jpg`"
            alt=""
            loading="lazy"
          />
          <span v-else class="ata-ini">{{ initialOf(artist) }}</span>
        </span>
        <span class="ata-name">{{ artist.name }}</span>
      </button>
      <div v-if="!results.length" class="ata-none">Aucun artiste</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onUnmounted } from 'vue'
import api from '../../utils/api.js'

const props = defineProps({
  // Selected artists — objects { id, name, has_artwork? }.
  modelValue: { type: Array, default: () => [] },
  placeholder: { type: String, default: 'Rechercher un artiste…' },
  debounce: { type: Number, default: 250 },
  limit: { type: Number, default: 6 },
  variant: { type: String, default: 'panel' }, // 'panel' | 'drawer' (44px target)
})
const emit = defineEmits(['update:modelValue'])

const inputEl = ref(null)
const query = ref('')
const results = ref([])
const open = ref(false)
const highlight = ref(-1)
let timer = null
let blurTimer = null
// Monotonic token (same pattern as useWindowedList): a request superseded by a
// newer search — or by close() — is dropped instead of clobbering the results
// or reopening the dropdown on a field the user already cleared/closed.
let token = 0

function focusInput() {
  inputEl.value?.focus()
}

function onInput() {
  clearTimeout(timer)
  const q = query.value.trim()
  if (!q) {
    close()
    return
  }
  timer = setTimeout(() => search(q), props.debounce)
}

async function search(q) {
  const mine = ++token
  try {
    const { data } = await api.get('/api/artists/', { params: { q, limit: props.limit } })
    if (mine !== token) return
    const selected = new Set(props.modelValue.map((a) => a.id))
    results.value = (data.items || []).filter((a) => !selected.has(a.id))
    highlight.value = results.value.length ? 0 : -1
    open.value = true
  } catch {
    if (mine === token) close()
  }
}

function onBlur() {
  // Close on click-outside/blur, delayed so a click on a dropdown item
  // (mousedown → blur → click → select) still lands before we tear it down.
  clearTimeout(blurTimer)
  blurTimer = setTimeout(close, 150)
}

function onKeydown(e) {
  if (e.key === 'Escape') {
    close()
    return
  }
  if (e.key === 'Backspace' && !query.value && props.modelValue.length) {
    removeArtist(props.modelValue[props.modelValue.length - 1])
    return
  }
  if (!open.value) return
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    highlight.value = Math.min(results.value.length - 1, highlight.value + 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    highlight.value = Math.max(0, highlight.value - 1)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    const hit = results.value[highlight.value]
    if (hit) select(hit)
  }
}

function select(artist) {
  emit('update:modelValue', [...props.modelValue, artist])
  query.value = ''
  close()
}

function removeArtist(artist) {
  emit(
    'update:modelValue',
    props.modelValue.filter((a) => a.id !== artist.id),
  )
}

function close() {
  // Bump the token so a response still in flight is ignored after we close.
  token++
  clearTimeout(timer)
  clearTimeout(blurTimer)
  open.value = false
  results.value = []
  highlight.value = -1
}

function initialOf(artist) {
  return (artist.name || '?').trim().charAt(0).toUpperCase()
}

onUnmounted(() => {
  clearTimeout(timer)
  clearTimeout(blurTimer)
})
</script>

<style scoped>
.ata {
  position: relative;
}
.ata-field {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-1);
  min-height: 38px;
  padding: var(--space-1) var(--space-2);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  background: var(--surface);
  cursor: text;
  transition: border-color 0.12s;
}
.ata--drawer .ata-field {
  min-height: var(--touch-min);
}
.ata-field:focus-within {
  border-color: var(--accent);
}

.ata-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--space-05);
  height: 24px;
  padding: 0 var(--space-05) 0 var(--space-2);
  border-radius: var(--r-pill);
  background: var(--accent-soft);
  color: var(--accent-ink);
  font: 600 var(--fs-xs) var(--font-ui);
  white-space: nowrap;
}
.ata-x {
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: inherit;
  cursor: pointer;
  transition: background 0.12s;
}
.ata-x:hover {
  background: var(--accent-soft-2);
}
.ata-x svg {
  width: 10px;
  height: 10px;
}
.ata-x:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.ata-input {
  flex: 1;
  min-width: 80px;
  border: 0;
  background: transparent;
  outline: none;
  color: var(--ink);
  font: 400 var(--fs-input) var(--font-ui);
}
.ata-input::placeholder {
  color: var(--ink-3);
}

.ata-drop {
  position: absolute;
  top: calc(100% + var(--space-1));
  left: 0;
  right: 0;
  z-index: 30;
  max-height: 220px;
  overflow-y: auto;
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-lg);
  padding: var(--space-1);
}
.ata-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  width: 100%;
  height: 36px;
  padding: 0 var(--space-2);
  border: 0;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--ink);
  font: 500 var(--fs-sm) var(--font-ui);
  text-align: left;
  cursor: pointer;
  transition: background 0.12s;
}
.ata-item:hover,
.ata-item.hl {
  background: var(--surface-2);
}
.ata-item:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}
.ata-ava {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  overflow: hidden;
  flex: none;
  display: grid;
  place-items: center;
  background: var(--surface-3);
}
.ata-ava img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.ata-ini {
  font: 600 var(--fs-nano) var(--font-ui);
  color: var(--ink-2);
}
.ata-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ata-none {
  padding: var(--space-2);
  font: 400 var(--fs-sm) var(--font-ui);
  color: var(--ink-3);
}
</style>
