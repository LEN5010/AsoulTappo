<script setup lang="ts">
// The back of a sealed result. It fills with the parent's --tone-fill, so the colour alone says how
// rare the front is; a band of light keeps crossing it because it is waiting to be pressed.
// Tiers below legendary bring --seal-fill, --seal-mark and --seal-rule instead (tokens.css): the rarity ladder.
// On the dealt reveal board, RevealTile sets a uniform coral --seal-fill so every sealed back stays identical.
import Icon from "../ui/Icon.vue";

defineProps<{ calm?: boolean }>();
</script>

<template>
  <span class="back" :class="{ calm }" aria-hidden="true">
    <i class="silk"></i>
    <i class="halftone"></i>
    <i class="rim"></i>
    <i class="rule"></i>
    <Icon name="spark" :size="14" class="star tr" />
    <Icon name="spark" :size="12" class="star bl" />
    <span class="emblem">
      <i class="emblem-ring"></i>
      <i class="emblem-diamond"></i>
    </span>
    <i class="mark"></i>
    <b class="word"><i></i>RESONANCE<i></i></b>
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
  background:
    linear-gradient(162deg, rgba(255, 255, 255, 0.24) 0%, transparent 40%, rgba(var(--c-900-rgb), 0.16) 100%),
    var(--seal-fill, var(--tone-fill, var(--c-500)));
  box-shadow:
    inset 0 0 0 3px #fff,
    inset 0 1px 0 4px rgba(255, 255, 255, 0.42),
    inset 0 -8px 18px -10px rgba(var(--c-900-rgb), 0.28);
  color: var(--seal-mark, #fff);
  container-type: inline-size;
}
/* Fine diagonal silk-screen weave across the card stock. */
.silk {
  position: absolute;
  inset: 3px;
  border-radius: calc(var(--radius-m) - 2px);
  background: repeating-linear-gradient(
    -45deg,
    currentColor 0 1px,
    transparent 1px 6px
  );
  opacity: 0.075;
}
/* Soft halftone dot gradient rising from the lower edge. */
.halftone {
  position: absolute;
  left: 3px;
  right: 3px;
  bottom: 3px;
  height: 48%;
  background: currentColor;
  opacity: 0.14;
  -webkit-mask: url("../assets/patterns/halftone.svg") center bottom / 120% auto no-repeat;
  mask: url("../assets/patterns/halftone.svg") center bottom / 120% auto no-repeat;
}
/* Subtle inner edge light that breathes in sync with the sealed aura. */
.rim {
  position: absolute;
  inset: 3px;
  border-radius: calc(var(--radius-m) - 2px);
  box-shadow: inset 0 0 14px 1px rgba(255, 255, 255, 0.34);
  opacity: 0.35;
  animation: rim-breathe 2.4s var(--ease-in-out) infinite;
}
.rule {
  position: absolute;
  inset: clamp(7px, 6.5cqw, 10px);
  border-radius: var(--radius-s);
  box-shadow: inset 0 0 0 1px var(--seal-rule, rgba(255, 255, 255, 0.6));
}
.rule::after {
  content: "";
  position: absolute;
  inset: 3px;
  border-radius: calc(var(--radius-s) - 2px);
  box-shadow: inset 0 0 0 1px var(--seal-rule, rgba(255, 255, 255, 0.55));
  opacity: 0.42;
}
.star {
  position: absolute;
  stroke-width: 0;
  fill: currentColor;
  opacity: 0.92;
}
.star.tr {
  right: clamp(11px, 10cqw, 15px);
  top: clamp(11px, 10cqw, 15px);
  width: 10cqw;
  height: auto;
}
.star.bl {
  left: clamp(11px, 10cqw, 15px);
  bottom: clamp(11px, 10cqw, 15px);
  width: 7.5cqw;
  height: auto;
  opacity: 0.68;
}
/* Silk-screened centre medallion framing the A-SOUL mark. */
.emblem {
  position: absolute;
  left: 50%;
  top: 48%;
  width: 56cqw;
  aspect-ratio: 1;
  translate: -50% -50%;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(255, 255, 255, 0.2) 0%, transparent 68%);
}
.emblem-ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  box-shadow:
    inset 0 0 0 1px var(--seal-rule, rgba(255, 255, 255, 0.55)),
    0 0 0 3px transparent,
    0 0 0 4px rgba(255, 255, 255, 0.18);
  opacity: 0.72;
}
.emblem-diamond {
  position: absolute;
  inset: 15%;
  border-radius: 3px;
  box-shadow: inset 0 0 0 1px var(--seal-rule, rgba(255, 255, 255, 0.55));
  rotate: 45deg;
  opacity: 0.46;
}
.mark {
  position: absolute;
  left: 21%;
  right: 21%;
  top: 48%;
  aspect-ratio: 3.172;
  background: currentColor;
  transform: translateY(-50%);
  filter: drop-shadow(0 1px 2px rgba(var(--c-900-rgb), 0.24));
  -webkit-mask: url("../assets/brand/asoul-logo.svg") center / contain no-repeat;
  mask: url("../assets/brand/asoul-logo.svg") center / contain no-repeat;
}
.word {
  position: absolute;
  left: 14%;
  right: 14%;
  bottom: 14%;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4cqw;
  font: 800 max(8px, 8cqw)/1 var(--font-latin);
  letter-spacing: 0.16em;
  opacity: 0.9;
}
.word i {
  flex: 1;
  max-width: 10cqw;
  height: 1px;
  background: var(--seal-rule, rgba(255, 255, 255, 0.55));
}
.sheen {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    108deg,
    transparent 33%,
    rgba(255, 255, 255, 0.18) 41%,
    rgba(255, 255, 255, 0.52) 48%,
    rgba(255, 255, 255, 0.14) 54%,
    transparent 62%
  ) 160% 0 / 260% 100% no-repeat;
  animation: back-sheen 3.2s var(--ease-in-out) infinite;
}
.calm .rim,
.calm .sheen {
  animation: none;
}
@keyframes rim-breathe {
  50% { opacity: 0.92; }
}
@keyframes back-sheen {
  0%, 52% { background-position: 160% 0; }
  100% { background-position: -60% 0; }
}
</style>
