<template>
  <section class="page-hero">
    <div class="hero-visual" :class="`hero-visual--${variant}`">
      <img v-if="imageSrc" :src="imageSrc" :alt="title" />
      <span v-else class="hero-fallback">{{ fallbackLetter }}</span>
    </div>
    <div class="hero-body">
      <h1 class="hero-title">{{ title }}</h1>
      <div v-if="$slots.subtitle" class="hero-sub">
        <slot name="subtitle" />
      </div>
      <p v-else-if="subtitle" class="hero-sub">{{ subtitle }}</p>
      <div v-if="$slots.badges" class="hero-badges">
        <slot name="badges" />
      </div>
      <div v-if="$slots.actions" class="hero-actions">
        <slot name="actions" />
      </div>
    </div>
  </section>
</template>

<script setup>
defineProps({
  variant: { type: String, default: 'square' }, // square | round | wide
  imageSrc: { type: String, default: null },
  title: { type: String, required: true },
  subtitle: { type: String, default: null },
  fallbackLetter: { type: String, default: '?' },
})
</script>

<style scoped>
.page-hero {
  display: flex;
  gap: var(--space-6);
  align-items: flex-start;
  padding: var(--pad) 0;
}

/* Visual */
.hero-visual {
  flex: none;
  overflow: hidden;
  background: var(--surface-2);
  display: grid;
  place-items: center;
}
.hero-visual img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.hero-fallback {
  font: 700 var(--fs-fallback)/1 var(--font-ui);
  color: var(--ink-3);
  text-transform: uppercase;
}

.hero-visual--square {
  width: 160px;
  height: 160px;
  border-radius: var(--r-md);
  border: 1px solid var(--line);
}
.hero-visual--round {
  width: 160px;
  height: 160px;
  border-radius: 50%;
  border: 1px solid var(--line);
}
.hero-visual--wide {
  width: 280px;
  height: 158px;
  border-radius: var(--r-lg);
  border: 1px solid var(--line);
}

/* Body */
.hero-body {
  flex: 1;
  min-width: 0;
  padding-top: var(--space-1);
}
.hero-title {
  font: 600 clamp(20px, 2.2vw, 34px)/1.2 var(--font-ui);
  letter-spacing: -0.02em;
  color: var(--ink);
  margin: 0;
  overflow-wrap: break-word;
}
.hero-sub {
  font: 400 var(--fs-base)/1.3 var(--font-ui);
  color: var(--ink-2);
  margin: var(--space-15) 0 0;
}
.hero-badges {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-3);
}
.hero-actions {
  display: flex;
  gap: var(--space-2);
  margin-top: var(--space-4);
}
</style>
