import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '../utils/api.js'

const VOLUME_KEY = 'diggy:volume'

export const useAudioPlayer = defineStore('audioPlayer', () => {
  // --- reactive state ---
  const track = ref(null) // { id, catalog_id, title, artist, bpm, key } | null
  const playing = ref(false)
  const currentTime = ref(0)
  const duration = ref(30)
  const volume = ref(parseFloat(localStorage.getItem(VOLUME_KEY)) || 0.8)
  const muted = ref(false)
  const loading = ref(false)
  const genrePlaying = ref(null) // genre name string during playRandom
  const artistPlaying = ref(null) // artist id during playRandomArtist

  // --- non-reactive ---
  let audio = null
  let lastGenreTrack = null
  let lastArtistTrack = null

  // --- getters ---
  const visible = computed(() => track.value !== null)
  const progress = computed(() => (duration.value > 0 ? currentTime.value / duration.value : 0))

  // --- helpers ---
  function isCurrent(catalogId) {
    return track.value?.catalog_id === catalogId
  }

  function ensureAudio() {
    if (audio) return audio
    audio = new Audio()
    audio.volume = volume.value
    audio.muted = muted.value
    audio.addEventListener('timeupdate', () => {
      currentTime.value = audio.currentTime
    })
    audio.addEventListener('loadedmetadata', () => {
      duration.value = audio.duration
    })
    audio.addEventListener('ended', () => {
      playing.value = false
    })
    audio.addEventListener('play', () => {
      playing.value = true
    })
    audio.addEventListener('pause', () => {
      playing.value = false
    })
    return audio
  }

  // --- actions ---
  async function play(trackObj) {
    // Same track → toggle play/pause
    if (track.value && track.value.catalog_id === trackObj.catalog_id && audio) {
      toggle()
      return
    }

    // Stop current
    if (audio) {
      audio.pause()
      audio.currentTime = 0
    }

    track.value = {
      id: trackObj.id,
      catalog_id: trackObj.catalog_id,
      title: trackObj.title || '',
      artist: trackObj.artist || '',
      artist_id: trackObj.artist_id || null,
      bpm: trackObj.bpm,
      key: trackObj.key,
    }
    currentTime.value = 0
    duration.value = 30
    genrePlaying.value = null
    artistPlaying.value = null
    loading.value = true

    try {
      const { data } = await api.get(`/api/catalog/${trackObj.catalog_id}/preview-url`)
      const el = ensureAudio()
      el.src = data.preview_url
      await el.play()
      loading.value = false
    } catch (e) {
      console.warn('[audioPlayer] preview failed:', e)
      close()
    }
  }

  function toggle() {
    if (!audio || !track.value) return
    if (audio.paused) {
      audio.play()
    } else {
      audio.pause()
    }
  }

  function seek(t) {
    if (!audio) return
    audio.currentTime = t
    currentTime.value = t
  }

  function setVolume(v) {
    volume.value = v
    if (audio) audio.volume = v
    localStorage.setItem(VOLUME_KEY, v)
  }

  function toggleMute() {
    muted.value = !muted.value
    if (audio) audio.muted = muted.value
  }

  function close() {
    if (audio) {
      audio.pause()
      audio.currentTime = 0
    }
    track.value = null
    playing.value = false
    currentTime.value = 0
    duration.value = 30
    genrePlaying.value = null
    artistPlaying.value = null
    loading.value = false
  }

  async function playRandom(genreName) {
    // If already playing this genre, toggle
    if (genrePlaying.value === genreName && audio && track.value) {
      toggle()
      return
    }

    try {
      const params = { genre: genreName }
      if (lastGenreTrack) params.exclude = lastGenreTrack
      const { data } = await api.get('/api/genres/random-track', { params })
      lastGenreTrack = data.catalog_id

      genrePlaying.value = genreName
      await play({
        id: data.catalog_id,
        catalog_id: data.catalog_id,
        title: data.title || '',
        artist: data.artist || '',
        bpm: data.bpm,
        key: data.key,
      })
      // Restore genrePlaying (play() clears it)
      genrePlaying.value = genreName
    } catch {
      lastGenreTrack = null
    }
  }

  async function playRandomArtist(artistId) {
    if (artistPlaying.value === artistId && audio && track.value) {
      toggle()
      return
    }

    try {
      const params = { artist_id: artistId }
      if (lastArtistTrack) params.exclude = lastArtistTrack
      const { data } = await api.get('/api/artists/random-track', { params })
      lastArtistTrack = data.catalog_id

      artistPlaying.value = artistId
      await play({
        id: data.catalog_id,
        catalog_id: data.catalog_id,
        title: data.title || '',
        artist: data.artist || '',
        bpm: data.bpm,
        key: data.key,
      })
      artistPlaying.value = artistId
    } catch {
      lastArtistTrack = null
    }
  }

  return {
    // state
    track,
    playing,
    currentTime,
    duration,
    volume,
    muted,
    loading,
    genrePlaying,
    artistPlaying,
    // getters
    visible,
    progress,
    // actions
    play,
    toggle,
    seek,
    setVolume,
    toggleMute,
    close,
    playRandom,
    playRandomArtist,
    isCurrent,
  }
})
