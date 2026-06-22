<template>
  <span class="libdot" :class="inLib ? 'in' : 'out'" :title="inLib ? 'Dans ma lib' : 'Pas dans la lib'">
    <span class="d"></span>
  </span>
</template>

<script setup>
defineProps({
  inLib: { type: Boolean, required: true },
})
</script>

<style scoped>
.libdot {
  display: inline-grid;
  place-items: center;
  width: 22px;
  height: 22px;
}
.libdot .d {
  width: 11px;
  height: 11px;
  border-radius: 50%;
}
.libdot.in .d {
  background: var(--pos);
  box-shadow: 0 0 0 3px var(--pos-soft);
}
.libdot.out .d {
  background: transparent;
  border: 1.5px dashed var(--ink-3);
  opacity: .6;
}
</style>
