<template>
  <nav class="bottom-nav">
    <RouterLink
      v-for="item in items"
      :key="item.to"
      :to="item.to"
      custom
      v-slot="{ isActive, navigate }"
    >
      <button
        class="bottom-nav-item"
        :class="{ 'is-active': isActive }"
        @click="navigate"
      >
        <span class="bottom-nav-icon" v-html="item.icon" />
        <span v-if="item.badge && newCount > 0" class="bottom-nav-badge">{{ newCount }}</span>
        <span class="bottom-nav-label">{{ item.label }}</span>
      </button>
    </RouterLink>
  </nav>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import api from '../utils/api.js'

const auth = useAuthStore()
const route = useRoute()
const newCount = ref(0)

const iconHome = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5L12 3l9 7.5V20a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/><path d="M9 21V14h6v7"/></svg>`
const iconGrid = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/></svg>`
const iconArtist = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="8" r="3.5"/><path d="M2 20c0-3.5 3.1-6 7-6s7 2.5 7 6"/><circle cx="18" cy="9" r="2.5"/><path d="M16 20c0-2.5 1.8-4 4-4"/></svg>`
const iconSet = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="1" fill="currentColor"/></svg>`
const iconTag = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M3 12V5a2 2 0 0 1 2-2h7l9 9-7 7-9-9z"/><circle cx="7.5" cy="7.5" r="1.2" fill="currentColor"/></svg>`
const iconAdmin = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>`

const baseItems = [
  { to: '/', label: 'Hub', icon: iconHome, badge: true },
  { to: '/catalog', label: 'Catalog', icon: iconGrid },
  { to: '/artists', label: 'Artistes', icon: iconArtist },
  { to: '/sets', label: 'Sets', icon: iconSet },
  { to: '/genres', label: 'Genres', icon: iconTag },
]

const items = computed(() => {
  const list = [...baseItems]
  if (auth.user?.is_admin) {
    list.push({ to: '/admin', label: 'Admin', icon: iconAdmin })
  }
  return list
})

async function fetchNewCount() {
  try {
    const res = await api.get('/radar/new-count')
    newCount.value = res.data.count ?? 0
  } catch {
    newCount.value = 0
  }
}

onMounted(fetchNewCount)
watch(() => route.path, fetchNewCount)
</script>

<style scoped>
.bottom-nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 999;
  height: var(--bottom-nav-h);
  padding-bottom: env(safe-area-inset-bottom, 0px);
  background: var(--surface);
  border-top: 1px solid var(--line);
  display: none;
  align-items: center;
}

@media (max-width: 640px) {
  .bottom-nav {
    display: flex;
  }
}

.bottom-nav-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-1);
  position: relative;
  background: none;
  border: none;
  cursor: pointer;
  color: var(--ink-3);
  padding: 0;
  height: 100%;
}

.bottom-nav-item.is-active {
  color: var(--accent);
}

.bottom-nav-item.is-active::before {
  content: '';
  position: absolute;
  top: 0;
  left: 50%;
  transform: translateX(-50%);
  width: 26px;
  height: 3px;
  background: var(--accent);
  border-radius: 0 0 2px 2px;
}

.bottom-nav-icon {
  width: 22px;
  height: 22px;
  display: grid;
  place-items: center;
}

.bottom-nav-icon :deep(svg) {
  width: 22px;
  height: 22px;
}

.bottom-nav-label {
  font: 500 var(--fs-xs)/1 var(--font-mono);
}

.bottom-nav-badge {
  position: absolute;
  top: 5px;
  left: calc(50% + 9px);
  background: var(--accent);
  color: var(--on-accent);
  font: 600 var(--fs-nano)/1 var(--font-mono);
  padding: var(--space-05) var(--space-1);
  border-radius: var(--r-sm);
  min-width: 16px;
  text-align: center;
}
</style>
