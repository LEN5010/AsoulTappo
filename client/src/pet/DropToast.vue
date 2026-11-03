<script setup lang="ts">
// Shows what came out of a box, above the pet; one drop at a time.
import { computed, onBeforeUnmount, watch } from "vue";
import type { Drop } from "../net/api";
import { dropLabel, getItem, RARITY_LABEL } from "../items";
import type { Rarity } from "../manifest";
import ItemArt from "../ui/ItemArt.vue";

const props = defineProps<{ drop: Drop | null }>();
const emit = defineEmits<{ done: [] }>();
const item = computed(() => (props.drop ? getItem(props.drop.item) : undefined));
let timer: ReturnType<typeof setTimeout> | undefined;
watch(() => props.drop, (d) => {
  clearTimeout(timer);
  if (d) timer = setTimeout(() => emit("done"), 3200);
}, { immediate: true });
onBeforeUnmount(() => clearTimeout(timer));
</script>

<template>
  <Transition name="toast">
    <button v-if="drop && item" :key="`${drop.item}-${drop.count}`" type="button" class="toast" :class="`r-${drop.rarity}`" data-hit data-no-drag @click="emit('done')">
      <span class="tile"><ItemArt :item="item" :size="58" /></span>
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
  position: absolute; left: 50%; bottom: calc(100% + 8px); z-index: 25; transform: translateX(-50%);
  display: flex; align-items: center; gap: 10px; padding: 8px 14px 8px 8px; border: none; cursor: pointer; text-align: left;
  border-radius: 22px; background: rgba(255, 252, 249, 0.98); box-shadow: 0 10px 28px rgba(50, 20, 30, 0.3); font-family: var(--font); color: var(--ink); white-space: nowrap;
}
.tile { width: 64px; height: 64px; border-radius: 16px; display: grid; place-items: center; background: var(--rar-common-bg); }
.r-rare .tile { background: var(--rar-rare-bg); } .r-epic .tile { background: var(--rar-epic-bg); }
.r-legendary .tile { background: var(--rar-legendary-bg); box-shadow: 0 0 0 2px rgba(233, 178, 58, 0.5), 0 0 18px rgba(233, 178, 58, 0.5); }
.txt { display: flex; flex-direction: column; gap: 1px; }
.txt b { font-size: 14px; color: var(--accent); }
.name { font-size: 13px; font-weight: 700; max-width: 160px; overflow: hidden; text-overflow: ellipsis; }
small { font-size: 11px; color: var(--ink-3); }
.toast-enter-active { animation: in 380ms cubic-bezier(0.34, 1.5, 0.64, 1); }
.toast-leave-active { transition: opacity 250ms, transform 250ms; }
.toast-leave-to { opacity: 0; transform: translate(-50%, -10px); }
@keyframes in { from { opacity: 0; transform: translate(-50%, 16px) scale(0.7); } }
</style>
