<script setup lang="ts">
// The paper strip under the pet: the tap count, the draw key while draws are available, the quick
// emote key and the panel key. Each thousand taps the number pops and throws a few sparks.
import { ref, watch } from "vue";
import { reducedMotion } from "../stores/theme";
import Icon from "../ui/Icon.vue";

// `grip` draws the handle on the strip's lower edge: "fold" tucks a pinned strip away until the pet is clicked,
// "pin" keeps a strip that a click brought out.
const props = defineProps<{
  count: number; view: "today" | "total"; width: number; quickOpen: boolean; draws: number; grip?: "fold" | "pin";
}>();
defineEmits<{ toggleView: []; quick: []; menu: []; resonance: []; grip: [] }>();
const fmt = (n: number) => n.toLocaleString("en-US");

const MILESTONE = 1000;
/** A larger jump is a reload or a sync, not taps crossing the line. */
const MAX_STEP = 200;
const SPARKS = 6;
const burst = ref(0);
watch(
  () => [props.count, props.view] as const,
  ([to, view], [from, was]) => {
    if (view !== was || reducedMotion.value) return;
    const step = to - from;
    if (step <= 0 || step > MAX_STEP || Math.floor(to / MILESTONE) <= Math.floor(from / MILESTONE)) return;
    burst.value++;
  },
);
</script>

<template>
  <div class="bar" :style="{ width: `${width}px` }">
    <button
      type="button" class="count"
      :title="view === 'today' ? '今日敲击，点击切换累计' : '累计敲击，点击切换今日'"
      @click="$emit('toggleView')"
    >
      <span class="figure">
        <b :key="burst" :class="{ pop: burst > 0 }">{{ fmt(count) }}</b>
        <span v-if="burst" :key="burst" class="burst" aria-hidden="true">
          <i v-for="n in SPARKS" :key="n" :style="{ '--a': `${(n - 1) * (360 / SPARKS) + 30}deg` }"></i>
        </span>
      </span>
      <small>{{ view === "today" ? "今日" : "累计" }}</small>
    </button>
    <button
      v-if="draws > 0" type="button" class="draw ui-btn small primary"
      :title="`共鸣 ${draws}`" :aria-label="`共鸣，可共鸣 ${draws} 次`" @click="$emit('resonance')"
    >
      <Icon class="draw-icon" name="card-spark" :size="15" />
      <span class="draw-word">共鸣</span>
      <b>{{ draws }}</b>
    </button>
    <slot />
    <button
      type="button" class="key spark ui-btn small" :aria-expanded="quickOpen"
      title="发表情" aria-label="发表情" @click="$emit('quick')"
    >
      <svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 2.5l2.5 7L21.5 12l-7 2.5L12 21.5l-2.5-7L2.5 12l7-2.5z" fill="currentColor" />
      </svg>
    </button>
    <button type="button" class="key ui-btn small" title="打开面板" aria-label="打开面板" @click="$emit('menu')">
      <Icon name="menu" :size="15" />
    </button>
    <button
      v-if="grip" type="button" class="grip" :class="grip" :title="grip === 'pin' ? '固定' : '收起'"
      :aria-label="grip === 'pin' ? '固定' : '收起'" @click="$emit('grip')"
    ></button>
  </div>
</template>

<style scoped>
/* Floats over any wallpaper, so its shadow is crisper than paper on the page. */
.bar {
  position: relative;
  container: bar / inline-size;
  --gap: 6px;
  display: flex;
  align-items: center;
  gap: var(--gap);
  height: 40px;
  margin-top: -4px;
  padding: 0 var(--gap);
  box-sizing: border-box;
  border-radius: 12px;
  background: var(--surface);
  box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.12), 0 6px 16px -6px rgba(var(--shadow-rgb), 0.35);
  font-family: var(--font);
  color: var(--ink);
}
/* A drawer handle on the lower edge: a short line, with a larger area to press. */
.grip {
  position: absolute;
  left: 50%;
  bottom: -5px;
  width: 44px;
  height: 14px;
  padding: 0;
  translate: -50% 0;
  border: none;
  background: transparent;
  cursor: pointer;
}
.grip::before {
  content: "";
  position: absolute;
  left: 50%;
  bottom: 6px;
  width: 22px;
  height: 3px;
  translate: -50% 0;
  border-radius: 2px;
  background: var(--c-200);
  transition: background var(--dur-fast), width var(--dur-fast) var(--ease-out);
}
.grip.pin::before { background: var(--c-400); }
.grip:hover::before { width: 30px; background: var(--c-500); }
/* A quiet key: its face comes up under the pointer. */
/* The count face and the keys share one 28px face height; the bottom margin makes room for the
 * keys' 3px lip, so the group (lip included) sits centred and every top and bottom edge lines up. */
.count,
.bar > .ui-btn {
  height: 28px;
  margin-bottom: 3px;
}
.bar > .ui-btn {
  flex: none;
}
.count {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 5px;
  padding: 0 8px 0 10px;
  border: none;
  border-radius: var(--radius-key-s);
  background: transparent;
  cursor: pointer;
  font: inherit;
  color: inherit;
  line-height: 28px;
  transition: background var(--dur-fast);
}
.count:hover {
  background: var(--c-100);
}
.count:active {
  background: var(--c-200);
}
.count:focus-visible {
  outline-offset: -2px;
}
/* The number clips itself on a short strip; the sparks sit beside it so they are never clipped. */
.figure {
  position: relative;
  min-width: 0;
  display: flex;
}
.count b {
  display: block;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font: 800 22px/28px var(--font-latin);
  color: var(--ink);
  white-space: nowrap;
}
.count small {
  flex: none;
  font-size: var(--fs-caption);
  font-weight: 800;
  color: var(--c-700);
}
.count b.pop {
  animation: count-pop 420ms var(--ease-pop);
}
@keyframes count-pop {
  30% {
    transform: scale(1.22);
    color: var(--c-700);
  }
}
/* Sparks thrown outward from the number's middle, once per thousand. */
.burst {
  position: absolute;
  left: 50%;
  top: 50%;
  z-index: 2;
  width: 0;
  height: 0;
  pointer-events: none;
}
.burst i {
  position: absolute;
  left: -3.5px;
  top: -3.5px;
  width: 7px;
  height: 7px;
  background: var(--c-500);
  clip-path: polygon(50% 0, 62% 38%, 100% 50%, 62% 62%, 50% 100%, 38% 62%, 0 50%, 38% 38%);
  opacity: 0;
  animation: spark-fly 600ms var(--ease-out) both;
}
@keyframes spark-fly {
  0% {
    opacity: 1;
    transform: rotate(var(--a)) translateY(0) scale(0.4);
  }
  60% {
    opacity: 1;
  }
  100% {
    opacity: 0;
    transform: rotate(var(--a)) translateY(-26px) scale(1);
  }
}
.draw {
  flex: none;
  gap: 4px;
  padding: 0 9px;
}
.draw b {
  font: 800 var(--fs-strong)/1 var(--font-latin);
}
.draw-icon {
  display: none;
}
/* Short strip: the key folds to its icon and the number, so the other keys keep their place. */
@container bar (max-width: 300px) {
  .draw {
    padding: 0 7px;
  }
  .draw-icon {
    display: block;
  }
  .draw-word {
    display: none;
  }
}
.key {
  flex: none;
  width: 28px;
  padding: 0;
}
.key svg,
.key :deep(.icon) {
  display: block;
  flex: none;
}
.spark svg {
  transition: transform var(--dur-slow) var(--ease-out);
}
.spark[aria-expanded="true"] svg {
  transform: rotate(45deg);
}
</style>
