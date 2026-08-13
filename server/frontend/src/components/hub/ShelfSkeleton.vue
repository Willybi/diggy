<template>
  <div class="discover" aria-busy="true" aria-hidden="true">
    <span class="sk-title"></span>
    <div class="hb-shelfgrid">
      <span v-for="n in count" :key="n" class="sk-card">
        <span class="sk-cover"></span>
        <span class="sk-body">
          <span class="sk-line sk-line--1"></span>
          <span class="sk-line sk-line--2"></span>
          <span class="sk-line sk-line--3"></span>
        </span>
      </span>
    </div>
  </div>
</template>

<script setup>
// Placeholder shown while an async Hub section chunk is still downloading. It is
// deliberately self-contained (no <DiscoveryCard> import) so it can live in the
// main bundle as the defineAsyncComponent fallback without dragging the heavy
// shelf components back into it. Layout mirrors .hb-shelfgrid so the section
// doesn't jump when the real cards resolve in.
defineProps({
  count: { type: Number, default: 9 },
})
</script>

<style scoped>
.discover {
  width: 100%;
  max-width: 960px;
  margin: var(--space-2) auto 0;
}
.sk-title {
  display: block;
  width: 180px;
  height: 16px;
  margin: 0 0 var(--space-4);
  border-radius: 6px;
  background: var(--surface-3);
  animation: sk-pulse 1.4s ease-in-out infinite;
}
.hb-shelfgrid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-3);
  padding: 0 0 var(--space-4);
}
.sk-card {
  display: flex;
  gap: var(--space-25);
  padding: var(--space-2);
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  min-width: 0;
}
.sk-cover {
  width: 64px;
  height: 64px;
  flex-shrink: 0;
  border-radius: var(--r-sm);
  background: var(--surface-3);
  animation: sk-pulse 1.4s ease-in-out infinite;
}
.sk-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--space-15);
  justify-content: center;
  min-width: 0;
}
.sk-line {
  border-radius: 5px;
  animation: sk-pulse 1.4s ease-in-out infinite;
}
.sk-line--1 {
  height: 11px;
  width: 70%;
  background: var(--surface-3);
}
.sk-line--2 {
  height: 9px;
  width: 45%;
  background: var(--surface-2);
}
.sk-line--3 {
  height: 9px;
  width: 60%;
  background: var(--surface-2);
}
@keyframes sk-pulse {
  0%,
  100% {
    opacity: 0.4;
  }
  50% {
    opacity: 0.9;
  }
}

@container app (max-width: 720px) {
  .hb-shelfgrid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@container app (max-width: 640px) {
  .discover {
    max-width: 100%;
  }
  .hb-shelfgrid {
    grid-template-columns: 1fr;
  }
}
</style>
