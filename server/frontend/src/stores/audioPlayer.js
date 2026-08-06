import { defineStore } from 'pinia'
import { ref, shallowRef, computed } from 'vue'
import api from '../utils/api.js'
import { useToast } from './toast.js'

const VOLUME_KEY = 'diggy:volume'

// A 503 on the preview endpoint is transient (Deezer throttled us): retry once
// after a short backoff instead of closing the player on a phantom failure.
const PREVIEW_RETRY_MAX = 1
const PREVIEW_RETRY_BACKOFF_MS = 800
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

// A queue stage can chase "next playable" across pages; bounded so a long tail
// of preview-less rows can't fan out endless loadMore calls.
const NEXT_LOAD_MORE_MAX = 5

export const useAudioPlayer = defineStore('audioPlayer', () => {
  // --- reactive state ---
  const track = ref(null) // { id, catalog_id, title, artist, bpm, key, avis } | null
  const playing = ref(false)
  const currentTime = ref(0)
  const duration = ref(30)
  const volume = ref(parseFloat(localStorage.getItem(VOLUME_KEY)) || 0.8)
  const muted = ref(false)
  const loading = ref(false)

  // Where "next" comes from — set by play()/playRandom*, drives the auto-advance
  // on `ended` and the PlayerBar next button. Shapes:
  //   null                                        → single-shot, stop at the end
  //   { type: 'list', getItems, loadMore?, onAvis? } → the launching listing;
  //     getItems() returns player-shaped tracks in display order, loadMore()
  //     fetches the next page, onAvis(id, avis) syncs the origin row
  //   { type: 'genre', name } / { type: 'artist', id } → random re-roll
  const source = shallowRef(null)

  // --- non-reactive ---
  let audio = null
  let lastGenreTrack = null
  let lastArtistTrack = null

  // --- getters ---
  const visible = computed(() => track.value !== null)
  const progress = computed(() => (duration.value > 0 ? currentTime.value / duration.value : 0))
  const canNext = computed(() => source.value !== null)
  const genrePlaying = computed(() => (source.value?.type === 'genre' ? source.value.name : null))
  const artistPlaying = computed(() => (source.value?.type === 'artist' ? source.value.id : null))

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
      if (source.value) void playNext()
    })
    audio.addEventListener('play', () => {
      playing.value = true
    })
    audio.addEventListener('pause', () => {
      playing.value = false
    })
    return audio
  }

  // Load & start a track, leaving `source` untouched (auto-advance keeps its
  // queue across hops). All entry points funnel here after setting the source.
  async function load(trackObj) {
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
      avis: trackObj.avis ?? null,
    }
    currentTime.value = 0
    duration.value = 30
    loading.value = true

    // Capture the target: a fast track switch mid-retry must not let a stale
    // attempt hijack the (single, shared) audio element.
    const targetId = trackObj.catalog_id
    let lastError = null

    for (let attempt = 0; attempt <= PREVIEW_RETRY_MAX; attempt++) {
      if (attempt > 0) {
        await sleep(PREVIEW_RETRY_BACKOFF_MS)
        if (!isCurrent(targetId)) return // track switched during the backoff
      }
      try {
        const { data } = await api.get(`/api/catalog/${targetId}/preview-url`, {
          suppressErrorToast: true,
        })
        if (!isCurrent(targetId)) return // user switched tracks while loading
        // The endpoint returns the viewer's current avis — authoritative over
        // whatever the launching row knew (some contexts know nothing).
        if ('avis' in data) track.value.avis = data.avis ?? null
        const el = ensureAudio()
        el.src = data.preview_url
        await el.play()
        if (isCurrent(targetId)) loading.value = false
        return
      } catch (e) {
        if (!isCurrent(targetId)) return // stale attempt (track switched) — ignore
        lastError = e
        // Retry only a transient 503 (Deezer quota); anything else is final.
        if (e.response?.status !== 503) break
      }
    }

    // Retries exhausted (or a non-retryable failure): on a transient 503 tell the
    // user it's temporary rather than silently closing on a dead-looking track.
    if (lastError?.response?.status === 503) {
      useToast().show('Preview temporairement indisponible, réessayez.')
    }
    console.warn('[audioPlayer] preview failed:', lastError)
    close()
  }

  // --- actions ---
  async function play(trackObj, src = null) {
    // Same track → toggle play/pause (adopting a newly provided queue so a
    // re-click from a listing rebinds "next" to that listing).
    if (track.value && track.value.catalog_id === trackObj.catalog_id && audio) {
      if (src) source.value = src
      toggle()
      return
    }
    source.value = src
    await load(trackObj)
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
    loading.value = false
    source.value = null
  }

  // Advance to the next track of the current source (auto on `ended`, manual
  // from the PlayerBar). End of queue → simple stop, the bar stays up.
  async function playNext() {
    const src = source.value
    const cur = track.value
    if (!src || !cur) return

    if (src.type === 'list') {
      const nextAfterCurrent = (items) => {
        const idx = items.findIndex((t) => t.catalog_id === cur.catalog_id)
        // The list was refetched under us (filters changed) and the current
        // track is gone: stop rather than jump somewhere unpredictable.
        if (idx === -1) return null
        return items.slice(idx + 1).find((t) => t.has_preview !== false) || null
      }
      let items = src.getItems() || []
      let next = nextAfterCurrent(items)
      for (let i = 0; !next && src.loadMore && i < NEXT_LOAD_MORE_MAX; i++) {
        const before = items.length
        try {
          await src.loadMore()
        } catch {
          break
        }
        items = src.getItems() || []
        if (items.length <= before) break // no progress: genuine end (or error)
        next = nextAfterCurrent(items)
      }
      if (next && source.value === src) await load(next)
      return
    }

    // Random sources: re-roll, excluding the track we just heard.
    await playRandomNext()
  }

  // Avis on the CURRENT track, from the PlayerBar. Optimistic (pattern of the
  // listing rows), synced back to the origin row via source.onAvis, and a
  // dislike skips to the next track immediately — that's the triage gesture.
  async function setAvis(avis) {
    const cur = track.value
    if (!cur) return
    const id = cur.catalog_id
    const prev = cur.avis ?? null
    cur.avis = avis
    source.value?.onAvis?.(id, avis)
    const req = api.patch(`/api/catalog/${id}/avis`, { avis }).catch(() => {
      if (track.value?.catalog_id === id) track.value.avis = prev
      source.value?.onAvis?.(id, prev)
    })
    if (avis === 'disliked' && source.value) void playNext()
    await req
  }

  // Reverse sync: a listing row's LikeDislike changed the avis of the track
  // that happens to be playing — reflect it in the bar.
  function syncAvis(catalogId, avis) {
    if (track.value?.catalog_id === catalogId) track.value.avis = avis
  }

  async function playRandom(genreName) {
    // If already playing this genre, toggle
    if (genrePlaying.value === genreName && audio && track.value) {
      toggle()
      return
    }
    source.value = { type: 'genre', name: genreName }
    await playRandomNext()
  }

  async function playRandomArtist(artistId) {
    if (artistPlaying.value === artistId && audio && track.value) {
      toggle()
      return
    }
    source.value = { type: 'artist', id: artistId }
    await playRandomNext()
  }

  // Roll a track from the current random source (first play and every "next").
  async function playRandomNext() {
    const src = source.value
    try {
      const isGenre = src.type === 'genre'
      const params = isGenre ? { genre: src.name } : { artist_id: src.id }
      const exclude = isGenre ? lastGenreTrack : lastArtistTrack
      if (exclude) params.exclude = exclude
      const url = isGenre ? '/api/genres/random-track' : '/api/artists/random-track'
      const { data } = await api.get(url, { params })
      if (isGenre) lastGenreTrack = data.catalog_id
      else lastArtistTrack = data.catalog_id
      if (source.value !== src) return
      await load({
        id: data.catalog_id,
        catalog_id: data.catalog_id,
        title: data.title || '',
        artist: data.artist || '',
        bpm: data.bpm,
        key: data.key,
      })
    } catch {
      if (src.type === 'genre') lastGenreTrack = null
      else lastArtistTrack = null
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
    source,
    genrePlaying,
    artistPlaying,
    // getters
    visible,
    progress,
    canNext,
    // actions
    play,
    toggle,
    seek,
    setVolume,
    toggleMute,
    close,
    playNext,
    setAvis,
    syncAvis,
    playRandom,
    playRandomArtist,
    isCurrent,
  }
})
