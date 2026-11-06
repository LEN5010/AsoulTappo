<script setup lang="ts">
// The back of a sealed result. It fills with the parent's --tone-fill, so the colour alone says how
// rare the front is; a band of light keeps crossing it because it is waiting to be pressed.
// Tiers below legendary bring --seal-fill, --seal-mark and --seal-rule instead (tokens.css): the rarity ladder.
import Icon from "../ui/Icon.vue";
</script>

<template>
  <span class="back" aria-hidden="true">
    <i class="rule"></i>
    <Icon name="spark" :size="14" class="star" />
    <i class="mark"></i>
    <b class="word">RESONANCE</b>
    <i class="sheen"></i>
  </span>
</template>

<style scoped>
.back {
  position: absolute;
  inset: 0;
  display: block;
  overflow: hidden;
  border-radius: var(--radius-m);
  background: var(--seal-fill, var(--tone-fill, var(--c-500)));
  box-shadow: inset 0 0 0 3px #fff, inset 0 1px 0 4px rgba(255, 255, 255, 0.35);
  color: var(--seal-mark, #fff);
  container-type: inline-size;
}
.rule {
  position: absolute;
  inset: 9px;
  border-radius: var(--radius-s);
  box-shadow: inset 0 0 0 1px var(--seal-rule, rgba(255, 255, 255, 0.55));
}
.star {
  position: absolute;
  right: 15px;
  top: 15px;
  width: 10cqw;
  height: auto;
  stroke-width: 0;
  fill: currentColor;
}
.mark {
  position: absolute;
  left: 22%;
  right: 22%;
  top: 50%;
  aspect-ratio: 3.172;
  background: currentColor;
  transform: translateY(-50%);
  filter: drop-shadow(0 1px 1px rgba(var(--c-900-rgb), 0.18));
  mask: url("../assets/brand/asoul-logo.svg") center / contain no-repeat;
  -webkit-mask: url("../assets/brand/asoul-logo.svg") center / contain no-repeat;
}
.word {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 15%;
  text-align: center;
  font: 800 max(8px, 8.5cqw)/1 var(--font-latin);
  letter-spacing: 0.16em;
  opacity: 0.85;
}
.sheen {
  position: absolute;
  inset: 0;
  background: linear-gradient(105deg, transparent 38%, rgba(255, 255, 255, 0.5) 50%, transparent 62%) 160% 0 / 260% 100% no-repeat;
  animation: back-sheen 3.2s var(--ease-in-out) infinite;
}
@keyframes back-sheen {
  0%, 55% { background-position: 160% 0; }
  100% { background-position: -60% 0; }
}
@media (prefers-reduced-motion: reduce) {
  .sheen { animation: none; opacity: 0; }
}
</style>
