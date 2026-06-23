import { defineStore } from 'pinia'
import { reactive } from 'vue'
import axios from 'axios'
import { useAuthStore } from './auth.js'

export const useOpinionsStore = defineStore('opinions', () => {
  // { artist: { '42': 'liked', ... }, set: { ... }, playlist: { ... }, genre: { ... } }
  const data = reactive({})
  let loaded = false

  function _headers() {
    const auth = useAuthStore()
    return auth.token ? { Authorization: `Bearer ${auth.token}` } : {}
  }

  async function load() {
    if (loaded) return
    try {
      const { data: resp } = await axios.get('/api/opinions/', { headers: _headers() })
      Object.assign(data, resp)
      loaded = true
    } catch {}
  }

  function get(entityType, entityKey) {
    return data[entityType]?.[String(entityKey)] || null
  }

  async function set(entityType, entityKey, opinion) {
    const key = String(entityKey)
    // Optimistic update
    if (!data[entityType]) data[entityType] = {}
    const prev = data[entityType][key]
    if (opinion) {
      data[entityType][key] = opinion
    } else {
      delete data[entityType][key]
    }
    try {
      await axios.patch('/api/opinions/', {
        entity_type: entityType,
        entity_key: key,
        opinion,
      }, { headers: _headers() })
    } catch {
      // Rollback
      if (prev) {
        data[entityType][key] = prev
      } else {
        delete data[entityType][key]
      }
    }
  }

  function reset() {
    Object.keys(data).forEach(k => delete data[k])
    loaded = false
  }

  return { data, load, get, set, reset }
})
