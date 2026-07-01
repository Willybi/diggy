import { ref, watch } from 'vue'

const STORAGE_KEY = 'diggy-theme'

const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
const saved = localStorage.getItem(STORAGE_KEY)
const isDark = ref(saved ? saved === 'dark' : prefersDark)

function applyTheme(dark) {
  document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
}

// Apply immediately to avoid flash on load
applyTheme(isDark.value)

watch(isDark, (val) => {
  applyTheme(val)
  localStorage.setItem(STORAGE_KEY, val ? 'dark' : 'light')
})

export function useTheme() {
  return {
    isDark,
    toggle: () => {
      isDark.value = !isDark.value
    },
  }
}
