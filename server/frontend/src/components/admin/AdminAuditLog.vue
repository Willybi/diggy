<template>
  <section class="al-wrap">
    <div class="at-region">
      <div class="at-head">
        <h2 class="at-title">
          Journal d'audit
          <span v-if="total" class="at-count">{{ total.toLocaleString('fr-FR') }}</span>
        </h2>
        <p class="al-sub">
          Qui a fait quoi, et quand — actions admin sensibles, les plus récentes d'abord.
        </p>
      </div>

      <div v-if="loading" class="at-empty">Chargement…</div>
      <div v-else-if="error" class="at-empty al-error">{{ error }}</div>
      <div v-else-if="items.length === 0" class="at-empty">Aucune entrée d'audit.</div>

      <div v-else class="at-scroll">
        <table class="at-table">
          <thead>
            <tr>
              <th>Cible</th>
              <th>Date</th>
              <th>Auteur</th>
              <th>Action</th>
              <th>Détails</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="entry in items" :key="entry.id">
              <td data-label="Cible" data-lead>
                <span class="at-id">{{ targetLabel(entry) }}</span>
              </td>
              <td class="at-tech" data-label="Date">
                {{ formatDate(entry.created_at) }}
              </td>
              <td class="at-tech" data-label="Auteur">
                {{ entry.user_email || '—' }}
              </td>
              <td data-label="Action">
                <span class="at-pill at-pill--neutral">{{ entry.action }}</span>
              </td>
              <td data-label="Détails" data-stack>
                <details v-if="hasDetails(entry.details)" class="at-details">
                  <summary>
                    <AdminIcon name="chevron" :size="11" class="at-details-chev" />
                    Voir le payload
                  </summary>
                  <div class="at-kv">
                    <template v-for="(v, k) in entry.details" :key="k">
                      <span class="at-kv-k">{{ k }}</span>
                      <span class="at-kv-v">{{ formatVal(v) }}</span>
                    </template>
                  </div>
                </details>
                <span v-else class="al-dash">—</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="totalPages > 1" class="at-pager">
        <button class="btn btn--sm" :disabled="page <= 1" @click="prevPage()">Précédent</button>
        <span class="at-pager-count">{{ page }} / {{ totalPages }}</span>
        <button class="btn btn--sm" :disabled="page >= totalPages" @click="nextPage()">
          Suivant
        </button>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../../utils/api.js'
import AdminIcon from './AdminIcon.vue'

const PER_PAGE = 20

const items = ref([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const error = ref('')

const totalPages = computed(() => Math.ceil(total.value / PER_PAGE))

async function fetchPage() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get('/api/admin/audit-log', {
      params: { page: page.value, per_page: PER_PAGE },
    })
    items.value = data.items
    total.value = data.total
  } catch (e) {
    error.value = e.response?.data?.detail || 'Erreur de chargement du journal'
    items.value = []
  } finally {
    loading.value = false
  }
}

function prevPage() {
  if (page.value <= 1) return
  page.value--
  fetchPage()
}

function nextPage() {
  if (page.value >= totalPages.value) return
  page.value++
  fetchPage()
}

// Cible = target_type #id (D9/B), tiret neutre si l'entrée n'en porte pas.
function targetLabel(entry) {
  if (!entry.target_type) return '—'
  return entry.target_id != null ? `${entry.target_type} #${entry.target_id}` : entry.target_type
}

function hasDetails(details) {
  return details && typeof details === 'object' && Object.keys(details).length > 0
}

// Valeur d'une paire du payload (D9) : scalaire brut, jamais de JSON à accolades —
// un objet imbriqué (rare) est aplati en chaîne compacte, borné par la cellule.
function formatVal(v) {
  if (v === null) return 'null'
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

function formatDate(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(d.getDate())}/${pad(d.getMonth() + 1)} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

onMounted(() => {
  fetchPage()
})
</script>

<style scoped>
.al-wrap {
  margin-bottom: var(--space-8);
}

/* Sous-titre existant conservé, en eyebrow discret fer à droite de l'en-tête. */
.al-sub {
  margin: 0;
  max-width: 48ch;
  font: 400 var(--fs-sm)/1.4 var(--font-ui);
  color: var(--ink-3);
  text-align: right;
}

/* État d'erreur de chargement : même ligne que l'état vide, teinte négative. */
.al-error {
  color: var(--neg-ink);
}

/* Cellule sans payload : tiret neutre mono, aligné sur les valeurs techniques. */
.al-dash {
  font: 400 var(--fs-xs)/1 var(--font-mono);
  color: var(--ink-3);
}

/* Payload D9 : clé à largeur fixe dans la grille clé·valeur du socle. */
.at-kv-k {
  min-width: 104px;
}

@container (max-width: 859px) {
  /* En-tête empilé (socle) : le sous-titre repasse à gauche. */
  .al-sub {
    text-align: left;
  }
}
</style>
