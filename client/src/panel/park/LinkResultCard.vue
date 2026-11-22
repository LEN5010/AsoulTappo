<script setup lang="ts">
// A settled tile matching game: how much of the board was cleared, as a ring and a percentage, and the shards it paid,
// counting up. Gold when the board was cleared.
import { computed, onBeforeUnmount, ref, watch } from "vue";
import type { LinkResult } from "../../stores/parkLink";
import Icon from "../../ui/Icon.vue";
import { countTo } from "./countTo";

const props = defineProps<{ result: LinkResult; calm: boolean }>();
defineEmits<{ close: [] }>();

const ROLL_MS = 900;
const fmt = (n: number) => n.toLocaleString("en-US");
const pct = computed(() => (props.result.total ? Math.floor((props.result.cleared * 100) / props.result.total) : 0));
const clear = computed(() => props.result.reason === "clear");

const rolled = ref(0);
let stop = () => {};
watch(() => props.result.id, () => {
  stop();
  const to = props.result.prize;
  if (props.calm || !to) {
    rolled.value = to;
    return;
  }
  rolled.value = 0;
  stop = countTo(rolled, to, ROLL_MS);
}, { immediate: true });
onBeforeUnmount(() => stop());
</script>

<template>
  <div class="link-result" :class="{ clear, calm }" role="status">
    <button type="button" class="ui-btn ghost small close" aria-label="关闭" @click="$emit('close')">
      <Icon name="close" :size="16" />
    </button>
    <div class="dial">
      <svg class="ring" viewBox="0 0 120 120" aria-hidden="true">
        <circle class="ring-track" cx="60" cy="60" r="52" pathLength="100" />
        <circle class="ring-fill" cx="60" cy="60" r="52" pathLength="100" :style="{ '--pct': pct }" />
      </svg>
      <b class="pct">{{ pct }}<small>%</small></b>
    </div>
    <p class="won"><Icon name="shard" :size="24" /><b>+{{ fmt(rolled) }}</b></p>
  </div>
</template>

<style scoped>
.link-result {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  width: 220px;
  padding: 20px 20px 18px;
  box-sizing: border-box;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: 0 0 0 1px rgba(var(--c-900-rgb), 0.05), 0 18px 40px -16px rgba(var(--c-900-rgb), 0.45);
  animation: result-in 420ms var(--ease-spring) both;
}
.link-result.clear {
  background: linear-gradient(180deg, #FFFDF6, #FFF6DD);
  box-shadow: inset 0 0 0 2px var(--gold), 0 18px 40px -16px rgba(var(--gold-rgb), 0.6);
}
.close {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 28px;
  padding: 0;
  color: var(--ink-3);
}
.dial {
  display: grid;
  place-items: center;
}
.dial > * {
  grid-area: 1 / 1;
}
.ring {
  width: 124px;
  height: 124px;
  rotate: -90deg;
}
.ring circle {
  fill: none;
  stroke-width: 10;
}
.ring-track {
  stroke: var(--c-100);
}
.ring-fill {
  stroke: var(--c-500);
  stroke-linecap: round;
  stroke-dasharray: 100;
  stroke-dashoffset: calc(100 - var(--pct));
  animation: ring-fill 900ms var(--ease-out) both;
}
.clear .ring-fill {
  stroke: var(--gold);
}
.pct {
  font: 800 38px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}
.pct small {
  font-size: 19px;
  color: var(--ink-2);
}
.won {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin: 0;
  color: var(--c-600);
}
.won b {
  font: 800 34px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}
.clear .won svg {
  color: var(--gold);
}
@keyframes result-in {
  from { opacity: 0; scale: 0.86; }
}
@keyframes ring-fill {
  from { stroke-dashoffset: 100; }
}
.calm,
.calm .ring-fill {
  animation: none;
}

@container panel (max-height: 560px) {
  .link-result {
    width: 196px;
    padding: 12px 16px 12px;
    gap: 2px;
  }
  .ring {
    width: 100px;
    height: 100px;
  }
  .pct {
    font-size: 30px;
  }
  .won b {
    font-size: 28px;
  }
}
</style>
