<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-brand">
        <div class="brand-glyph">D</div>
        <span class="brand-name">Diggy</span>
      </div>

      <h1 class="login-title">Connexion</h1>
      <p class="login-sub">Connecte-toi avec ton compte Google pour continuer.</p>

      <div id="g_id_signin" class="google-btn-wrap"></div>

      <p v-if="error" class="login-error">{{ error }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const router = useRouter()
const auth = useAuthStore()
const error = ref('')

async function handleCredential(response) {
  error.value = ''
  try {
    await auth.googleLogin(response.credential)
    router.push('/')
  } catch (e) {
    error.value = e.message
  }
}

onMounted(() => {
  // Expose callback globally for GSI
  window.__diggyGoogleCallback = handleCredential

  const script = document.createElement('script')
  script.src = 'https://accounts.google.com/gsi/client'
  script.async = true
  script.onload = () => {
    window.google.accounts.id.initialize({
      client_id: import.meta.env.VITE_GOOGLE_CLIENT_ID || '',
      callback: window.__diggyGoogleCallback,
    })
    window.google.accounts.id.renderButton(
      document.getElementById('g_id_signin'),
      {
        type: 'standard',
        theme: 'outline',
        size: 'large',
        text: 'signin_with',
        shape: 'rectangular',
        width: 296,
      },
    )
  }
  document.head.appendChild(script)
})
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
  gap: 16px;
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

.login-sub {
  font: 400 13px/1.4 var(--font-ui);
  color: var(--ink-2);
  margin: 0;
}

.google-btn-wrap {
  display: flex;
  justify-content: center;
  margin: 4px 0;
}

.login-error {
  font: 400 13px/1.4 var(--font-ui);
  color: var(--error);
  margin: 0;
}
</style>
