<script setup lang="ts">
// The reverse of a card, sealed until the draw scene turns it over.
</script>

<template>
  <span class="back" aria-hidden="true">
    <i class="stripe"></i>
    <i class="mark"></i>
  </span>
</template>

<style scoped>
.back {
  position: absolute;
  inset: 0;
  display: block;
  overflow: hidden;
  background: var(--accent-deep);
}
.stripe {
  position: absolute;
  top: -8%;
  bottom: -8%;
  left: 44%;
  width: 30%;
  background: rgba(255, 255, 255, 0.14);
  transform: skewX(var(--skew));
}
.mark {
  position: absolute;
  left: 16%;
  right: 16%;
  top: 50%;
  aspect-ratio: 3.172;
  background: var(--surface);
  transform: translateY(-50%);
  mask: url("../assets/brand/asoul-logo.svg") center / contain no-repeat;
  -webkit-mask: url("../assets/brand/asoul-logo.svg") center / contain no-repeat;
}
</style>
