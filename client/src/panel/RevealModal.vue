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
.title { margin: 0 0 14px; text-align: center; font-size: 16px; font-weight: 700; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(92px, 1fr)); gap: 10px; }
.grid.one { grid-template-columns: 1fr; justify-items: center; }
.slot { display: flex; flex-direction: column; align-items: center; gap: 3px; text-align: center; animation: flip 420ms ease-out both; }
.tile { position: relative; display: grid; place-items: center; padding: 8px; overflow: hidden; border-radius: var(--r-l); background: var(--rar-common-bg); box-shadow: inset 0 0 0 1px var(--line); }
.tile::after { content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 3px; background: var(--rar-common); }
.r-rare .tile { background: var(--rar-rare-bg); } .r-rare .tile::after { background: var(--rar-rare); }
.r-epic .tile { background: var(--rar-epic-bg); } .r-epic .tile::after { background: var(--rar-epic); }
.r-legendary .tile { background: var(--rar-legendary-bg); box-shadow: inset 0 0 0 1px rgba(210, 154, 28, 0.5); } .r-legendary .tile::after { background: var(--rar-legendary); }
.label { font-size: 12px; color: var(--accent); }
.name { font-size: 12px; font-weight: 600; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
small { font-size: 11px; color: var(--ink-3); }
.sum { text-align: center; font-size: 13px; margin: 14px 0 0; }
.actions { display: flex; justify-content: center; margin-top: 16px; }
@keyframes flip { from { opacity: 0; transform: perspective(600px) rotateY(80deg); } }
</style>
