<template>
  <RouterLink v-if="to" :to="to" class="shelf-card" :class="variant">
    <div class="sc-img" :class="variant">
      <img
        v-if="imageSrc"
        :src="imageSrc"
        alt=""
        loading="lazy"
        @error="(e) => (e.target.style.display = 'none')"
      />
      <span v-else class="sc-fb">{{ fallbackLetter }}</span>
      <slot name="overlay" />
    </div>
    <span class="sc-title">{{ title }}</span>
    <span v-if="subtitle" class="sc-sub">{{ subtitle }}</span>
    <slot name="badge" />
  </RouterLink>
  <div v-else class="shelf-card" :class="variant">
    <div class="sc-img" :class="variant">
      <img
        v-if="imageSrc"
        :src="imageSrc"
        alt=""
        loading="lazy"
        @error="(e) => (e.target.style.display = 'none')"
      />
      <span v-else class="sc-fb">{{ fallbackLetter }}</span>
      <slot name="overlay" />
    </div>
    <span class="sc-title">{{ title }}</span>
    <span v-if="subtitle" class="sc-sub">{{ subtitle }}</span>
    <slot name="badge" />
  </div>
</template>

<script setup>
defineProps({
  variant: { type: String, default: 'square' }, // 'square' | 'round'
  imageSrc: { type: String, default: null },
  title: { type: String, required: true },
  subtitle: { type: String, default: null },
  to: { type: String, default: null },
  fallbackLetter: { type: String, default: '?' },
})
</script>

<style scoped>
.shelf-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  width: 120px;
  flex: none;
  scroll-snap-align: start;
  text-decoration: none;
  color: inherit;
  cursor: pointer;
  transition: transform 0.15s;
}
.shelf-card:hover {
  transform: translateY(-2px);
}

/* Image */
.sc-img {
  width: 100px;
  height: 100px;
  border-radius: var(--r-sm);
  background: var(--surface-2);
  border: 1px solid var(--line);
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: none;
  position: relative;
}
.sc-img.round {
  border-radius: 50%;
}
.sc-img img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.sc-fb {
  font: 600 22px/1 var(--font-ui);
  color: var(--ink-3);
}

/* Text */
.sc-title {
  font: 500 12px/1.3 var(--font-ui);
  color: var(--ink);
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  max-width: 100%;
}
.sc-sub {
  font: 400 10.5px/1 var(--font-mono);
  color: var(--ink-3);
  text-align: center;
  white-space: nowrap;
}
</style>
