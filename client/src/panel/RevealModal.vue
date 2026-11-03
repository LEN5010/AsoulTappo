<script setup lang="ts">
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
    <h3 class="title">{{ title ?? `开出了 ${drops.length} 个表情` }}</h3>
    <div class="grid" :class="{ one: list.length === 1 }">
      <div
        v-for="x in list" :key="x.i"
        class="sq-slot" :class="`r-${x.d.rarity}`"
        :style="{ animationDelay: `${x.i * 90}ms` }"
      >
        <span class="well">
          <ItemArt :item="x.item!" :size="list.length === 1 ? 132 : 76" />
        </span>
        <b class="label">{{ dropLabel(x.item!, x.d.new) }}</b>
        <span class="name">{{ x.item!.name }}</span>
        <small>{{ RARITY_LABEL[x.d.rarity as Rarity] }}<template v-if="x.d.shards"> · 碎片 +{{ x.d.shards }}</template></small>
      </div>
    </div>
    <p v-if="shardsTotal" class="ui-muted sum">累计转化碎片 +{{ shardsTotal }}</p>
    <div class="actions"><button type="button" class="ui-btn primary" @click="emit('close')">收下</button></div>
  </Modal>
</template>

<style scoped>
.title {
  margin: 0 0 14px;
  text-align: center;
  font-size: 16px;
  font-weight: 800;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(104px, 1fr));
  gap: 12px;
}
.grid.one {
  grid-template-columns: 1fr;
  justify-items: center;
}
.sq-slot {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 7px 7px 9px;
  border-radius: 20px;
  background: var(--tile-frame);
  border: 2px solid var(--tile-border);
  box-shadow: 0 3px 0 var(--tile-lip);
  text-align: center;
  animation: flip 380ms cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
.grid.one .sq-slot {
  width: 176px;
}
.well {
  width: 100%;
  aspect-ratio: 1;
  border-radius: 14px;
  display: grid;
  place-items: center;
  background:
    repeating-linear-gradient(-35deg, rgba(255, 255, 255, 0.22) 0 10px, transparent 10px 22px),
    var(--rar-common-bg);
}
.r-rare .well {
  background:
    repeating-linear-gradient(-35deg, rgba(255, 255, 255, 0.22) 0 10px, transparent 10px 22px),
    var(--rar-rare-bg);
}
.label {
  margin-top: 4px;
  font-size: 11px;
  font-weight: 800;
  color: var(--accent-deep);
}
.name {
  font-size: 12px;
  font-weight: 800;
  max-width: 110px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
small {
  font-size: 10px;
  font-weight: 700;
  color: var(--ink-3);
}
.sum {
  text-align: center;
  font-size: 13px;
  font-weight: 700;
  margin: 14px 0 0;
}
.actions {
  display: flex;
  justify-content: center;
  margin-top: 16px;
}
@keyframes flip {
  from {
    opacity: 0;
    transform: perspective(600px) rotateY(80deg) scale(0.92);
  }
}
</style>
