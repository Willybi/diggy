<template>
  <div class="app-shell">
    <SidebarNav class="app-sidebar" />
    <main class="app-main">
      <RouterView />
    </main>
  </div>
</template>

<script setup>
import SidebarNav from './components/SidebarNav.vue'
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
.app-shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
}
.app-sidebar {
  width: 232px;
  flex: none;
}
.app-main {
  flex: 1 1 0;
  min-width: 0;
  overflow-y: auto;
}
</style>
