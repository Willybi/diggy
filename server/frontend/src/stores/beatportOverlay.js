import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { useAudioPlayer } from './audioPlayer.js'

// State of the single global Beatport preview overlay (D12): every surface's
// Beatport play button opens THE one overlay mounted in App.vue. The embed
// iframe is a licensing black box — this store never touches its audio; it
// only PAUSES the Deezer player on open (pause, not close(): the bar stays up
// so the user resumes afterwards — never two audios at once).
export const useBeatportOverlay = defineStore('beatportOverlay', () => {
  // { id, title, artist, beatport_id } | null — null = overlay closed.
  const track = ref(null)

  const visible = computed(() => track.value !== null)

  function open(trackObj) {
    const player = useAudioPlayer()
    if (player.playing) player.toggle()
    track.value = {
      id: trackObj.catalog_id ?? trackObj.id,
      title: trackObj.title || '',
      artist: trackObj.artist || '',
      beatport_id: trackObj.beatport_id,
    }
  }

  function close() {
    track.value = null
  }

  return { track, visible, open, close }
})
