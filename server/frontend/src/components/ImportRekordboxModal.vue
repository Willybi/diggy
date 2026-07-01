<template>
  <div
    class="modal-overlay"
    @dragover.prevent
    @drop.prevent
    @click.self="handleOverlayClick"
  >
    <div class="modal-box">
      <h2 class="modal-title">Importer depuis Rekordbox</h2>

      <!-- idle -->
      <template v-if="phase === 'idle'">
        <div
          class="drop-zone"
          :class="{ 'drop-zone--over': dragOver }"
          @dragover.prevent="onDragOver"
          @dragleave="onDragLeave"
          @drop.prevent="onDrop"
        >
          <svg class="drop-icon" viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1.8">
            <rect x="6" y="8" width="36" height="32" rx="3" />
            <path d="M16 20h16M16 27h10" stroke-linecap="round" />
            <path d="M30 34l4-4-4-4" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <p class="drop-label">Déposer votre export XML ici</p>
          <p class="drop-or">ou</p>
          <button class="btn-accent" @click="openFilePicker">Parcourir</button>
          <input
            ref="fileInput"
            type="file"
            accept=".xml"
            class="file-input-hidden"
            @change="handleFileChange"
          />
        </div>

        <div class="instructions">
          <p>
            Dans Rekordbox :
            <strong>Fichier → Exporter la collection dans la liste des pistes → XML</strong>
          </p>
        </div>

        <div class="modal-foot">
          <button class="btn-ghost" @click="emit('close')">Annuler</button>
        </div>
      </template>

      <!-- uploading -->
      <template v-else-if="phase === 'uploading'">
        <div class="state-body">
          <div class="spinner"></div>
          <p class="state-label">Envoi en cours…</p>
        </div>
      </template>

      <!-- processing -->
      <template v-else-if="phase === 'processing' && stats.total === 0">
        <div class="state-body">
          <div class="spinner"></div>
          <p class="state-label">Import en cours…</p>
        </div>
      </template>

      <!-- processing with known total -->
      <template v-else-if="phase === 'processing'">
        <div class="state-body">
          <div class="progress-wrap">
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: progressPct + '%' }"></div>
            </div>
            <span class="progress-pct">{{ progressPct }}%</span>
          </div>
          <p class="state-label">
            {{ stats.inserted }} importés · {{ stats.updated }} mis à jour · {{ stats.total }} tracks
          </p>
        </div>
      </template>

      <!-- done -->
      <template v-else-if="phase === 'done'">
        <div class="state-body">
          <div class="done-icon">
            <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2.5">
              <circle cx="24" cy="24" r="20" />
              <path d="M15 24l7 7 11-14" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </div>
          <p class="state-label">
            <strong>{{ stats.inserted }}</strong> nouveaux tracks ·
            <strong>{{ stats.updated }}</strong> mis à jour
          </p>
          <button class="btn-accent" @click="handleDone">Voir ma bibliothèque</button>
        </div>
      </template>

      <!-- error -->
      <template v-else-if="phase === 'error'">
        <div class="state-body">
          <div class="error-icon">
            <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="2.5">
              <circle cx="24" cy="24" r="20" />
              <path d="M24 16v10M24 32v1" stroke-linecap="round" />
            </svg>
          </div>
          <p class="error-msg">{{ errorMsg }}</p>
          <button class="btn-ghost" @click="reset">Réessayer</button>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onUnmounted } from 'vue'
import { useAuthStore } from '../stores/auth.js'
import api from '../utils/api.js'

const emit = defineEmits(['close', 'done'])

const auth = useAuthStore()
const fileInput = ref(null)

const phase = ref('idle')
const dragOver = ref(false)
const taskId = ref(null)
const stats = ref({ inserted: 0, updated: 0, total: 0 })
const errorMsg = ref('')
let pollTimer = null

const progressPct = computed(() => {
  const done = stats.value.inserted + stats.value.updated
  if (!stats.value.total) return 0
  return Math.min(100, Math.round((done / stats.value.total) * 100))
})

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

onUnmounted(stopPoll)

function handleOverlayClick() {
  if (phase.value === 'idle') emit('close')
}

function openFilePicker() {
  fileInput.value?.click()
}

function handleFileChange(e) {
  const file = e.target.files?.[0]
  if (file) processFile(file)
}

function onDragOver() {
  dragOver.value = true
}

function onDragLeave() {
  dragOver.value = false
}

function onDrop(e) {
  dragOver.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) processFile(file)
}

function validateFile(file) {
  if (!file.name.toLowerCase().endsWith('.xml')) {
    return 'Ce fichier n\'est pas un export XML Rekordbox valide'
  }
  if (file.size > 10 * 1024 * 1024) {
    return 'Fichier trop volumineux (max 10 Mo)'
  }
  return null
}

async function processFile(file) {
  const validationError = validateFile(file)
  if (validationError) {
    errorMsg.value = validationError
    phase.value = 'error'
    return
  }

  phase.value = 'uploading'

  const formData = new FormData()
  formData.append('file', file)

  let res
  try {
    res = await fetch('/api/import/rekordbox-xml', {
      method: 'POST',
      headers: { Authorization: `Bearer ${auth.token}` },
      body: formData,
    })
  } catch {
    errorMsg.value = 'Erreur lors de l\'import, réessayez'
    phase.value = 'error'
    return
  }

  if (!res.ok) {
    if (res.status === 409) {
      errorMsg.value = 'Un import est déjà en cours, réessayez dans quelques minutes'
    } else if (res.status === 413) {
      errorMsg.value = 'Fichier trop volumineux (max 10 Mo)'
    } else if (res.status === 422) {
      errorMsg.value = 'Ce fichier n\'est pas un export XML Rekordbox valide'
    } else {
      errorMsg.value = 'Erreur lors de l\'import, réessayez'
    }
    phase.value = 'error'
    return
  }

  const data = await res.json()
  taskId.value = data.task_id
  phase.value = 'processing'
  startPoll()
}

function startPoll() {
  pollTimer = setInterval(async () => {
    try {
      const { data } = await api.get(`/api/import/status/${taskId.value}`)
      if (data.total != null) stats.value.total = data.total
      if (data.inserted != null) stats.value.inserted = data.inserted
      if (data.updated != null) stats.value.updated = data.updated

      if (data.status === 'done') {
        stopPoll()
        phase.value = 'done'
      } else if (data.status === 'error') {
        stopPoll()
        errorMsg.value = 'Erreur lors de l\'import, réessayez'
        phase.value = 'error'
      }
    } catch {
      stopPoll()
      errorMsg.value = 'Erreur lors de l\'import, réessayez'
      phase.value = 'error'
    }
  }, 2000)
}

function handleDone() {
  emit('done')
  emit('close')
}

function reset() {
  stopPoll()
  taskId.value = null
  stats.value = { inserted: 0, updated: 0, total: 0 }
  errorMsg.value = ''
  phase.value = 'idle'
  if (fileInput.value) fileInput.value.value = ''
}
</script>

<style scoped>
/* ============ OVERLAY ============ */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: var(--overlay-modal);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
  padding: 24px;
}

/* ============ BOX ============ */
.modal-box {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-lg, 16px);
  box-shadow: var(--shadow-lg);
  width: 100%;
  max-width: 480px;
  padding: 28px 28px 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.modal-title {
  margin: 0;
  font: 600 18px/1.2 var(--font-ui);
  color: var(--ink);
}

/* ============ DROP ZONE ============ */
.drop-zone {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  border: 2px dashed var(--line-2);
  border-radius: var(--r-md, 10px);
  padding: 32px 24px;
  text-align: center;
  cursor: default;
  transition:
    border-color 0.15s,
    background 0.15s;
}

.drop-zone--over {
  border-color: var(--accent);
  background: var(--accent-soft);
}

.drop-icon {
  width: 48px;
  height: 48px;
  color: var(--ink-3);
}

.drop-zone--over .drop-icon {
  color: var(--accent-ink);
}

.drop-label {
  margin: 0;
  font: 500 15px var(--font-ui);
  color: var(--ink);
}

.drop-or {
  margin: 0;
  font: 400 13px var(--font-mono);
  color: var(--ink-3);
}

.file-input-hidden {
  display: none;
}

/* ============ INSTRUCTIONS ============ */
.instructions {
  background: var(--surface-2);
  border-radius: var(--r-sm, 6px);
  padding: 12px 14px;
}

.instructions p {
  margin: 0;
  font: 400 13px/1.5 var(--font-ui);
  color: var(--ink-2);
}

.instructions strong {
  color: var(--ink);
  font-weight: 600;
}

/* ============ FOOTER ============ */
.modal-foot {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

/* ============ BUTTONS ============ */
.btn-accent {
  display: inline-flex;
  align-items: center;
  height: 38px;
  padding: 0 18px;
  border-radius: var(--r-sm, 6px);
  border: none;
  background: var(--accent);
  color: var(--on-accent);
  font: 600 13.5px var(--font-ui);
  cursor: pointer;
  transition: background 0.12s;
}

.btn-accent:hover {
  background: var(--accent-hover);
}

.btn-ghost {
  display: inline-flex;
  align-items: center;
  height: 38px;
  padding: 0 16px;
  border-radius: var(--r-sm, 6px);
  border: 1px solid var(--line-2);
  background: transparent;
  color: var(--ink-2);
  font: 500 13.5px var(--font-ui);
  cursor: pointer;
  transition:
    background 0.12s,
    color 0.12s;
}

.btn-ghost:hover {
  background: var(--surface-2);
  color: var(--ink);
}

/* ============ STATE BODY (uploading / processing / done / error) ============ */
.state-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 20px 0 8px;
  text-align: center;
}

.state-label {
  margin: 0;
  font: 400 14px/1.5 var(--font-ui);
  color: var(--ink-2);
}

.state-label strong {
  color: var(--ink);
  font-weight: 600;
}

/* ============ SPINNER ============ */
.spinner {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  border: 3px solid var(--line-2);
  border-top-color: var(--accent);
  animation: spin 0.75s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* ============ PROGRESS BAR ============ */
.progress-wrap {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
}

.progress-bar {
  flex: 1;
  height: 8px;
  background: var(--surface-2);
  border-radius: 999px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 999px;
  transition: width 0.4s ease;
}

.progress-pct {
  flex: none;
  font: 600 12px/1 var(--font-mono);
  color: var(--accent-ink);
  min-width: 36px;
  text-align: right;
}

/* ============ DONE ICON ============ */
.done-icon {
  width: 52px;
  height: 52px;
  color: var(--pos-ink);
}

.done-icon svg {
  width: 100%;
  height: 100%;
  stroke: var(--pos-ink);
}

/* ============ ERROR ICON ============ */
.error-icon {
  width: 52px;
  height: 52px;
  color: var(--neg-ink);
}

.error-icon svg {
  width: 100%;
  height: 100%;
  stroke: var(--neg-ink);
}

.error-msg {
  margin: 0;
  font: 500 14px/1.5 var(--font-ui);
  color: var(--neg-ink);
  text-align: center;
}
</style>
