<!--
  NavCover — a "stretched link" that covers its positioned container, turning a
  whole surface (card, row…) into a real navigable <a>/RouterLink so ctrl+click,
  middle-click and "open in new tab" work.

  Usage convention (referenced by the nav-native chantier lots):
  - the container must be `position: relative`;
  - place <NavCover> as its FIRST child;
  - any interactive control inside (play button, links, avis…) must be
    positioned (`position: relative` is enough) so it paints ABOVE the cover
    and stays clickable.

  Renders nothing when neither `to` nor `href` is set (safe for `:to="maybeNull"`).
-->
<template>
  <a
    v-if="href"
    class="nav-cover"
    :href="href"
    target="_blank"
    rel="noopener"
    :aria-label="label"
  />
  <RouterLink v-else-if="to" class="nav-cover" :to="to" :aria-label="label" />
</template>

<script setup>
defineProps({
  to: { type: [String, Object], default: null }, // internal RouterLink target
  href: { type: String, default: null }, // external link target
  label: { type: String, default: '' }, // aria-label of the link
})
</script>

<style scoped>
.nav-cover {
  position: absolute;
  inset: 0;
  border-radius: inherit;
}
.nav-cover:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}
</style>
