<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-brand">
        <div class="brand-glyph">D</div>
        <span class="brand-name">Diggy</span>
      </div>

      <h1 class="login-title">{{ isRegister ? 'Créer un compte' : 'Connexion' }}</h1>

      <form class="login-form" @submit.prevent="submit">
        <div class="field">
          <label class="field-label">Email</label>
          <input v-model="email" type="email" class="field-input" required autocomplete="email" />
        </div>

        <div v-if="isRegister" class="field">
          <label class="field-label">Nom d'utilisateur</label>
          <input v-model="username" type="text" class="field-input" required autocomplete="username" />
        </div>

        <div class="field">
          <label class="field-label">Mot de passe</label>
          <input v-model="password" type="password" class="field-input" required autocomplete="current-password" />
        </div>

        <p v-if="error" class="login-error">{{ error }}</p>

        <button type="submit" class="btn-primary" :disabled="loading">
          {{ loading ? '…' : (isRegister ? 'Créer le compte' : 'Se connecter') }}
        </button>
      </form>

      <button class="login-switch" @click="isRegister = !isRegister">
        {{ isRegister ? 'Déjà un compte ? Connexion' : 'Créer un compte' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const router = useRouter()
const auth = useAuthStore()

const email = ref('')
const username = ref('')
const password = ref('')
const isRegister = ref(false)
const loading = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  loading.value = true
  try {
    if (isRegister.value) {
      await auth.register(email.value, username.value, password.value)
    } else {
      await auth.login(email.value, password.value)
    }
    router.push('/')
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
  padding: 36px 32px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.login-brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-glyph {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  background: var(--accent);
  color: var(--on-accent, #fff);
  display: grid;
  place-items: center;
  font: 700 15px/1 var(--font-ui);
}

.brand-name {
  font: 600 16px/1 var(--font-ui);
  letter-spacing: -0.02em;
  color: var(--ink);
}

.login-title {
  font: 600 22px/1.2 var(--font-ui);
  color: var(--ink);
  margin: 0;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.field-label {
  font: 500 12px/1 var(--font-ui);
  color: var(--ink-2);
  letter-spacing: 0.02em;
}

.field-input {
  background: var(--surface-2);
  border: 1px solid var(--line-2);
  border-radius: 8px;
  padding: 9px 12px;
  font: 400 14px/1 var(--font-ui);
  color: var(--ink);
  outline: none;
  transition: border-color 0.15s;
}

.field-input:focus {
  border-color: var(--accent);
}

.login-error {
  font: 400 13px/1.4 var(--font-ui);
  color: var(--error);
  margin: 0;
}

.btn-primary {
  background: var(--accent);
  color: var(--on-accent);
  border: none;
  border-radius: 8px;
  padding: 11px 16px;
  font: 600 14px/1 var(--font-ui);
  cursor: pointer;
  transition: background 0.15s;
  margin-top: 4px;
}

.btn-primary:hover:not(:disabled) {
  background: var(--accent-hover);
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.login-switch {
  background: none;
  border: none;
  color: var(--accent-ink);
  font: 400 13px/1 var(--font-ui);
  cursor: pointer;
  padding: 0;
  text-align: left;
}

.login-switch:hover {
  text-decoration: underline;
}
</style>
