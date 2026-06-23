<template>
  <div class="app-container">
    <div class="app-shell">
      <SidebarNav class="app-sidebar" />
      <main class="app-main">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<script setup>
import { watch } from 'vue'
import { useRoute } from 'vue-router'
import SidebarNav from './components/SidebarNav.vue'
import { useAudioPlayer } from './stores/audioPlayer'

const route = useRoute()
const player = useAudioPlayer()
watch(() => route.path, () => player.stop())
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
</style>

<style scoped>
.app-container {
  container-type: inline-size;
  height: 100vh;
}
.app-shell {
  display: grid;
  grid-template-columns: 232px 1fr;
  height: 100%;
  overflow: hidden;
}
.app-main {
  min-width: 0;
  overflow-y: auto;
  container: app / inline-size;
}

@container (max-width: 900px) {
  .app-shell {
    grid-template-columns: 66px 1fr;
  }
}
</style>
