<template>
  <aside class="sidebar">
    <div class="sidebar-brand">
      <div class="brand-glyph">D</div>
      <span class="brand-name">Diggy</span>
    </div>

    <nav class="nav-section">
      <p class="nav-label">Library</p>
      <RouterLink v-for="item in libraryItems" :key="item.to"
        :to="item.to" custom v-slot="{ isActive, navigate }"
      >
        <span class="nav-item" :class="{ 'is-active': isActive }" @click="navigate">
          <span class="nav-icon" v-html="item.icon" />
          {{ item.label }}
          <span v-if="item.count != null" class="nav-count">{{ item.count }}</span>
        </span>
      </RouterLink>
    </nav>

    <nav class="nav-section">
      <p class="nav-label">Discover</p>
      <RouterLink v-for="item in discoverItems" :key="item.to"
        :to="item.to" custom v-slot="{ isActive, navigate }"
      >
        <span class="nav-item" :class="{ 'is-active': isActive }" @click="navigate">
          <span class="nav-icon" v-html="item.icon" />
          {{ item.label }}
          <span v-if="item.count != null" class="nav-count">{{ item.count }}</span>
        </span>
      </RouterLink>
    </nav>

    <nav v-if="auth.user?.is_admin" class="nav-section">
      <p class="nav-label">Admin</p>
      <RouterLink to="/admin" custom v-slot="{ isActive, navigate }">
        <span class="nav-item" :class="{ 'is-active': isActive }" @click="navigate">
          <span class="nav-icon" v-html="iconAdmin" />
          Admin
        </span>
      </RouterLink>
    </nav>

    <div class="sidebar-footer">
      <div v-if="auth.isAuthenticated" class="user-row">
        <span class="nav-icon" v-html="iconUser" />
        <span class="user-name">{{ auth.user?.username }}</span>
        <button class="logout-btn" @click="handleLogout" title="Déconnexion">
          <span v-html="iconLogout" />
        </button>
      </div>
      <RouterLink v-else to="/login" custom v-slot="{ navigate }">
        <span class="nav-item" @click="navigate">
          <span class="nav-icon" v-html="iconUser" />
          Connexion
        </span>
      </RouterLink>

      <button class="nav-item theme-toggle" @click="toggle">
        <span class="nav-icon" v-html="isDark ? iconSun : iconMoon" />
        {{ isDark ? 'Light mode' : 'Dark mode' }}
      </button>
    </div>
  </aside>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import axios from 'axios'
import { useTheme } from '../composables/useTheme.js'
import { useAuthStore } from '../stores/auth.js'

const { isDark, toggle } = useTheme()
const auth = useAuthStore()
const router = useRouter()

const radarNewCount = ref(null)

async function fetchRadarNewCount() {
  try {
    const { data } = await axios.get('/api/radar/new-count')
    radarNewCount.value = data.count || null
  } catch {}
}

onMounted(fetchRadarNewCount)

function handleLogout() {
  auth.logout()
  router.push('/login')
}

const iconArtist = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="8" r="3.5"/><path d="M2 20c0-3.5 3.1-6 7-6s7 2.5 7 6"/><circle cx="18" cy="9" r="2.5"/><path d="M16 20c0-2.5 1.8-4 4-4"/></svg>`
const iconAdmin = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>`
const iconLib = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19V5a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1v14M9 19V5a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1v14M14 19l4-15 3 1-4 14"/></svg>`
const iconGrid = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/></svg>`
const iconSet = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="1" fill="currentColor"/></svg>`
const iconPlaylist = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M3 6h18M3 12h12M3 18h8"/></svg>`
const iconRadar = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.4" fill="currentColor"/></svg>`
const iconTag = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M3 12V5a2 2 0 0 1 2-2h7l9 9-7 7-9-9z"/><circle cx="7.5" cy="7.5" r="1.2" fill="currentColor"/></svg>`
const iconSun = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="12" cy="12" r="5"/><path d="M12 2v2M12 20v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M2 12h2M20 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>`
const iconMoon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`
const iconUser = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>`
const iconLogout = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M17 16l4-4-4-4M21 12H9"/><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/></svg>`

const libraryItems = [
  { to: '/catalog',   label: 'Catalog',    icon: iconGrid,     count: null },
  { to: '/artists',   label: 'Artistes',   icon: iconArtist,   count: null },
  { to: '/sets',      label: 'Sets',       icon: iconSet,      count: null },
  { to: '/playlists', label: 'Playlists',  icon: iconPlaylist, count: null },
]

const discoverItems = computed(() => [
  { to: '/radar', label: 'Radar',       icon: iconRadar, count: radarNewCount.value || null },
  { to: '/tags',  label: 'Genres',      icon: iconTag,   count: null },
])
</script>

<style scoped>
.sidebar {
  height: 100%;
  background: var(--surface);
  border-right: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  padding: 16px 12px;
  gap: 0;
}
.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px 20px;
}
.brand-glyph {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: var(--accent);
  color: var(--on-accent);
  display: grid;
  place-items: center;
  font: 700 15px/1 var(--font-ui);
}
.brand-name {
  font: 600 16px/1 var(--font-ui);
  letter-spacing: -0.02em;
  color: var(--ink);
}
.nav-section {
  margin-bottom: 8px;
}
.nav-label {
  font: 500 10px/1 var(--font-mono);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-3);
  padding: 14px 8px 6px;
  margin: 0;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 9px 10px;
  border-radius: var(--r-sm);
  color: var(--ink-2);
  cursor: pointer;
  font: 500 14px/1 var(--font-ui);
  transition: background 0.12s, color 0.12s;
  user-select: none;
}
.nav-item:hover {
  background: var(--surface-2);
  color: var(--ink);
}
.nav-item.is-active {
  background: var(--accent-soft);
  color: var(--accent-ink);
}
.nav-icon {
  width: 17px;
  height: 17px;
  flex: none;
  display: grid;
  place-items: center;
  opacity: 0.85;
}
.nav-icon :deep(svg) {
  width: 17px;
  height: 17px;
}
.nav-count {
  margin-left: auto;
  font: 400 11px/1 var(--font-mono);
  color: var(--ink-3);
}
.nav-item.is-active .nav-count {
  color: var(--accent-ink);
}
.sidebar-footer {
  margin-top: auto;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}
.theme-toggle {
  width: 100%;
  border: none;
  background: transparent;
  font: inherit;
}

.user-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: var(--r-sm);
  color: var(--ink-2);
  font: 500 13px/1 var(--font-ui);
  margin-bottom: 4px;
}

.user-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.logout-btn {
  background: none;
  border: none;
  padding: 2px;
  cursor: pointer;
  color: var(--ink-3);
  display: grid;
  place-items: center;
  border-radius: 4px;
  transition: color 0.12s, background 0.12s;
}

.logout-btn:hover {
  color: var(--ink);
  background: var(--surface-2);
}

.logout-btn :deep(svg) {
  width: 15px;
  height: 15px;
}
</style>
