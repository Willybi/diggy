import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useToast = defineStore('toast', () => {
  const message = ref('')
  const type = ref('error')
  const visible = ref(false)
  const action = ref(null) // { label, route }
  let timer = null

  function show(msg, t = 'error', duration = 5000, act = null) {
    clearTimeout(timer)
    message.value = msg
    type.value = t
    action.value = act
    visible.value = true
    timer = setTimeout(hide, duration)
  }

  function hide() {
    visible.value = false
    action.value = null
  }

  return { message, type, visible, action, show, hide }
})
