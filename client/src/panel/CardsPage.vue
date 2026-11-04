<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { poolName, poolSkin } from "../cards";
import { manifest, type ManifestCard } from "../manifest";
import { collection, drawCards, error, tickets } from "../stores/player";
import FilterChips from "../ui/FilterChips.vue";
import { rise } from "../ui/motion";
import SegTabs from "../ui/SegTabs.vue";
import CardAlbum, { type AlbumFilter } from "./CardAlbum.vue";
import CardDetail from "./CardDetail.vue";
import PoolStage from "./PoolStage.vue";
import RevealScene from "./RevealScene.vue";

const VIEWS = [{ id: "pool", label: "抽卡" }, { id: "album", label: "卡册" }] as const;
const FILTERS = [
  { id: "all", label: "全部" },
  { id: "hidden", label: "隐藏款" },
  { id: "owned", label: "已拥有" },
  { id: "missing", label: "未拥有" },
] as const;

const selectedSeries = ref(manifest.series[0]!.id);
const view = ref<"pool" | "album">("pool");
const filter = ref<AlbumFilter>("all");

const series = computed(() => manifest.series.find((s) => s.id === selectedSeries.value) ?? manifest.series[0]!);
const cards = computed(() => manifest.cards.filter((c) => c.series === selectedSeries.value));
const skin = computed(() => poolSkin(selectedSeries.value));
const ownedCount = (c: ManifestCard) => collection.owned[`card:${c.id}`] ?? 0;
const haveCount = computed(() => cards.value.filter(ownedCount).length);

const poolTabs = computed(() =>
  manifest.series.map((p) => ({
    id: p.id,
    label: poolName(p.name),
    count: manifest.cards.filter((c) => c.series === p.id).filter(ownedCount).length,
  })),
);

const root = ref<HTMLElement>();
watch([selectedSeries, view, filter], () => nextTick(() => rise(root.value)));

const detail = ref<ManifestCard | null>(null);
const detailFrom = ref<DOMRect>();
function inspect(c: ManifestCard, from?: DOMRect) {
  detail.value = c;
  detailFrom.value = from;
}

const revealing = ref(false);
const pending = ref(0);

function draw(all: boolean) {
  if (revealing.value || !tickets.value) return;
  pending.value = all ? tickets.value : 1;
  revealing.value = true;
}
async function nextBatch() {
  const result = await drawCards(selectedSeries.value, Math.min(pending.value, 100));
  pending.value = result ? pending.value - result.length : 0;
  return result;
}
</script>

<template>
  <div ref="root" class="cards-page" :style="skin.tokens">
    <SegTabs v-model="selectedSeries" :tabs="poolTabs" :disabled="revealing" label="卡池" />

    <div class="head">
      <FilterChips v-model="view" :options="VIEWS" label="收藏集视图" />
      <FilterChips v-if="view === 'album'" v-model="filter" :options="FILTERS" label="卡册筛选" />
      <span class="have">已集齐 <b>{{ haveCount }}</b> / {{ cards.length }}</span>
    </div>

    <p v-if="error" class="ui-error" role="alert">{{ error }}</p>

    <PoolStage v-if="view === 'pool'" :series="series" :cards="cards" :busy="revealing" @inspect="inspect" @draw="draw" />
    <CardAlbum v-else :cards="cards" :filter="filter" @inspect="inspect" />

    <CardDetail v-if="detail" :card="detail" :from="detailFrom" @close="detail = null" />
    <RevealScene v-if="revealing" kind="card" :load="nextBatch" :remaining="pending" :tint="skin.tokens" @close="revealing = false" />
  </div>
</template>

<style scoped>
.cards-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  padding: 8px 20px 14px 16px;
  gap: 10px;
}
.head {
  flex: none;
  display: flex;
  align-items: center;
  gap: 18px;
}
.have {
  margin-left: auto;
  font-size: var(--fs-label);
  font-weight: 800;
  color: var(--ink-2);
  white-space: nowrap;
}
.have b {
  font: italic 800 var(--fs-section)/1 var(--font-latin);
  color: var(--accent-deep);
}
</style>
