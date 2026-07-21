<template>
  <aside class="sidebar">
    <RouterLink to="/" class="sidebar-brand">
      <div class="brand-glyph">D</div>
      <span class="brand-name">Diggy</span>
    </RouterLink>

    <nav class="nav-section">
      <p class="nav-label"><span>Library</span></p>
      <RouterLink
        v-for="item in libraryItems"
        :key="item.to"
        :to="item.to"
        custom
        v-slot="{ isActive, navigate }"
      >
        <span class="nav-item" :class="{ 'is-active': isActive }" @click="navigate">
          <span class="nav-icon" v-html="item.icon" />
          <span class="nav-text">{{ item.label }}</span>
          <span v-if="item.count != null" class="nav-count">{{ item.count }}</span>
        </span>
      </RouterLink>
    </nav>

    <!-- ADMIN : surface utility, se detache (decision D2) -->
    <nav v-if="auth.user?.is_admin" class="nav-section nav-admin">
      <p class="nav-label"><span>Admin</span></p>
      <RouterLink to="/admin" custom v-slot="{ isActive, navigate }">
        <span class="nav-item" :class="{ 'is-active': isActive }" @click="navigate">
          <span class="nav-icon" v-html="iconAdmin" />
          <span class="nav-text">Admin</span>
          <span class="util-key">ADM</span>
        </span>
      </RouterLink>
    </nav>

    <div class="sidebar-footer">
      <div v-if="auth.isAuthenticated" class="user-row">
        <span class="nav-icon" v-html="iconUser" />
        <span class="user-name">{{ auth.user?.username }}</span>
        <button class="logout-btn" @click="handleLogout" title="Deconnexion">
          <span v-html="iconLogout" />
        </button>
      </div>
      <RouterLink v-else to="/login" custom v-slot="{ navigate }">
        <span class="nav-item" @click="navigate">
          <span class="nav-icon" v-html="iconUser" />
          <span class="nav-text">Connexion</span>
        </span>
      </RouterLink>

      <button class="nav-item theme-toggle" @click="toggle">
        <span class="nav-icon" v-html="isDark ? iconSun : iconMoon" />
        <span class="nav-text">{{ isDark ? 'Light mode' : 'Dark mode' }}</span>
      </button>
    </div>
  </aside>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useTheme } from '../composables/useTheme.js'
import { useAuthStore } from '../stores/auth.js'

const { isDark, toggle } = useTheme()
const auth = useAuthStore()
const router = useRouter()

function handleLogout() {
  auth.logout()
  router.push('/login')
}

const iconArtist = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="8" r="3.5"/><path d="M2 20c0-3.5 3.1-6 7-6s7 2.5 7 6"/><circle cx="18" cy="9" r="2.5"/><path d="M16 20c0-2.5 1.8-4 4-4"/></svg>`
const iconAdmin = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>`
const iconGrid = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/></svg>`
const iconSet = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="1" fill="currentColor"/></svg>`
const iconPlaylist = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M3 6h18M3 12h12M3 18h8"/></svg>`
const iconTag = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M3 12V5a2 2 0 0 1 2-2h7l9 9-7 7-9-9z"/><circle cx="7.5" cy="7.5" r="1.2" fill="currentColor"/></svg>`
const iconCollection = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 5V3h10v2"/><path d="M9 5V2h6v3"/></svg>`
const iconSun = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="12" cy="12" r="5"/><path d="M12 2v2M12 20v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M2 12h2M20 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>`
const iconMoon = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`
const iconUser = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>`
const iconLogout = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"><path d="M17 16l4-4-4-4M21 12H9"/><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/></svg>`
const libraryItems = [
  { to: '/explorer', label: 'Explorer', icon: iconGrid, count: null },
  { to: '/artists', label: 'Artistes', icon: iconArtist, count: null },
  { to: '/sets', label: 'Sets', icon: iconSet, count: null },
  { to: '/playlists', label: 'Playlists', icon: iconPlaylist, count: null },
  { to: '/genres', label: 'Genres', icon: iconTag, count: null },
  { to: '/collections', label: 'Collections', icon: iconCollection, count: null },
]
</script>

<style scoped>
.sidebar {
  height: 100%;
  background: var(--surface);
  border-right: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  padding: var(--space-5) var(--space-4) var(--space-4);
  gap: var(--space-05);
}
.sidebar-brand {
  display: flex;
  align-items: center;
  gap: var(--space-25);
  padding: var(--space-1) var(--space-2) var(--space-5);
  text-decoration: none;
  cursor: pointer;
}
.brand-glyph {
  width: 30px;
  height: 30px;
  border-radius: var(--r-sm);
  background: var(--accent);
  color: var(--on-accent);
  display: grid;
  place-items: center;
  font: 700 var(--fs-title)/1 var(--font-ui);
  flex: none;
}
.brand-name {
  font: 600 var(--fs-md)/1 var(--font-ui);
  letter-spacing: 0.2px;
  color: var(--ink);
}
.nav-section {
  margin-bottom: 0;
}
.nav-label {
  font: 500 var(--fs-xs)/1 var(--font-mono);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--ink-3);
  padding: var(--space-4) var(--space-25) var(--space-2);
  margin: 0;
}
.nav-item {
  display: flex;
  align-items: center;
  gap: var(--space-25);
  padding: var(--space-2) var(--space-25);
  border-radius: var(--r-sm);
  color: var(--ink-2);
  cursor: pointer;
  font: 500 var(--fs-base)/1 var(--font-ui);
  transition:
    background 0.12s,
    color 0.12s;
  user-select: none;
  text-decoration: none;
  line-height: 1;
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
  width: 19px;
  height: 19px;
  flex: none;
  display: grid;
  place-items: center;
}
.nav-icon :deep(svg) {
  width: 19px;
  height: 19px;
}
.nav-text {
  white-space: nowrap;
}
.nav-count {
  margin-left: auto;
  font: 500 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-3);
}
.nav-item.is-active .nav-count {
  color: var(--accent-ink);
}

/* --- ADMIN : surface "utility", se detache (decision D2) --- */
.nav-admin {
  margin-top: var(--space-2);
  padding-top: var(--space-3);
  border-top: 1px dashed var(--line-2);
}
.nav-admin .nav-label {
  color: var(--ink-3);
  padding-top: var(--space-1);
}
.nav-admin .nav-item {
  color: var(--ink-2);
  border: 1px dashed var(--line-2);
  background: var(--surface-2);
}
.nav-admin .nav-item:hover {
  background: var(--surface-3);
}
.util-key {
  margin-left: auto;
  font: 600 var(--fs-nano)/1 var(--font-mono);
  letter-spacing: 0.1em;
  color: var(--ink-3);
  border: 1px solid var(--line-2);
  border-radius: 4px;
  padding: var(--space-05) var(--space-1);
}

.sidebar-footer {
  margin-top: auto;
  padding-top: var(--space-4);
  display: flex;
  flex-direction: column;
  gap: var(--space-05);
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
  gap: var(--space-25);
  padding: var(--space-2) var(--space-25);
  border-radius: var(--r-sm);
  color: var(--ink-2);
  font: 500 var(--fs-base)/1 var(--font-ui);
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
  padding: var(--space-05);
  cursor: pointer;
  color: var(--ink-3);
  display: grid;
  place-items: center;
  border-radius: 4px;
  transition:
    color 0.12s,
    background 0.12s;
  margin-left: auto;
}
.logout-btn:hover {
  color: var(--accent-ink);
}
.logout-btn :deep(svg) {
  width: 18px;
  height: 18px;
}

/* ============ RESPONSIVE — rail mode via container query ============ */
@container (max-width: 900px) {
  .brand-name,
  .nav-text,
  .nav-count,
  .nav-label span,
  .util-key {
    display: none;
  }
  .nav-label {
    text-align: center;
    padding: var(--space-4) 0 var(--space-2);
  }
  .nav-label::after {
    content: '\b7';
  }
  .nav-item {
    justify-content: center;
    padding: var(--space-25) 0;
  }
  .nav-admin .nav-item {
    border-style: dashed;
  }
  .user-row {
    justify-content: center;
  }
  .user-name {
    display: none;
  }
  .logout-btn {
    margin-left: 0;
  }
}
</style>
