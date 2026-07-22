<template>
  <div class="app-container">
    <a href="#main-content" class="skip-link">Aller au contenu</a>
    <div class="app-shell" :class="{ 'no-sidebar': !auth.isAuthenticated }">
      <SidebarNav v-if="auth.isAuthenticated" class="app-sidebar" />
      <main id="main-content" class="app-main" :class="{ 'has-player': player.visible }">
        <RouterView />
      </main>
    </div>
    <Transition name="player">
      <PlayerBar v-if="player.visible" />
    </Transition>
    <BottomNav v-if="auth.isAuthenticated" />
    <ToastNotification />
  </div>
</template>

<script setup>
import { watch } from 'vue'
import SidebarNav from './components/SidebarNav.vue'
import PlayerBar from './components/PlayerBar.vue'
import BottomNav from './components/BottomNav.vue'
import ToastNotification from './components/ToastNotification.vue'
import { useAudioPlayer } from './stores/audioPlayer'
import { useAuthStore } from './stores/auth'
import { useOpinionsStore } from './stores/opinions.js'

const player = useAudioPlayer()
const auth = useAuthStore()
const opinions = useOpinionsStore()

// Guests get a 401 on /api/opinions/, and the OAuth callback is an SPA
// navigation (no reload) — load on auth transitions, not once at startup.
// refreshUser() runs on the same transitions so a stale persisted user
// (e.g. is_admin flipped server-side) is corrected at boot and on login;
// fire-and-forget so it never blocks the first render.
watch(
  () => auth.isAuthenticated,
  (ok) => {
    if (ok) {
      auth.refreshUser()
      opinions.load()
    } else {
      opinions.reset()
    }
  },
  { immediate: true },
)
</script>

<style>
*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}
html,
body {
  height: 100%;
}
body {
  font-family: var(--font-ui);
  background: var(--bg);
  color: var(--ink);
  -webkit-font-smoothing: antialiased;
}

/* Player bar transitions (must be unscoped for <Transition>) */
.player-enter-active {
  transition:
    transform 0.34s cubic-bezier(0.22, 1, 0.36, 1),
    opacity 0.34s ease;
}
.player-enter-from {
  transform: translateY(100%);
  opacity: 0;
}
.player-leave-active {
  transition:
    transform 0.24s ease-in,
    opacity 0.24s ease-in;
}
.player-leave-to {
  transform: translateY(100%);
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .player-enter-active,
  .player-leave-active {
    transition: opacity 0.2s ease;
  }
  .player-enter-from,
  .player-leave-to {
    transform: none;
  }
}
</style>

<style>
.skip-link {
  position: absolute;
  top: -100%;
  left: 16px;
  z-index: 9999;
  padding: var(--space-2) var(--space-4);
  background: var(--accent);
  color: var(--on-accent);
  border-radius: var(--r-sm);
  font: 500 var(--fs-base) var(--font-ui);
  text-decoration: none;
}
.skip-link:focus {
  top: 8px;
}
</style>

<style scoped>
.app-container {
  --sidebar-w: 232px;
  container-type: inline-size;
  height: 100vh;
}
.app-shell {
  display: grid;
  grid-template-columns: var(--sidebar-w) 1fr;
  height: 100%;
  overflow: hidden;
}
.app-shell.no-sidebar {
  grid-template-columns: 1fr;
}
.app-main {
  min-width: 0;
  overflow-y: auto;
  /* Lock horizontal panning: a few px of overflow anywhere would otherwise
     turn app-main into an x-scroll container (overflow-y:auto forces the
     x axis to `auto` too). Clip x + kill the residual rubber-band on iOS. */
  overflow-x: hidden;
  overscroll-behavior-x: none;
  container: app / inline-size;
}
.app-main.has-player {
  padding-bottom: 100px;
}

@container (max-width: 900px) {
  .app-container {
    --sidebar-w: 66px;
  }
}

@container (max-width: 640px) {
  .app-container {
    --sidebar-w: 0px;
  }
  .app-shell {
    grid-template-columns: 1fr;
  }
  .app-sidebar {
    display: none;
  }
  .app-main {
    padding-bottom: calc(var(--bottom-nav-h) + env(safe-area-inset-bottom, 0px));
  }
  .app-main.has-player {
    padding-bottom: calc(var(--bottom-nav-h) + env(safe-area-inset-bottom, 0px) + 90px);
  }
}
</style>
