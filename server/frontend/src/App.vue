<template>
  <div class="app-container">
    <div class="app-shell">
      <SidebarNav class="app-sidebar" />
      <main class="app-main" :class="{ 'has-player': player.visible }">
        <RouterView />
      </main>
    </div>
    <Transition name="player">
      <PlayerBar v-if="player.visible" />
    </Transition>
  </div>
</template>

<script setup>
import SidebarNav from './components/SidebarNav.vue'
import PlayerBar from './components/PlayerBar.vue'
import { useAudioPlayer } from './stores/audioPlayer'
import { useOpinionsStore } from './stores/opinions.js'

const player = useAudioPlayer()
const opinions = useOpinionsStore()
opinions.load()
</script>

<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body { height: 100%; }
body {
  font-family: var(--font-ui);
  background: var(--bg);
  color: var(--ink);
  -webkit-font-smoothing: antialiased;
}

/* Player bar transitions (must be unscoped for <Transition>) */
.player-enter-active {
  transition: transform .34s cubic-bezier(.22, 1, .36, 1), opacity .34s ease;
}
.player-enter-from {
  transform: translateY(100%);
  opacity: 0;
}
.player-leave-active {
  transition: transform .24s ease-in, opacity .24s ease-in;
}
.player-leave-to {
  transform: translateY(100%);
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .player-enter-active,
  .player-leave-active {
    transition: opacity .2s ease;
  }
  .player-enter-from,
  .player-leave-to {
    transform: none;
  }
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
.app-main {
  min-width: 0;
  overflow-y: auto;
  container: app / inline-size;
}
.app-main.has-player {
  padding-bottom: calc(var(--row-h) + 56px);
}

@container (max-width: 900px) {
  .app-container { --sidebar-w: 66px; }
}
</style>
