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
  display: flex; align-items: center; gap: 10px; padding: 6px 12px 6px 6px; border: 1px solid var(--line-2); cursor: pointer; text-align: left;
  border-radius: var(--r-xl); background: rgba(252, 251, 250, 0.99); box-shadow: 0 10px 24px rgba(43, 35, 38, 0.2); font-family: var(--font); color: var(--ink); white-space: nowrap;
}
.tile { position: relative; width: 60px; height: 60px; overflow: hidden; border-radius: var(--r-l); display: grid; place-items: center; background: var(--rar-common-bg); }
.tile::after { content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 3px; background: var(--rar-common); }
.r-rare .tile { background: var(--rar-rare-bg); } .r-rare .tile::after { background: var(--rar-rare); }
.r-epic .tile { background: var(--rar-epic-bg); } .r-epic .tile::after { background: var(--rar-epic); }
.r-legendary .tile { background: var(--rar-legendary-bg); } .r-legendary .tile::after { background: var(--rar-legendary); }
.txt { display: flex; flex-direction: column; gap: 1px; }
.txt b { font-size: 13px; color: var(--accent); }
.name { font-size: 13px; font-weight: 600; max-width: 160px; overflow: hidden; text-overflow: ellipsis; }
small { font-size: 11px; color: var(--ink-3); }
.toast-enter-active { animation: in 240ms ease-out; }
.toast-leave-active { transition: opacity 250ms, transform 250ms; }
.toast-leave-to { opacity: 0; transform: translate(-50%, -10px); }
@keyframes in { from { opacity: 0; transform: translate(-50%, 10px); } }
</style>
