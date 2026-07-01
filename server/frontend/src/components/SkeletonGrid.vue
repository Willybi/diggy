<template>
  <template v-for="i in count" :key="i">
    <div class="skeleton-card">
      <div class="sk-art"></div>
      <div class="sk-body">
        <div class="sk-line w60"></div>
        <div class="sk-line w40"></div>
      </div>
    </div>
  </template>
</template>

<script setup>
defineProps({
  count: { type: Number, default: 12 },
})
</script>

<style scoped>
.skeleton-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  overflow: hidden;
}
.sk-art {
  height: 130px;
  background: var(--surface-2);
  animation: shimmer 1.2s ease-in-out infinite alternate;
}
.sk-body {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.sk-line {
  height: 14px;
  border-radius: 4px;
  background: var(--surface-2);
  animation: shimmer 1.2s ease-in-out infinite alternate;
}
.sk-line.w60 {
  width: 60%;
}
.sk-line.w40 {
  width: 40%;
}
@keyframes shimmer {
  from {
    opacity: 0.6;
  }
  to {
    opacity: 1;
  }
}
@media (prefers-reduced-motion: reduce) {
  .sk-art,
  .sk-line {
    animation: none;
  }
}
</style>
