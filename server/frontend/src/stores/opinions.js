import { defineStore } from 'pinia'
import { reactive } from 'vue'
import api from '../utils/api.js'

export const useOpinionsStore = defineStore('opinions', () => {
  // { artist: { '42': 'liked', ... }, set: { ... }, playlist: { ... }, genre: { ... } }
  const data = reactive({})
  let loaded = false

  async function load() {
    if (loaded) return
    try {
      const { data: resp } = await api.get('/api/opinions/')
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
      await api.patch('/api/opinions/', {
        entity_type: entityType,
        entity_key: key,
        opinion,
      })
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
    Object.keys(data).forEach((k) => delete data[k])
    loaded = false
  }

  return { data, load, get, set, reset }
})
