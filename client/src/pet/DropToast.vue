<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from "vue";
import type { Drop } from "../net/api";
import { dropLabel, getItem, RARITY_LABEL } from "../items";
import type { Rarity } from "../manifest";
import ItemArt from "../ui/ItemArt.vue";

/** `side` is where the toast sits next to the pet, so it never covers an emote above the head. */
const props = defineProps<{ drop: Drop | null; side: "left" | "right" }>();
const emit = defineEmits<{ done: [] }>();
const item = computed(() => (props.drop ? getItem(props.drop.item) : undefined));
let timer: ReturnType<typeof setTimeout> | undefined;
watch(
  () => props.drop,
  (d) => {
    clearTimeout(timer);
    if (d) timer = setTimeout(() => emit("done"), 3200);
  },
  { immediate: true },
);
onBeforeUnmount(() => clearTimeout(timer));
</script>

<template>
  <Transition name="toast">
    <button
      v-if="drop && item" :key="`${drop.item}-${drop.count}`" type="button"
      class="toast" :class="[`r-${drop.rarity}`, side]" data-hit data-no-drag @click="emit('done')"
    >
      <span class="tile ui-frame"><ItemArt :item="item" :size="54" /></span>
      <span class="txt">
        <b>{{ dropLabel(item, drop.new) }}</b>
        <span class="name">{{ item.name }}</span>
        <small>{{ RARITY_LABEL[drop.rarity as Rarity] ?? drop.rarity }}<template v-if="drop.shards"> · 碎片 +{{ drop.shards }}</template></small>
      </span>
    </button>
  </Transition>
</template>

<style scoped>
.toast {
  position: absolute;
  bottom: 36px;
  z-index: 25;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 16px 6px 6px;
  border: 0;
  cursor: pointer;
  text-align: left;
  background: var(--surface);
  box-shadow: var(--drop-m) var(--accent), 0 10px 24px rgba(var(--ink-rgb), 0.2);
  font-family: var(--font);
  color: var(--ink);
  white-space: nowrap;
}
.toast.left {
  right: calc(100% + 14px);
}
.toast.right {
  left: calc(100% + 14px);
}
.tile {
  width: 58px;
  height: 58px;
  display: grid;
  place-items: center;
  background: var(--rar-common-bg);
}
.r-rare .tile { background: var(--rar-rare-bg); }
.r-epic .tile { background: var(--rar-epic-bg); }
.r-legendary .tile { background: var(--rar-legendary-bg); }
.txt { display: flex; flex-direction: column; gap: 1px; }
.txt b { font-size: var(--fs-label); font-weight: 800; color: var(--accent-deep); }
.name { font: 800 var(--fs-strong)/1.15 var(--font); max-width: 160px; overflow: hidden; text-overflow: ellipsis; }
small { font-size: var(--fs-caption); font-weight: 700; color: var(--ink-3); }
.toast-enter-active { animation: in var(--dur-slow) var(--ease-out); }
.toast-leave-active { transition: opacity var(--dur-base), transform var(--dur-base); }
.toast-leave-to { opacity: 0; transform: translateY(-10px); }
@keyframes in { from { opacity: 0; transform: translate(-16px, 12px); } }
</style>
