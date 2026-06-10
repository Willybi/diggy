import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

export const useAudioPlayer = defineStore('audioPlayer', () => {
  const playingId = ref(null)
  let audio = null

  function stop() {
    if (audio) {
      audio.pause()
      audio = null
    }
    playingId.value = null
  }

  async function toggle(id, catalogId) {
    if (playingId.value === id) {
      stop()
      return
    }
    stop()
    try {
      const { data } = await axios.get(`/api/catalog/${catalogId}/preview-url`)
      audio = new Audio(data.preview_url)
      audio.play()
      playingId.value = id
      audio.addEventListener('ended', stop)
    } catch { /* pas de preview */ }
  }

  return { playingId, toggle, stop }
})
