import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from 'axios'

export const useAudioPlayer = defineStore('audioPlayer', () => {
  const playingId = ref(null)
  let audio = null
  let lastGenreTrack = null

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

  async function playRandom(genreName) {
    stop()
    try {
      const params = { genre: genreName }
      if (lastGenreTrack) params.exclude = lastGenreTrack
      const { data } = await axios.get('/api/genres/random-track', { params })
      const catalogId = data.catalog_id
      lastGenreTrack = catalogId
      const { data: prev } = await axios.get(`/api/catalog/${catalogId}/preview-url`)
      audio = new Audio(prev.preview_url)
      audio.play()
      playingId.value = `genre:${genreName}`
      audio.addEventListener('ended', stop)
    } catch {
      lastGenreTrack = null
    }
  }

  return { playingId, toggle, stop, playRandom }
})
