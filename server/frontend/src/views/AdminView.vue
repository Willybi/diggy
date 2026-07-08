<template>
  <div class="admin-view">
    <header class="view-header">
      <h1 class="view-title">Admin</h1>
      <div class="tab-bar">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          class="tab-btn"
          :class="{ active: activeTab === tab.id }"
          @click="activeTab = tab.id"
        >
          {{ tab.label }}
        </button>
      </div>
    </header>

    <AdminArtists v-if="activeTab === 'artists'" />
    <AdminFlags v-else-if="activeTab === 'flags'" />
    <AdminSets v-else-if="activeTab === 'sets'" />
    <AdminGenres v-else-if="activeTab === 'genres'" />
    <AdminCrawl v-else-if="activeTab === 'crawl'" />
    <AdminBeatport v-else-if="activeTab === 'beatport'" />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import AdminArtists from '../components/admin/AdminArtists.vue'
import AdminFlags from '../components/admin/AdminFlags.vue'
import AdminSets from '../components/admin/AdminSets.vue'
import AdminGenres from '../components/admin/AdminGenres.vue'
import AdminCrawl from '../components/admin/AdminCrawl.vue'
import AdminBeatport from '../components/admin/AdminBeatport.vue'

const tabs = [
  { id: 'artists', label: 'Artistes' },
  { id: 'flags', label: 'Flags' },
  { id: 'sets', label: 'Sets' },
  { id: 'genres', label: 'Genres' },
  { id: 'crawl', label: 'Crawl' },
  { id: 'beatport', label: 'Beatport' },
]

const activeTab = ref('artists')
</script>

<style scoped>
.admin-view {
  padding: var(--pad) calc(var(--pad) * 1.5);
  max-width: 1100px;
  margin: 0 auto;
}
.view-header {
  margin-bottom: var(--space-6);
}
.view-title {
  font: 600 var(--fs-lg)/1.1 var(--font-ui);
  letter-spacing: -0.02em;
  color: var(--ink);
  margin-bottom: var(--space-4);
}
.tab-bar {
  display: flex;
  gap: var(--space-1);
  border-bottom: 1px solid var(--line);
  padding-bottom: 0;
}
.tab-btn {
  padding: var(--space-2) var(--space-4);
  border: none;
  background: none;
  color: var(--ink-3);
  font: 500 var(--fs-sm)/1 var(--font-ui);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition:
    color 0.12s,
    border-color 0.12s;
}
.tab-btn:hover {
  color: var(--ink);
}
.tab-btn.active {
  color: var(--accent-ink);
  border-bottom-color: var(--accent);
}
</style>
