import { ref, onMounted, onUnmounted, nextTick } from 'vue'

export function useInfiniteScroll(fetchMore, options = {}) {
  const sentinel = ref(null)
  let observer = null

  const observerOptions = {
    rootMargin: '0px 0px 360px 0px',
    ...options,
  }

  onMounted(() => {
    nextTick(() => {
      if (!sentinel.value) return
      observer = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting) fetchMore()
      }, observerOptions)
      observer.observe(sentinel.value)
    })
  })

  onUnmounted(() => {
    observer?.disconnect()
  })

  return { sentinel }
}
