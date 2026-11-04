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
        class="drop" :class="`r-${x.d.rarity}`"
        :style="{ animationDelay: `${x.i * 90}ms` }"
      >
        <span class="well ui-frame">
          <ItemArt :item="x.item!" :size="list.length === 1 ? 124 : 64" />
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
  font: 400 21px/1.1 var(--font-display);
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(92px, 124px));
  justify-content: center;
  gap: 12px 10px;
}
.grid.one {
  grid-template-columns: 1fr;
  justify-items: center;
}
.drop {
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  text-align: center;
  animation: drop-in 460ms var(--ease-out) both;
}
.grid.one .drop {
  width: 176px;
}
.well {
  width: 100%;
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--dots) 0 0 / 9px 9px, var(--rar-common-bg);
}
.r-rare .well {
  background: var(--rar-rare-bg);
}
.r-epic .well {
  background: var(--rar-epic-bg);
}
.r-legendary .well {
  background: var(--rar-legendary-bg);
}
.label {
  margin-top: 5px;
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
@keyframes drop-in {
  from {
    opacity: 0;
    transform: translate(-14px, 20px);
  }
}
</style>
