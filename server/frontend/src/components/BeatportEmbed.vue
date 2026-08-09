<template>
  <div ref="root" class="bp-embed">
    <iframe
      v-if="visible"
      class="bp-frame"
      :src="embedSrc"
      loading="lazy"
      scrolling="no"
      title="Extrait Beatport"
    ></iframe>
    <div v-else class="bp-frame bp-frame--placeholder" aria-hidden="true"></div>
    <a class="bp-link" :href="trackUrl" target="_blank" rel="noopener">Voir sur Beatport ↗</a>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  beatportId: { type: [Number, String], required: true },
})

const root = ref(null)
const visible = ref(false)
let observer = null

// Official Beatport embed player — the ONLY licensed way to play Beatport
// samples (direct sample_url playback is contractually excluded). The iframe
// is a black box: no bridge to the audioPlayer store, ever.
const embedSrc = computed(() => `https://embed.beatport.com/?id=${props.beatportId}&type=track`)
const trackUrl = computed(() => `https://www.beatport.com/track/-/${props.beatportId}`)

onMounted(() => {
  // One-shot lazy mount: the iframe only loads once the block nears the
  // viewport. Without IntersectionObserver (old browsers, jsdom) render eager.
  if (typeof IntersectionObserver === 'undefined') {
    visible.value = true
    return
  }
  observer = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting) {
        visible.value = true
        observer.disconnect()
        observer = null
      }
    },
    { rootMargin: '0px 0px 200px 0px' },
  )
  observer.observe(root.value)
})

onUnmounted(() => {
  observer?.disconnect()
})
</script>

<style scoped>
.bp-embed {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  width: 100%;
  /* official embed recommendation (width 100%, capped at 600px) */
  max-width: 600px;
}
/* 162px = fixed height of the official Beatport track embed; the placeholder
   reserves the exact same box so the lazy mount causes no layout shift */
.bp-frame {
  display: block;
  width: 100%;
  height: 162px;
  border: 0;
  border-radius: var(--r-md);
  background: var(--surface-2);
}
.bp-frame--placeholder {
  border: 1px solid var(--line);
  box-sizing: border-box;
}
.bp-link {
  align-self: flex-end;
  font: 500 var(--fs-xs) / 1 var(--font-ui);
  color: var(--accent-ink);
  text-decoration: none;
}
.bp-link:hover {
  text-decoration: underline;
}
.bp-link:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
</style>
