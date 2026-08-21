<template>
  <div class="collections-view">
    <div class="page-head">
      <div class="titles">
        <h1>Collections</h1>
        <div class="sub">
          {{ collections.length }} collection{{ collections.length !== 1 ? 's' : '' }}
          <template v-if="folders.length">
            · {{ folders.length }} dossier{{ folders.length !== 1 ? 's' : '' }}
          </template>
        </div>
      </div>
      <div class="head-tools">
        <button class="btn-folder" @click="openCreateFolder">
          <span class="plus">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
              <path
                d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"
                stroke-linejoin="round"
              />
            </svg>
          </span>
          <span class="addlbl">Nouveau dossier</span>
        </button>
        <button class="btn-add" @click="openCreateCollection">
          <span class="plus">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
              <path d="M12 5v14M5 12h14" stroke-linecap="round" />
            </svg>
          </span>
          <span class="addlbl">Nouvelle collection</span>
        </button>
      </div>
    </div>

    <div v-if="loading" class="state">Chargement…</div>
    <div v-else-if="!collections.length && !folders.length" class="state">
      Aucune collection — crée ta première playlist
    </div>

    <div v-else class="tree">
      <!-- Folders (one level, no nesting) -->
      <section v-for="folder in folders" :key="folder.id" class="folder">
        <header class="folder-head">
          <button class="folder-toggle" @click="toggleFolder(folder.id)">
            <span class="chevron" :class="{ open: isExpanded(folder.id) }">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M9 6l6 6-6 6" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </span>
            <span class="folder-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
                <path
                  d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"
                  stroke-linejoin="round"
                />
              </svg>
            </span>
            <span class="folder-name">{{ folder.name }}</span>
            <span class="folder-count"
              >{{ collectionsInFolder(folder.id).length }} collection{{
                collectionsInFolder(folder.id).length !== 1 ? 's' : ''
              }}</span
            >
          </button>
          <div class="folder-actions">
            <button class="ico-btn" title="Renommer" @click="openRenameFolder(folder)">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.7"
                stroke-linecap="round"
                stroke-linejoin="round"
              >
                <path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />
              </svg>
            </button>
            <button
              class="ico-btn ico-del"
              title="Supprimer le dossier"
              @click="confirmDeleteFolder(folder)"
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.7"
                stroke-linecap="round"
              >
                <path
                  d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"
                />
              </svg>
            </button>
          </div>
        </header>

        <div v-if="isExpanded(folder.id)" class="folder-body">
          <div v-if="!collectionsInFolder(folder.id).length" class="folder-empty">Dossier vide</div>
          <div v-else class="coll-grid">
            <CollectionCard
              v-for="coll in collectionsInFolder(folder.id)"
              :key="coll.id"
              :coll="coll"
              :folders="folders"
              @open="goTo"
              @assign="assignFolder"
              @delete="confirmDelete"
            />
          </div>
        </div>
      </section>

      <!-- Collections without a folder -->
      <section v-if="orphans.length || folders.length" class="folder orphans">
        <header class="folder-head is-static">
          <span class="folder-icon muted">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7">
              <path d="M4 7h16M4 12h16M4 17h16" stroke-linecap="round" stroke-dasharray="2 3" />
            </svg>
          </span>
          <span class="folder-name">Sans dossier</span>
          <span class="folder-count"
            >{{ orphans.length }} collection{{ orphans.length !== 1 ? 's' : '' }}</span
          >
        </header>
        <div class="folder-body">
          <div v-if="!orphans.length" class="folder-empty">Aucune collection ici</div>
          <div v-else class="coll-grid">
            <CollectionCard
              v-for="coll in orphans"
              :key="coll.id"
              :coll="coll"
              :folders="folders"
              @open="goTo"
              @assign="assignFolder"
              @delete="confirmDelete"
            />
          </div>
        </div>
      </section>
    </div>

    <!-- Create/rename modal (collection · folder · rename folder) -->
    <div v-if="modalMode" class="modal-overlay" @click.self="closeModal">
      <div class="modal-box">
        <h2>{{ modalTitle }}</h2>
        <input
          ref="nameInput"
          v-model="modalName"
          type="text"
          :placeholder="modalPlaceholder"
          @keydown.enter="submitModal"
          autofocus
        />
        <div class="modal-actions">
          <button class="btn-cancel" @click="closeModal">Annuler</button>
          <button class="btn-confirm" :disabled="!modalName.trim() || saving" @click="submitModal">
            {{ saving ? 'Enregistrement…' : modalSubmitLabel }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import api from '../utils/api.js'
import CollectionCard from '../components/CollectionCard.vue'

const router = useRouter()

const collections = ref([])
const folders = ref([])
const loading = ref(true)
const expanded = ref({})

// Modal: one box, three modes — create a collection, create a folder, rename one.
const modalMode = ref(null) // null | 'collection' | 'folder' | 'rename'
const modalName = ref('')
const renameTarget = ref(null)
const saving = ref(false)
const nameInput = ref(null)

const orphans = computed(() => collections.value.filter((c) => c.folder_id == null))

function collectionsInFolder(id) {
  return collections.value.filter((c) => c.folder_id === id)
}

function isExpanded(id) {
  return expanded.value[id] !== false
}

function toggleFolder(id) {
  expanded.value[id] = !isExpanded(id)
}

function goTo(coll) {
  router.push(`/collections/${coll.id}`)
}

async function fetchAll() {
  loading.value = true
  try {
    const [collRes, foldRes] = await Promise.all([
      api.get('/api/collections/'),
      api.get('/api/collections/folders'),
    ])
    collections.value = collRes.data
    folders.value = foldRes.data
  } finally {
    loading.value = false
  }
}

// --- Modal openers -------------------------------------------------------
async function focusName() {
  await nextTick()
  nameInput.value?.focus()
}

function openCreateCollection() {
  modalMode.value = 'collection'
  modalName.value = ''
  renameTarget.value = null
  focusName()
}

function openCreateFolder() {
  modalMode.value = 'folder'
  modalName.value = ''
  renameTarget.value = null
  focusName()
}

function openRenameFolder(folder) {
  modalMode.value = 'rename'
  modalName.value = folder.name
  renameTarget.value = folder
  focusName()
}

function closeModal() {
  modalMode.value = null
  modalName.value = ''
  renameTarget.value = null
}

const modalTitle = computed(() => {
  if (modalMode.value === 'folder') return 'Nouveau dossier'
  if (modalMode.value === 'rename') return 'Renommer le dossier'
  return 'Nouvelle collection'
})
const modalPlaceholder = computed(() =>
  modalMode.value === 'collection' ? 'Nom de la collection' : 'Nom du dossier',
)
const modalSubmitLabel = computed(() => (modalMode.value === 'rename' ? 'Renommer' : 'Créer'))

async function submitModal() {
  const name = modalName.value.trim()
  if (!name || saving.value) return
  saving.value = true
  try {
    if (modalMode.value === 'collection') {
      await api.post('/api/collections/', { name })
    } else if (modalMode.value === 'folder') {
      await api.post('/api/collections/folders', { name })
    } else if (modalMode.value === 'rename' && renameTarget.value) {
      await api.patch(`/api/collections/folders/${renameTarget.value.id}`, { name })
    }
    closeModal()
    await fetchAll()
  } finally {
    saving.value = false
  }
}

// --- Deletions & assignment ---------------------------------------------
async function confirmDelete(coll) {
  if (!confirm(`Supprimer « ${coll.name} » ?`)) return
  try {
    await api.delete(`/api/collections/${coll.id}`)
    await fetchAll()
  } catch {
    // silent — the api interceptor already toasts on failure
  }
}

async function confirmDeleteFolder(folder) {
  const n = collectionsInFolder(folder.id).length
  const warn = n
    ? `Supprimer le dossier « ${folder.name} » ? Ses ${n} collection${n !== 1 ? 's' : ''} deviendront « Sans dossier ».`
    : `Supprimer le dossier « ${folder.name} » ?`
  if (!confirm(warn)) return
  try {
    await api.delete(`/api/collections/folders/${folder.id}`)
    await fetchAll()
  } catch {
    // silent
  }
}

// Assign (or detach) a collection to/from a folder. `folderId` comes off the
// select as a string; '' means "Sans dossier" → null.
async function assignFolder(coll, folderId) {
  const target = folderId === '' || folderId == null ? null : Number(folderId)
  if (target === (coll.folder_id ?? null)) return
  try {
    await api.patch(`/api/collections/${coll.id}/folder`, { folder_id: target })
    await fetchAll()
  } catch {
    // silent
  }
}

onMounted(fetchAll)
</script>

<style scoped>
.collections-view {
  container-type: inline-size;
  min-height: 100%;
  max-width: var(--page-max-w);
  margin-inline: auto;
  width: 100%;
}

/* ============ PAGE HEAD ============ */
.titles h1 {
  margin: 0;
  font-size: var(--fs-xl);
  font-weight: 600;
  letter-spacing: -0.3px;
  color: var(--ink);
}
.sub {
  margin-top: var(--space-1);
  font: 500 var(--fs-sm)/1 var(--font-mono);
  color: var(--ink-2);
}
.head-tools {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

/* ============ BTNS ============ */
.btn-add,
.btn-folder {
  display: inline-flex;
  align-items: center;
  gap: var(--space-15);
  height: 38px;
  padding: 0 var(--space-4);
  border-radius: var(--r-sm);
  border: 1px solid transparent;
  font: 600 var(--fs-sm) var(--font-ui);
  cursor: pointer;
  white-space: nowrap;
}
.btn-add {
  background: var(--accent);
  color: var(--on-accent);
}
.btn-add:hover {
  background: var(--accent-hover);
}
.btn-folder {
  background: var(--surface);
  border-color: var(--line-2);
  color: var(--ink-2);
}
.btn-folder:hover {
  color: var(--ink);
  border-color: var(--ink-3);
}
.btn-add svg,
.btn-folder svg {
  width: 15px;
  height: 15px;
}

/* ============ TREE ============ */
.tree {
  padding: var(--space-4) var(--page-px) var(--space-8);
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}
.folder {
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--surface);
  overflow: hidden;
}
.folder-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) var(--space-4);
}
.folder-toggle {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex: 1;
  min-width: 0;
  border: none;
  background: transparent;
  padding: 0;
  cursor: pointer;
  text-align: left;
  color: inherit;
}
.folder-head.is-static {
  cursor: default;
}
.chevron {
  display: grid;
  place-items: center;
  color: var(--ink-3);
  transition: transform 0.14s;
}
.chevron.open {
  transform: rotate(90deg);
}
.chevron svg {
  width: 15px;
  height: 15px;
}
.folder-icon {
  display: grid;
  place-items: center;
  color: var(--ink-2);
}
.folder-icon.muted {
  color: var(--ink-3);
}
.folder-icon svg {
  width: 17px;
  height: 17px;
}
.folder-name {
  font: 600 var(--fs-title)/1 var(--font-ui);
  color: var(--ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.folder-count {
  font: 500 var(--fs-sm)/1 var(--font-mono);
  color: var(--ink-3);
  white-space: nowrap;
}
.folder-actions {
  display: flex;
  align-items: center;
  gap: var(--space-1);
}
.ico-btn {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border: none;
  background: transparent;
  color: var(--ink-3);
  border-radius: var(--r-xs);
  cursor: pointer;
  transition: color 0.14s;
}
.ico-btn:hover {
  color: var(--ink);
}
.ico-del:hover {
  color: var(--neg-ink);
}
.ico-btn svg {
  width: 16px;
  height: 16px;
}
.folder-body {
  border-top: 1px solid var(--line);
  padding: var(--space-4);
}
.folder-empty {
  font: 500 var(--fs-sm)/1 var(--font-mono);
  color: var(--ink-3);
  padding: var(--space-2) 0;
}

/* ============ GRID ============ */
.coll-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: var(--space-4);
}

/* ============ MODAL ============ */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: var(--overlay-modal);
  display: grid;
  place-items: center;
  z-index: 900;
}
.modal-box {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  padding: var(--space-6);
  width: 380px;
  max-width: calc(100vw - 32px);
  box-shadow: var(--shadow-lg);
}
.modal-box h2 {
  margin: 0 0 var(--space-4);
  font: 600 var(--fs-md)/1 var(--font-ui);
  color: var(--ink);
}
.modal-box input {
  width: 100%;
  height: 42px;
  padding: 0 var(--space-4);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  background: var(--bg);
  font: 400 var(--fs-input) var(--font-ui);
  color: var(--ink);
  outline: none;
  box-sizing: border-box;
}
.modal-box input::placeholder {
  color: var(--ink-3);
}
.modal-box input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-25);
  margin-top: var(--space-5);
}
.btn-cancel {
  height: 38px;
  padding: 0 var(--space-4);
  border-radius: var(--r-sm);
  border: 1px solid var(--line-2);
  background: var(--surface);
  color: var(--ink-2);
  font: 500 var(--fs-sm) var(--font-ui);
  cursor: pointer;
}
.btn-cancel:hover {
  color: var(--ink);
  border-color: var(--ink-3);
}
.btn-confirm {
  height: 38px;
  padding: 0 var(--space-5);
  border-radius: var(--r-sm);
  border: none;
  background: var(--accent);
  color: var(--on-accent);
  font: 600 var(--fs-sm) var(--font-ui);
  cursor: pointer;
}
.btn-confirm:hover {
  background: var(--accent-hover);
}
.btn-confirm:disabled {
  opacity: 0.5;
  cursor: default;
}

/* ============ STATES ============ */
.state {
  /* diverges from canonical .state: horizontal page padding (listing view) */
  padding: var(--space-10) var(--page-px);
}

/* ============ RESPONSIVE ============ */
@container (max-width: 640px) {
  .page-head {
    padding-left: var(--page-px-mobile);
    padding-right: var(--page-px-mobile);
  }
  .tree {
    padding: var(--space-4) var(--page-px-mobile) var(--space-6);
  }
  .state {
    padding-left: var(--page-px-mobile);
    padding-right: var(--page-px-mobile);
  }
  .addlbl {
    display: none;
  }
  .btn-add,
  .btn-folder {
    padding: 0 var(--space-3);
  }
}
@container (max-width: 500px) {
  .coll-grid {
    grid-template-columns: 1fr;
  }
}
</style>
