<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-brand">
        <div class="brand-glyph">D</div>
        <span class="brand-name">Diggy</span>
      </div>

      <h1 class="login-title">Connexion</h1>

      <p v-if="error" class="login-error">{{ error }}</p>

      <button class="google-btn" @click="handleLogin" :disabled="loading">
        <svg class="google-icon" viewBox="0 0 24 24" width="20" height="20">
          <path
            fill="#4285F4"
            d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"
          />
          <path
            fill="#34A853"
            d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
          />
          <path
            fill="#FBBC05"
            d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
          />
          <path
            fill="#EA4335"
            d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
          />
        </svg>
        {{ loading ? '…' : 'Se connecter avec Google' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useAuthStore } from '../stores/auth.js'

const auth = useAuthStore()
const loading = ref(false)
const error = ref('')

async function handleLogin() {
  error.value = ''
  loading.value = true
  try {
    await auth.loginWithGoogle()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
}

.login-card {
  width: 360px;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: var(--space-8) var(--space-8);
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.login-brand {
  display: flex;
  align-items: center;
  gap: var(--space-25);
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
}

.brand-name {
  font: 600 var(--fs-title)/1 var(--font-ui);
  letter-spacing: -0.02em;
  color: var(--ink);
}

.login-title {
  font: 600 var(--fs-lg)/1.2 var(--font-ui);
  color: var(--ink);
  margin: 0;
}

.login-error {
  font: 400 var(--fs-sm)/1.4 var(--font-ui);
  color: var(--error);
  margin: 0;
}

.google-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-25);
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-radius: 8px;
  padding: var(--space-25) var(--space-4);
  font: 600 var(--fs-base)/1 var(--font-ui);
  color: var(--ink);
  cursor: pointer;
  transition:
    background 0.15s,
    border-color 0.15s;
}

.google-btn:hover:not(:disabled) {
  background: var(--surface-2);
  border-color: var(--ink-3);
}

.google-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.google-icon {
  flex-shrink: 0;
}
</style>
