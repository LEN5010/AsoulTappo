<script setup lang="ts">
import { computed, ref } from "vue";
import { craftCost, type Item } from "../items";
import { collection, craftItem, error, online, shards } from "../stores/player";
import Icon from "./Icon.vue";

const props = defineProps<{ item: Item }>();
const busy = ref(false);
const attempted = ref(false);
const crafted = ref(false);
const owned = computed(() => props.item.starter || !!collection.owned[props.item.id]);
const cost = computed(() => craftCost(props.item));
async function craft() {
  if (busy.value || owned.value || cost.value === null || !online.value || shards.value < cost.value) return;
  busy.value = true;
  attempted.value = true;
  try { crafted.value = await craftItem(props.item.id); }
  finally { busy.value = false; }
}
</script>

<template>
  <div v-if="cost !== null" class="craft-action">
    <template v-if="!owned">
      <div class="price"><span>碎片兑换</span><b><Icon name="shard" :size="16" />{{ cost }}</b></div>
      <button type="button" class="ui-btn primary" :disabled="busy || !online || shards < cost" :aria-busy="busy" @click="craft">
        {{ busy ? '兑换中…' : !online ? '连接后兑换' : shards < cost ? `还差 ${cost - shards} 碎片` : '兑换这件藏品' }}
      </button>
      <small class="balance">持有 <b>{{ shards }}</b> 碎片</small>
    </template>
    <p v-if="crafted" class="success" role="status"><Icon name="check" :size="14" />兑换成功</p>
    <p v-else-if="attempted && error" class="ui-error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped>
.craft-action { width: 100%; margin-top: auto; padding-top: 22px; display: flex; flex-direction: column; gap: 10px; }
.price { display: flex; align-items: center; justify-content: space-between; gap: 16px; font-size: var(--fs-body); color: var(--ink-2); }
.price b { display: flex; align-items: center; gap: 5px; color: var(--c-700); font: 800 26px/1 var(--font-latin); }
.balance { text-align: center; color: var(--ink-3); font-size: var(--fs-label); }
.balance b { font-variant-numeric: tabular-nums; }
.success { display: flex; align-items: center; gap: 6px; margin: 0; color: var(--c-700); font-size: var(--fs-body); font-weight: 700; }
</style>
