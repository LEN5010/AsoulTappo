<script setup lang="ts">
// Cards flip in one after another after opening boxes or crafting.
import { computed } from "vue";
import type { Drop } from "../net/api";
import { dropLabel, getItem, RARITY_LABEL } from "../items";
import type { Rarity } from "../manifest";
import Modal from "../ui/Modal.vue";
import ItemArt from "../ui/ItemArt.vue";

const props = defineProps<{ drops: Drop[]; title?: string }>();
const emit = defineEmits<{ close: [] }>();
const list = computed(() => props.drops.map((d, i) => ({ d, i, item: getItem(d.item) })).filter((x) => x.item));
const shardsTotal = computed(() => props.drops.reduce((n, d) => n + d.shards, 0));
</script>

<template>
  <Modal :title="title ?? '开箱结果'" wide @close="emit('close')">
    <h3 class="title">{{ title ?? `开出了 ${drops.length} 件` }}</h3>
    <div class="grid" :class="{ one: list.length === 1 }">
      <div v-for="x in list" :key="x.i" class="slot" :class="`r-${x.d.rarity}`" :style="{ animationDelay: `${x.i * 120}ms` }">
        <span class="tile"><ItemArt :item="x.item!" :size="list.length === 1 ? 150 : list.length > 4 ? 64 : 84" /></span>
        <b class="label">{{ dropLabel(x.item!, x.d.new) }}</b>
        <span class="name">{{ x.item!.name }}</span>
        <small>{{ RARITY_LABEL[x.d.rarity as Rarity] }}<template v-if="x.d.shards"> · 碎片 +{{ x.d.shards }}</template></small>
      </div>
    </div>
    <p v-if="shardsTotal" class="ui-muted sum">碎片 +{{ shardsTotal }}</p>
    <div class="actions"><button type="button" class="ui-btn primary" @click="emit('close')">收下</button></div>
  </Modal>
</template>

<style scoped>
.title { margin: 0 0 12px; text-align: center; font-size: 18px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(92px, 1fr)); gap: 10px; }
.grid.one { grid-template-columns: 1fr; justify-items: center; }
.slot { display: flex; flex-direction: column; align-items: center; gap: 3px; text-align: center; animation: flip 520ms cubic-bezier(0.34, 1.4, 0.64, 1) both; }
.tile { display: grid; place-items: center; padding: 8px; border-radius: 20px; background: var(--rar-common-bg); box-shadow: inset 0 0 0 1.5px rgba(255, 255, 255, 0.8); }
.r-rare .tile { background: var(--rar-rare-bg); } .r-epic .tile { background: var(--rar-epic-bg); box-shadow: 0 0 16px rgba(239, 138, 114, 0.45); }
.r-legendary .tile { background: var(--rar-legendary-bg); box-shadow: 0 0 0 2px rgba(233, 178, 58, 0.5), 0 0 22px rgba(233, 178, 58, 0.6); }
.label { font-size: 12px; color: var(--accent); }
.name { font-size: 12px; font-weight: 700; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
small { font-size: 11px; color: var(--ink-3); }
.sum { text-align: center; font-size: 13px; margin: 14px 0 0; }
.actions { display: flex; justify-content: center; margin-top: 16px; }
@keyframes flip { from { opacity: 0; transform: perspective(600px) rotateY(90deg) scale(0.8); } }
</style>
