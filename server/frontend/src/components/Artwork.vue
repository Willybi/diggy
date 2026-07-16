<template>
  <span class="artwork" :class="`artwork--${size}`">
    <span class="aw-frame">
      <img
        v-if="src && !failed"
        class="aw-img"
        :src="src"
        :alt="alt"
        loading="lazy"
        @error="failed = true"
      />
      <span v-else class="aw-ph"></span>
    </span>
    <span v-if="inLib !== undefined" class="aw-lib" :class="inLib ? 'in' : 'out'">
      <span class="aw-lib-dot"></span>
    </span>
  </span>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  src: { type: String, default: undefined },
  alt: { type: String, default: '' },
  size: { type: String, default: 'row' }, // 'hero' | 'card' | 'row'
  // undefined = no in-lib indicator. `default: undefined` keeps the value
  // undefined when absent (a bare Boolean prop would coerce to false).
  inLib: { type: Boolean, default: undefined },
})

const failed = ref(false)
// A new src is a fresh image: clear the previous load error so it gets a chance.
watch(
  () => props.src,
  () => {
    failed.value = false
  },
)
</script>

<style scoped>
.artwork {
  position: relative;
  display: inline-block;
  flex: none;
  line-height: 0;
}
.artwork--hero {
  width: 216px;
}
.artwork--row {
  width: 36px;
}
.artwork--card {
  display: block;
  width: 100%;
}

.aw-frame {
  display: block;
  width: 100%;
  aspect-ratio: 1;
  overflow: hidden;
  border: 1px solid var(--ct-line);
  background: var(--surface-2);
}
.artwork--hero .aw-frame,
.artwork--card .aw-frame {
  border-radius: var(--r-md);
}
.artwork--row .aw-frame {
  border-radius: var(--r-xs);
}

.aw-img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.aw-ph {
  display: block;
  width: 100%;
  height: 100%;
  background: repeating-linear-gradient(45deg, var(--surface-2) 0 6px, var(--surface-3) 6px 12px);
}

/* In-lib indicator — round chip overflowing the bottom-right corner. */
.aw-lib {
  position: absolute;
  box-sizing: border-box;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--surface);
  border: 1px solid var(--line);
  box-shadow: var(--shadow-sm);
}
.aw-lib-dot {
  box-sizing: border-box;
  border-radius: 50%;
}
.aw-lib.in .aw-lib-dot {
  background: var(--pos);
}
.aw-lib.out .aw-lib-dot {
  border: 1.5px dashed var(--ink-3);
}

.artwork--hero .aw-lib {
  width: 20px;
  height: 20px;
  right: -4px;
  bottom: -4px;
}
.artwork--card .aw-lib {
  width: 16px;
  height: 16px;
  right: -3px;
  bottom: -3px;
}
.artwork--row .aw-lib {
  width: 12px;
  height: 12px;
  right: -2px;
  bottom: -2px;
}
.artwork--hero .aw-lib-dot {
  width: 9px;
  height: 9px;
}
.artwork--card .aw-lib-dot {
  width: 7px;
  height: 7px;
}
.artwork--row .aw-lib-dot {
  width: 5px;
  height: 5px;
}
</style>
