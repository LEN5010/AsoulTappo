<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { prime } from "../audio/sfx";
import { getCard, type ManifestCard, type Rarity } from "../manifest";
import { economy } from "../stores/economy";
import { type Item, RARITY_DESC, RARITY_LABEL } from "../items";
import { bannerLeft, bannerRates, baseRates, heldItems, poolOf, effectiveRates, runningBanners } from "../resonance";
import { formatCount, nextTapText, todayIncome } from "../income";
import { collection, resonate, draws, status, online, error } from "../stores/player";
import { ui } from "../stores/ui";
import Icon from "../ui/Icon.vue";
import Modal from "../ui/Modal.vue";
import PoolStage from "./PoolStage.vue";
import BannerStage from "./BannerStage.vue";
import PoolTabs from "./PoolTabs.vue";
import RevealScene from "./RevealScene.vue";
import CardDetail from "./CardDetail.vue";
import SkinDetail from "./SkinDetail.vue";
import PlateDetail from "./PlateDetail.vue";
import type { Plate } from "../pet/plates";

const pool = computed(() => poolOf(heldItems()));
// The pools: the standing one, and the limited ones the server runs now. A minute's tick opens and closes them and
// counts their time down.
const now = ref(Date.now());
const clock = window.setInterval(() => (now.value = Date.now()), 30_000);
onBeforeUnmount(() => window.clearInterval(clock));
const banners = computed(() => runningBanners(now.value));
const banner = computed(() => banners.value.find((b) => b.id === ui.pool) ?? null);
const pools = computed(() => [
  { id: "", name: "此间共鸣" },
  ...banners.value.map((b) => ({ id: b.id, name: b.name, left: bannerLeft(b, now.value) })),
]);
// A pool that ended while it was on show hands the page back to the standing pool.
watch(banner, (b) => { if (!b && ui.pool && economy.value) ui.pool = ""; });
const featuredLeft = computed(() => !!banner.value?.items.some((id) => !collection.owned[id]));
const standingDone = computed(() => Object.values(pool.value).flat().every((i) => collection.owned[i.id]));
const complete = computed(() => standingDone.value && !featuredLeft.value);
const rates = computed(() => banner.value
  ? bannerRates(banner.value, pool.value, collection.owned)
  : { featured: 0, tiers: effectiveRates(pool.value, collection.owned) });
const base = computed(() => baseRates());
// Decode the draw sounds while the page sits idle, so the first draw is not silent.
onMounted(prime);
const revealing = ref(false);
const pending = ref(0);
/** The pool the draws in progress are from: switching pools waits for them. */
let drawing = "";
/** Size of the last request, offered again from the result board. */
const last = ref(0);
const again = computed(() =>
  (last.value === 1 || last.value === 10) && online.value && !complete.value && draws.value >= last.value ? last.value : 0);
const probabilities = ref(false);
const detail = ref<ManifestCard | null>(null);
const skin = ref<Item | null>(null);
const plate = ref<Plate | null>(null);
const tiers: Rarity[] = RARITY_DESC;
/** Prices and odds from the server; the keys and the table wait for them. */
const res = computed(() => economy.value?.resonance ?? null);
const cost = computed(() => res.value?.cost ?? 0);
const income = computed(() => todayIncome(status.value));
const missingTier = (r: "legendary" | "skin") => pool.value[r].some((i) => !collection.owned[i.id]);
function inspect(item: Item) {
  if (item.kind === "card") detail.value = getCard(item.ref) ?? null;
  else skin.value = item;
}
/** Past this share of the hard pity the legendary gauge glows. */
const PITY_NEAR = 90;
/** The gauges of the bar: a limited pool's own promise first, then the save's two; the bar has room for two. */
const gauges = computed(() => {
  const out: { id: string; label: string; icon: string; count: number; hard: number | null }[] = [];
  const b = banner.value;
  if (b?.pity && featuredLeft.value) {
    out.push({ id: "featured", label: "限定", icon: "spark", count: status.value?.resonance.banners?.[b.id]?.pity ?? 0, hard: b.pity });
  }
  for (const r of ["legendary", "skin"] as const) {
    if (missingTier(r)) {
      out.push({ id: r, label: r === "legendary" ? "大隐藏" : "皮肤", icon: r === "legendary" ? "crown" : "shirt",
        count: status.value?.resonance.pity[r] ?? 0, hard: res.value?.pity[r] ?? null });
    }
  }
  return out.slice(0, 2).map((g) => ({ ...g, percent: g.hard ? Math.min(100, g.count / g.hard * 100) : 0 }));
});
function draw(count: number) {
  if (revealing.value || !online.value || complete.value || draws.value < count) return;
  pending.value = count;
  last.value = count;
  drawing = banner.value?.id ?? "";
  revealing.value = true;
}
function drawAgain() {
  pending.value = last.value;
}
async function nextBatch() {
  const result = await resonate(Math.min(pending.value, 100), drawing || undefined);
  pending.value = result ? Math.max(0, pending.value - result.length) : 0;
  return result;
}
</script>

<template>
  <div class="resonance-page ui-scroll">
    <p v-if="error" class="ui-error" role="alert">{{ error }}</p>
    <Transition name="pool" mode="out-in">
      <BannerStage
        v-if="banner" :key="banner.id" :banner="banner" :busy="revealing"
        :paused="probabilities || !!detail || !!skin || !!plate" @inspect="inspect"
      >
        <template #switch><PoolTabs v-model="ui.pool" :pools="pools" :disabled="revealing" /></template>
      </BannerStage>
      <PoolStage v-else :busy="revealing" :paused="probabilities || !!detail || !!skin || !!plate" @inspect="inspect" @plate="plate = $event">
        <template v-if="banners.length" #switch><PoolTabs v-model="ui.pool" :pools="pools" :disabled="revealing" /></template>
      </PoolStage>
    </Transition>
    <footer class="console">
      <div class="pities">
        <div v-for="g in gauges" :key="g.id" class="pity" :class="[g.id, { near: g.id === 'legendary' && g.percent >= PITY_NEAR }]">
          <span>
            <Icon :name="g.icon" :size="14" />
            {{ g.label }} <b>{{ g.count }}</b><i>/ {{ g.hard ?? '—' }}</i>
          </span>
          <div class="ui-bar"><i :style="{ width: `${g.percent}%` }"></i></div>
        </div>
      </div>
      <div class="supply">
        <p><span>可共鸣</span><b>{{ draws }}</b><span>次</span></p>
        <p v-if="income" class="today" :title="nextTapText(income)">
          <Icon name="shard" :size="13" />今日已获得<b>{{ formatCount(income.today) }}</b>
        </p>
      </div>
      <b v-if="complete" class="done">已集齐</b>
      <div class="keys">
        <button type="button" class="ui-btn large act once" :disabled="revealing || !online || !res || draws < 1 || complete" @click="draw(1)">
          <span class="act-label">共鸣一次</span>
          <small class="act-cost"><Icon name="shard" :size="11" />{{ cost }}</small>
        </button>
        <button type="button" class="ui-btn act ten primary pulse" :disabled="revealing || !online || !res || draws < 10 || complete" @click="draw(10)">
          <span class="act-label">共鸣十次</span>
          <small class="act-cost"><Icon name="shard" :size="11" />{{ cost * 10 }}</small>
        </button>
        <button type="button" class="ui-btn ghost rates-btn" title="概率说明" aria-label="概率说明" @click="probabilities = true">
          <Icon name="info" :size="18" />
        </button>
      </div>
    </footer>
    <Modal v-if="probabilities" :title="banner ? `${banner.name}概率` : '共鸣概率'" heading @close="probabilities = false">
      <table v-if="res" class="rates"><thead><tr><th>档位</th><th>基础概率</th><th>当前概率</th><th>保底</th></tr></thead><tbody>
        <tr v-if="banner" class="featured-row"><td>限定</td><td>{{ banner.rate }}%</td><td>{{ rates.featured }}%</td><td>{{ banner.pity ? `${banner.pity} 次` : '—' }}</td></tr>
        <tr v-for="r in tiers" :key="r"><td>{{ RARITY_LABEL[r] }}</td><td>{{ base[r] }}%</td><td>{{ rates.tiers[r] }}%</td><td>{{ r === 'legendary' || r === 'skin' ? `${res.pity[r]} 次` : '—' }}</td></tr>
        <tr v-if="res.holoChance"><td>镭射款</td><td colspan="2">抽到对应卡片时 {{ +res.holoChance.toFixed(2) }}%</td><td>—</td></tr>
      </tbody></table>
      <p v-else class="rates-wait" role="status">连接服务器后显示</p>
      <p v-if="banner && res" class="rates-note">限定从普通档取概率。卡池结束后，限定内容进入此间共鸣。</p>
    </Modal>
    <CardDetail v-if="detail" :card="detail" preview @close="detail = null" />
    <SkinDetail v-if="skin" :name="skin.ref" @close="skin = null" />
    <PlateDetail v-if="plate" :plate="plate" @close="plate = null" />
    <RevealScene v-if="revealing" :load="nextBatch" :remaining="pending" :again="again" @again="drawAgain" @close="revealing = false" />
  </div>
</template>

<style scoped>
/* The page is the stage; the action bar is a sheet of paper fixed to its bottom edge. */
.resonance-page {
  height: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}
.resonance-page > .ui-error {
  margin: 10px 20px 0 16px;
}
.console {
  position: sticky;
  bottom: 0;
  z-index: 2;
  flex: none;
  margin-top: auto;
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 12px 16px 14px 24px;
  border-radius: 20px 20px 0 0;
  background: var(--surface);
  box-shadow: 0 -10px 28px -18px rgba(var(--shadow-rgb), 0.38), 0 -1px 2px rgba(var(--shadow-rgb), 0.05);
}
.pities {
  flex: 0 1 190px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.pity {
  min-width: 0;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.pity span {
  display: flex;
  align-items: baseline;
  gap: 4px;
  white-space: nowrap;
}
.pity b {
  margin-left: auto;
  font: 800 var(--fs-strong)/1 var(--font-latin);
  color: var(--ink);
}
.pity span i {
  font: 800 var(--fs-label)/1 var(--font-latin);
  font-style: normal;
  color: var(--ink-3);
}
.pity svg {
  align-self: center;
  color: var(--c-700);
}
.pity .ui-bar {
  height: 6px;
  margin-top: 4px;
}
.pity.legendary svg {
  color: var(--gold);
}
/* A limited pool's own promise, in its pearl. */
.pity.featured svg {
  color: var(--pearl-deep);
}
.pity.featured .ui-bar > i {
  background: var(--grad-pearl);
}
/* Switching pools: the stage crosses over, the bar under it stays. */
.pool-enter-active {
  transition: opacity 240ms, transform 320ms var(--ease-out);
}
.pool-leave-active {
  transition: opacity 120ms var(--ease-in);
}
.pool-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.pool-leave-to {
  opacity: 0;
}
.featured-row td:first-child {
  font-weight: 800;
  color: var(--pearl-deep);
}
.rates-note {
  margin: 12px 0 0;
  font-size: var(--fs-label);
  color: var(--ink-3);
}
.pity.legendary .ui-bar > i {
  background: var(--grad-gold);
}
/* Nearly there: the legendary gauge glows and breathes slowly. */
.pity.near .ui-bar {
  overflow: visible;
}
.pity.near .ui-bar > i {
  box-shadow: 0 0 10px 1px rgba(var(--gold-rgb), 0.7);
  animation: near-breathe 2.8s var(--ease-in-out) infinite;
}
@keyframes near-breathe {
  50% {
    box-shadow: 0 0 4px 0 rgba(var(--gold-rgb), 0.35);
  }
}
.supply {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.supply p {
  display: flex;
  align-items: baseline;
  gap: 5px;
  margin: 0;
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--ink-2);
  white-space: nowrap;
}
.supply b {
  font: 800 26px/1 var(--font-latin);
  color: var(--ink);
}
/* Today's tap shards, set like the pity counts beside them. */
.supply .today {
  gap: 4px;
  font-size: var(--fs-label);
}
.supply .today svg {
  align-self: center;
  color: var(--c-700);
}
.supply .today b {
  margin-left: 2px;
  font: 800 var(--fs-strong)/1 var(--font-latin);
}
.done {
  flex: none;
  font-size: var(--fs-strong);
  color: var(--c-700);
}
.keys {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  padding-bottom: 3px;
}
.act {
  flex-direction: column;
  gap: 3px;
}
.once {
  min-width: 112px;
}
/* The space bar of the row: taller and wider than any other key. */
.ten {
  height: 60px;
  min-width: clamp(150px, 24cqw, 230px);
  padding: 0 28px;
  font-size: 18px;
}
.act-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
/* The price under the action, so the cost of a press is never a guess. */
.act-cost {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font: 800 var(--fs-label)/1 var(--font-latin);
  letter-spacing: 0.04em;
  opacity: 0.75;
}
.once:not(:disabled) .act-cost svg {
  color: var(--c-500);
}
.rates-btn {
  width: 36px;
  padding: 0;
}
@container panel (max-width: 820px) {
  .console {
    gap: 12px;
    padding-left: 18px;
  }
  .supply .today {
    display: none;
  }
  .ten {
    min-width: 140px;
    padding: 0 18px;
  }
  .once {
    min-width: 0;
    padding: 0 16px;
  }
}
/* Narrow: the keys keep their row; the supply line gives way first. */
@container panel (max-width: 720px) {
  .console {
    gap: 8px;
    padding: 10px 10px 12px 14px;
  }
  .supply {
    display: none;
  }
  .pities {
    flex: 1 1 auto;
  }
  .keys {
    gap: 6px;
  }
  .ten {
    min-width: 0;
  }
}
@container panel (max-height: 600px) {
  .ten {
    height: 52px;
  }
  .console {
    padding-top: 8px;
    padding-bottom: 10px;
  }
}
.rates {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--fs-body);
}
th, td {
  text-align: left;
  padding: 10px 6px;
  border-bottom: 1px solid var(--c-100);
}
</style>
