<template>
  <RelBlock :title="title" :count="total">
    <!-- Collapsed: horizontal shelf -->
    <div v-if="!expanded" class="shelf">
      <slot v-for="(item, i) in items" :key="i" :item="item" />
    </div>

    <!-- Expanded: wrapped grid -->
    <div v-else class="shelf-grid">
      <slot v-for="(item, i) in items" :key="i" :item="item" />
    </div>

    <!-- Toggle button -->
    <button v-if="total > initialCount" class="load-more" :disabled="loading" @click="toggle">
      {{ toggleLabel }}
    </button>

    <!-- Pagination (expanded only) -->
    <div v-if="expanded && totalPages > 1" class="shelf-pagination">
      <button class="pg-arrow" :disabled="page === 0" @click="goPage(page - 1)">&larr;</button>
      <template v-for="(p, i) in visiblePages" :key="i">
        <span v-if="p === '...'" class="pg-ellipsis">...</span>
        <button v-else class="pg-btn" :class="{ active: p === page }" @click="goPage(p)">
          {{ p + 1 }}
        </button>
      </template>
      <button class="pg-arrow" :disabled="page >= totalPages - 1" @click="goPage(page + 1)">
        &rarr;
      </button>
    </div>
  </RelBlock>
</template>

<script setup>
import { computed } from 'vue'
import RelBlock from './RelBlock.vue'

const props = defineProps({
  title: { type: String, required: true },
  items: { type: Array, required: true },
  total: { type: Number, required: true },
  loading: { type: Boolean, default: false },
  expanded: { type: Boolean, default: false },
  page: { type: Number, default: 0 },
  pageSize: { type: Number, default: 48 },
  initialCount: { type: Number, default: 12 },
})

const emit = defineEmits(['update:expanded', 'update:page', 'load-page'])

const totalPages = computed(() => Math.ceil(props.total / props.pageSize))

const toggleLabel = computed(() => {
  if (props.loading) return 'Chargement\u2026'
  if (props.expanded) return 'R\u00e9duire'
  return `Voir les ${props.total - props.initialCount} autres`
})

const visiblePages = computed(() => {
  const last = totalPages.value - 1
  if (last <= 6) return Array.from({ length: last + 1 }, (_, i) => i)

  const pages = new Set([0, last])
  for (let i = props.page - 2; i <= props.page + 2; i++) {
    if (i > 0 && i < last) pages.add(i)
  }
  const sorted = [...pages].sort((a, b) => a - b)
  const result = []
  let prev = -1
  for (const p of sorted) {
    if (prev !== -1 && p - prev > 1) result.push('...')
    result.push(p)
    prev = p
  }
  return result
})

function toggle() {
  const next = !props.expanded
  emit('update:expanded', next)
  if (next) {
    emit('update:page', 0)
    emit('load-page', { offset: 0, limit: props.pageSize })
  }
}

function goPage(p) {
  if (p < 0 || p >= totalPages.value || p === props.page) return
  emit('update:page', p)
  emit('load-page', { offset: p * props.pageSize, limit: props.pageSize })
}
</script>

<style scoped>
.shelf {
  display: flex;
  gap: 14px;
  overflow-x: auto;
  padding: 14px;
  scroll-snap-type: x proximity;
  -webkit-overflow-scrolling: touch;
}
.shelf::-webkit-scrollbar {
  display: none;
}

.shelf-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  padding: 14px;
}

.load-more {
  display: block;
  margin: 8px auto 0;
  padding: 6px 14px;
  border: none;
  background: none;
  color: var(--accent);
  font: 500 13px/1 var(--font-ui);
  cursor: pointer;
}
.load-more:hover:not(:disabled) {
  text-decoration: underline;
}
.load-more:disabled {
  opacity: 0.6;
  cursor: default;
}

.shelf-pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 4px;
  padding: 12px 0;
}
.pg-btn,
.pg-arrow {
  min-width: 32px;
  height: 32px;
  border: none;
  border-radius: var(--r-sm);
  background: var(--surface);
  color: var(--ink-3);
  font: 500 12px/1 var(--font-mono);
  cursor: pointer;
  transition:
    background 0.12s,
    color 0.12s;
}
.pg-btn:hover,
.pg-arrow:hover:not(:disabled) {
  background: var(--surface-2);
  color: var(--ink);
}
.pg-btn.active {
  background: var(--accent-soft);
  color: var(--accent-ink);
}
.pg-arrow:disabled {
  opacity: 0.3;
  cursor: default;
}
.pg-ellipsis {
  font: 500 12px/1 var(--font-mono);
  color: var(--ink-3);
  padding: 0 4px;
}
</style>
