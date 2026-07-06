<template>
  <Transition name="toast">
    <div v-if="toast.visible" class="toast" :class="toast.type" @click="toast.hide()">
      <span>{{ toast.message }}</span>
      <button v-if="toast.action" class="toast-action" @click.stop="onAction">
        {{ toast.action.label }}
      </button>
    </div>
  </Transition>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useToast } from '../stores/toast.js'

const toast = useToast()
const router = useRouter()

function onAction() {
  toast.hide()
  if (toast.action?.route) router.push(toast.action.route)
}
</script>

<style scoped>
.toast {
  position: fixed;
  bottom: calc(var(--bottom-nav-h, 0px) + 16px);
  left: 50%;
  transform: translateX(-50%);
  z-index: 9000;
  padding: 10px 20px;
  border-radius: var(--r-sm);
  font: 500 13px/1.4 var(--font-ui);
  cursor: pointer;
  max-width: 90vw;
  text-align: center;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
}
.toast.error {
  background: var(--neg-soft);
  color: var(--neg-ink);
  border: 1px solid var(--neg-ink);
}
.toast.success {
  background: var(--pos-soft);
  color: var(--pos-ink);
  border: 1px solid var(--pos-ink);
}
.toast.info {
  background: var(--accent-soft);
  color: var(--accent-ink);
  border: 1px solid var(--accent-ink);
}
.toast-action {
  margin-left: 12px;
  padding: 4px 12px;
  border: none;
  border-radius: var(--r-xs);
  background: var(--accent);
  color: var(--bg);
  font: 600 12px/1 var(--font-ui);
  cursor: pointer;
}
.toast-action:hover {
  background: var(--accent-hover);
}
.toast-enter-active,
.toast-leave-active {
  transition:
    opacity 0.25s ease,
    transform 0.25s ease;
}
.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(12px);
}
</style>
