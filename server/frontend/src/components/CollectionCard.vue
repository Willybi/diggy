<template>
  <div class="coll-card" @click="$emit('open', coll)">
    <div class="coll-name">{{ coll.name }}</div>
    <div class="coll-meta">
      <span class="coll-count"
        >{{ coll.item_count }} track{{ coll.item_count !== 1 ? 's' : '' }}</span
      >
      <span class="coll-date">{{ fmtDate(coll.created_at) }}</span>
    </div>

    <div class="coll-assign" @click.stop>
      <span class="assign-icon">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
          <path
            d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"
            stroke-linejoin="round"
          />
        </svg>
      </span>
      <select
        class="assign-select"
        :value="coll.folder_id == null ? '' : String(coll.folder_id)"
        aria-label="Dossier"
        @change="$emit('assign', coll, $event.target.value)"
      >
        <option value="">Sans dossier</option>
        <option v-for="f in folders" :key="f.id" :value="String(f.id)">{{ f.name }}</option>
      </select>
    </div>

    <button class="coll-del" title="Supprimer" @click.stop="$emit('delete', coll)">
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.7"
        stroke-linecap="round"
      >
        <path
          d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"
        />
      </svg>
    </button>
  </div>
</template>

<script setup>
import { fmtDate } from '../utils/format'

defineProps({
  coll: { type: Object, required: true },
  folders: { type: Array, default: () => [] },
})
defineEmits(['open', 'assign', 'delete'])
</script>

<style scoped>
.coll-card {
  position: relative;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  padding: var(--space-5);
  cursor: pointer;
  transition: background 0.12s;
}
.coll-card:hover {
  background: var(--surface-2);
}
.coll-name {
  font: 600 var(--fs-title)/1.3 var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding-right: var(--space-6);
}
.coll-meta {
  margin-top: var(--space-2);
  display: flex;
  align-items: center;
  gap: var(--space-25);
  font: 500 var(--fs-sm)/1 var(--font-mono);
  color: var(--ink-3);
}

/* ---- Folder assignment ---- */
.coll-assign {
  margin-top: var(--space-4);
  display: flex;
  align-items: center;
  gap: var(--space-2);
}
.assign-icon {
  display: grid;
  place-items: center;
  color: var(--ink-3);
  flex: none;
}
.assign-icon svg {
  width: 15px;
  height: 15px;
}
.assign-select {
  flex: 1;
  min-width: 0;
  height: 32px;
  padding: 0 var(--space-2);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  background: var(--bg);
  color: var(--ink-2);
  font: 500 var(--fs-sm) var(--font-ui);
  cursor: pointer;
  outline: none;
}
.assign-select:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}

.coll-del {
  position: absolute;
  top: 14px;
  right: 14px;
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  border: none;
  background: transparent;
  color: var(--ink-3);
  border-radius: var(--r-xs);
  cursor: pointer;
  opacity: 0;
  transition:
    opacity 0.14s,
    color 0.14s;
}
.coll-card:hover .coll-del {
  opacity: 1;
}
.coll-del:hover {
  color: var(--neg-ink);
}
.coll-del svg {
  width: 16px;
  height: 16px;
}
</style>
