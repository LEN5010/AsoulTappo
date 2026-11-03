<script setup lang="ts">
import { computed, onBeforeUnmount, watch } from "vue";
import type { Drop } from "../net/api";
import { dropLabel, getItem, RARITY_LABEL } from "../items";
import type { Rarity } from "../manifest";
import ItemArt from "../ui/ItemArt.vue";

const props = defineProps<{ drop: Drop | null }>();
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
      class="toast" :class="`r-${drop.rarity}`" data-hit data-no-drag @click="emit('done')"
    >
      <span class="tile"><ItemArt :item="item" :size="54" /></span>
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
  left: 50%;
  bottom: calc(100% + 10px);
  z-index: 25;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 14px 6px 6px;
  border: 2.5px solid var(--tile-border);
  cursor: pointer;
  text-align: left;
  border-radius: 22px;
  background: rgba(253, 244, 231, 0.99);
  box-shadow: 0 3px 0 var(--tile-lip), 0 10px 24px rgba(72, 38, 20, 0.2);
  font-family: var(--font);
  color: var(--ink);
  white-space: nowrap;
}
.tile {
  position: relative;
  width: 58px;
  height: 58px;
  overflow: hidden;
  border-radius: 16px;
  display: grid;
  place-items: center;
  background: var(--rar-common-bg);
}
.r-rare .tile { background: var(--rar-rare-bg); }
.r-epic .tile { background: var(--rar-epic-bg); }
.r-legendary .tile { background: var(--rar-legendary-bg); }
.txt { display: flex; flex-direction: column; gap: 1px; }
.txt b { font-size: 12px; font-weight: 800; color: var(--accent-deep); }
.name { font-size: 13px; font-weight: 800; max-width: 160px; overflow: hidden; text-overflow: ellipsis; }
small { font-size: 11px; font-weight: 700; color: var(--ink-3); }
.toast-enter-active { animation: in 240ms cubic-bezier(0.34, 1.56, 0.64, 1); }
.toast-leave-active { transition: opacity 250ms, transform 250ms; }
.toast-leave-to { opacity: 0; transform: translate(-50%, -10px); }
@keyframes in { from { opacity: 0; transform: translate(-50%, 10px) scale(0.92); } }
</style>
