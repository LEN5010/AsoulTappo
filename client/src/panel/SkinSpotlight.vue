<script setup lang="ts">
import { computed } from "vue";
import { getCharacter } from "../characters";
import { memberOf } from "../manifest";
import type { Drop } from "../net/api";
import { reducedMotion } from "../stores/theme";
const props = defineProps<{ drop: Drop; settled: boolean }>();
defineEmits<{ done: [] }>();
const name = computed(() => props.drop.item.slice(5));
</script>

<template>
  <div class="skin-spot" :class="{ settled: settled || reducedMotion }">
    <i class="aura" aria-hidden="true"></i>
    <i class="orbit one" aria-hidden="true"></i>
    <i class="orbit two" aria-hidden="true"></i>
    <div class="row">
      <div class="figure" @animationend.self="$emit('done')">
        <img :src="getCharacter(name)?.bg" :alt="name" />
        <i class="floor" aria-hidden="true"></i>
      </div>
      <div class="facts">
        <span class="ui-tag gold">皮肤解锁</span>
        <small>{{ memberOf(name) }}</small>
        <h3>{{ name }}</h3>
        <b v-if="drop.new" class="fresh">NEW</b>
        <b v-else>已拥有 ×{{ drop.count }}</b>
        <p>可在背包中切换</p>
      </div>
    </div>
    <template v-if="!settled && !reducedMotion">
      <i class="curtain left" aria-hidden="true"></i>
      <i class="curtain right" aria-hidden="true"></i>
      <strong class="title">皮肤解锁</strong>
      <i class="flash" aria-hidden="true"></i>
    </template>
  </div>
</template>

<style scoped>
.skin-spot {
  position: absolute;
  inset: 0;
  overflow: hidden;
  background: var(--stage-dark);
  color: var(--on-ink);
}
.aura {
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse at 35% 50%, rgba(var(--gold-rgb), 0.3), transparent 64%);
}
.orbit {
  position: absolute;
  left: 35%;
  top: 50%;
  width: 62cqh;
  height: 62cqh;
  margin: -31cqh;
  border: 1px solid rgba(var(--gold-rgb), 0.48);
  border-radius: 50%;
  transform: rotate(-28deg) scaleX(1.4);
}
.orbit.two {
  transform: rotate(32deg) scaleX(1.65);
  opacity: 0.4;
}
.row {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 24px;
  height: 100%;
  padding: 55px 40px;
  box-sizing: border-box;
}
.figure {
  position: relative;
  flex: 0 1 60%;
  height: 82%;
  animation: materialize 1200ms var(--ease-out) 300ms both;
}
.figure img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  filter: drop-shadow(0 0 24px rgba(var(--gold-rgb), 0.3));
}
.floor {
  position: absolute;
  left: 10%;
  right: 10%;
  bottom: 8%;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--gold), transparent);
  box-shadow: 0 0 28px var(--gold);
}
.facts {
  position: relative;
  flex: 0 1 30%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
  animation: facts 650ms var(--ease-out) 850ms backwards;
}
.facts small {
  margin-top: 8px;
  color: var(--gold-soft);
  font-size: var(--fs-body);
  font-weight: 800;
}
h3 { margin: 0; font: 800 var(--fs-heading)/1.2 var(--font); }
.fresh {
  font: 800 var(--fs-title)/1 var(--font-latin);
  color: var(--gold-soft);
  letter-spacing: 0.08em;
}
p { margin: 0; font-size: var(--fs-body); }
.curtain {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 50%;
  z-index: 2;
  background: var(--gold-soft);
  animation: curtain 950ms var(--ease-in-out) 150ms both;
}
.curtain.left { left: 0; --exit: -110%; }
.curtain.right { right: 0; --exit: 110%; }
.title {
  position: absolute;
  left: 50%;
  top: 50%;
  z-index: 3;
  color: var(--ink);
  font: 800 var(--fs-burst)/1 var(--font);
  white-space: nowrap;
  animation: title 950ms var(--ease-out) 150ms both;
}
.flash {
  position: absolute;
  inset: 0;
  z-index: 4;
  background: var(--surface);
  pointer-events: none;
  animation: flash 1500ms linear both;
}
.settled .figure, .settled .facts { animation: none; }
@keyframes materialize {
  0% { transform: translateY(24px) scale(0.8); filter: brightness(0); }
  45% { filter: brightness(0.2); }
  68% { filter: brightness(1.7); }
  100% { transform: translateY(0) scale(1); filter: brightness(1); }
}
@keyframes facts { from { opacity: 0; transform: translateX(28px); } }
@keyframes curtain {
  0%, 30% { transform: translateX(0); }
  100% { transform: translateX(var(--exit)); }
}
@keyframes title {
  0% { opacity: 0; transform: translate(-50%, -50%) scale(1.5); }
  25%, 55% { opacity: 1; transform: translate(-50%, -50%) scale(1); }
  100% { opacity: 0; transform: translate(-50%, -50%) scale(0.9); }
}
@keyframes flash {
  0%, 48%, 100% { opacity: 0; }
  54% { opacity: 0.75; }
}
</style>
