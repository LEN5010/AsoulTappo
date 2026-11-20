<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { usePageActive } from "../composables/usePageActive";
import { prime } from "../audio/sfx";
import { getCard, type ManifestCard, type Rarity } from "../manifest";
import { economy } from "../stores/economy";
import { type Item, RARITY_DESC, RARITY_LABEL } from "../items";
import { bannerBaseRates, bannerLeft, bannerRates, baseRates, featuredItems, heldItems, pityOpen, poolDone, poolOf, effectiveRates, runningBanners } from "../resonance";
import { formatCount, nextTapText, todayIncome } from "../income";
import { collection, resonate, draws, shards, status, online, error, loadEconomy } from "../stores/player";
import { reducedMotion } from "../stores/theme";
import { ui } from "../stores/ui";
import Icon from "../ui/Icon.vue";
import Modal from "../ui/Modal.vue";
import PoolStage from "./PoolStage.vue";
import BannerStage from "./BannerStage.vue";
import PoolTabs from "./PoolTabs.vue";
import RevealScene from "./RevealScene.vue";
import CardDetail from "./CardDetail.vue";
import SkinDetail from "./SkinDetail.vue";
import HistoryDialog from "./HistoryDialog.vue";
import PlateDetail from "./PlateDetail.vue";
import type { Plate } from "../pet/plates";

const pool = computed(() => poolOf(heldItems()));
// The pools: the standing one, and the limited ones the server runs now. A minute's tick opens and closes them and
// counts their time down.
const now = ref(Date.now());
const clock = window.setInterval(() => (now.value = Date.now()), 30_000);
onBeforeUnmount(() => window.clearInterval(clock));
const pageActive = usePageActive();
watch(pageActive, (active) => { if (active) now.value = Date.now(); });
const expired = computed(() => economy.value?.resonance.banners
  ?.filter((b) => b.end * 1000 <= now.value).map((b) => b.id).join(",") ?? "");
watch(() => pageActive.value && online.value && expired.value, (ids) => {
  if (ids) void loadEconomy();
}, { immediate: true });
const banners = computed(() => runningBanners(now.value));
const banner = computed(() => banners.value.find((b) => b.id === ui.pool) ?? null);
const pools = computed(() => [
  { id: "", name: "此间共鸣" },
  ...banners.value.map((b) => ({ id: b.id, name: b.name, left: bannerLeft(b, now.value) })),
]);
// A pool that ended while it was on show hands the page back to the standing pool.
watch(banner, (b) => { if (!b && ui.pool && economy.value) ui.pool = ""; });
const featuredLeft = computed(() => !!banner.value?.items.some((id) => !collection.owned[id]));
/** The shared tiers whose next draw in the pool on show gives a featured item. */
const guaranteed = computed(() => (banner.value && status.value?.resonance.banners?.[banner.value.id]?.guaranteed) || []);
const rates = computed(() => banner.value
  ? bannerRates(banner.value, pool.value, collection.owned, guaranteed.value)
  : { featured: 0, tiers: effectiveRates(pool.value, collection.owned), shared: [] });
const base = computed(() => (banner.value ? bannerBaseRates(banner.value) : baseRates()));
// Everything this pool's odds can reach is owned, the holo versions the server deals included.
const standingDone = computed(() => poolDone(pool.value, collection.owned, base.value));
const complete = computed(() => !!economy.value && standingDone.value && !featuredLeft.value);
/** What a limited pool's featured items are called: skins when they all are. */
const featuredWord = computed(() =>
  (banner.value && featuredItems(banner.value).every((i) => i.kind === "character") ? "本期皮肤" : "本期限定"));
// Decode the draw sounds while the page sits idle, so the first draw is not silent.
onMounted(prime);
const revealing = ref(false);
const pending = ref(0);
/** The pool the draws in progress are from: switching pools waits for them. */
let drawing = "";
/** Size of the last request, offered again from the result board. */
const last = ref(0);
const again = computed(() =>
  (last.value === 1 || last.value === 10) && online.value && !complete.value && draws.value >= last.value &&
  (!drawing || banners.value.some((b) => b.id === drawing)) ? last.value : 0);
const probabilities = ref(false);
const history = ref(false);
const detail = ref<ManifestCard | null>(null);
const skin = ref<Item | null>(null);
const plate = ref<Plate | null>(null);
/** The table's rows: the tiers this pool gives odds. */
const tiers = computed<Rarity[]>(() => RARITY_DESC.filter((r) => base.value[r] > 0));
/** Prices and odds from the server; the keys and the table wait for them. */
const res = computed(() => economy.value?.resonance ?? null);
const cost = computed(() => res.value?.cost ?? 0);
const income = computed(() => todayIncome(status.value));
const canOnce = computed(() => !revealing.value && online.value && !!res.value && !complete.value && draws.value >= 1);
const canTen = computed(() => !revealing.value && online.value && !!res.value && !complete.value && draws.value >= 10);
const onceShort = computed(() => (res.value && cost.value > shards.value ? cost.value - shards.value : 0));
const tenShort = computed(() => (res.value && cost.value * 10 > shards.value ? cost.value * 10 - shards.value : 0));
/** A gauge shows while its pity can still bring something new from the pool on show (featured items included). */
const missingTier = (r: "legendary" | "skin") => pityOpen(r, pool.value, collection.owned, banner.value);
function inspect(item: Item) {
  if (item.kind === "card") detail.value = getCard(item.ref) ?? null;
  else skin.value = item;
}
/** Past this share of the hard pity the gauge glows with anticipation. */
const PITY_NEAR = 90;
/** The gauges of the bar: a limited pool's own promise first, then the save's two; the bar has room for two. */
const gauges = computed(() => {
  const out: { id: string; label: string; icon: string; count: number; hard: number | null }[] = [];
  const b = banner.value;
  if (b?.pity && featuredLeft.value) {
    out.push({ id: "featured", label: featuredWord.value, icon: "spark", count: status.value?.resonance.banners?.[b.id]?.pity ?? 0, hard: b.pity });
  }
  for (const r of ["legendary", "skin"] as const) {
    if (missingTier(r)) {
      // The pity's skin is a featured one for certain: the gauge says so in its label.
      const sure = r === "skin" && guaranteed.value.includes(r);
      out.push({ id: r, label: r === "legendary" ? "大隐藏" : sure ? featuredWord.value : "皮肤",
        icon: r === "legendary" ? "crown" : sure ? "spark" : "shirt",
        count: status.value?.resonance.pity[r] ?? 0, hard: res.value?.pity[r] ?? null });
    }
  }
  return out.slice(0, 2).map((g) => ({
    ...g,
    percent: g.hard ? Math.min(100, g.count / g.hard * 100) : 0,
    left: g.hard ? Math.max(0, g.hard - g.count) : null,
  }));
});
/** Post-reveal keyboard guard so holding or mashing Space/Enter to close RevealScene never misfires a new draw. */
let revealClosedAt = 0;
function guardDrawKey(e: KeyboardEvent) {
  if (e.repeat || ((e.key === " " || e.key === "Enter") && performance.now() - revealClosedAt < 450)) {
    e.preventDefault();
  }
}
function guardDrawKeyUp(e: KeyboardEvent) {
  if (e.key === " " && performance.now() - revealClosedAt < 450) e.preventDefault();
}
function onRevealClose() {
  revealClosedAt = performance.now();
  revealing.value = false;
}
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
  <div class="resonance-page ui-scroll" :class="{ calm: reducedMotion }">
    <p v-if="error" class="ui-error" role="alert">{{ error }}</p>
    <Transition name="pool" mode="out-in" :css="!reducedMotion">
      <BannerStage
        v-if="banner" :key="banner.id" :banner="banner" :busy="revealing"
        :paused="probabilities || history || !!detail || !!skin || !!plate" @inspect="inspect" @plate="plate = $event"
      >
        <template #switch><PoolTabs v-model="ui.pool" :pools="pools" :disabled="revealing" /></template>
      </BannerStage>
      <PoolStage v-else :busy="revealing" :paused="probabilities || history || !!detail || !!skin || !!plate" @inspect="inspect" @plate="plate = $event">
        <template v-if="banners.length" #switch><PoolTabs v-model="ui.pool" :pools="pools" :disabled="revealing" /></template>
      </PoolStage>
    </Transition>
    <footer class="console" :class="{ 'state-empty': !complete && draws < 1, 'state-once': !complete && draws >= 1 && draws < 10, 'state-ten': !complete && draws >= 10 }">
      <div class="pities">
        <div
          v-for="g in gauges" :key="g.id" class="pity" :class="[g.id, { near: g.percent >= PITY_NEAR }]"
          :title="g.left !== null ? `剩余 ${g.left} 次保底` : undefined"
        >
          <span>
            <Icon :name="g.icon" :size="14" />
            {{ g.label }}
            <em v-if="g.percent >= PITY_NEAR" class="near-tag">即将</em>
            <b>{{ g.count }}</b><i>/ {{ g.hard ?? '—' }}</i>
          </span>
          <div class="ui-bar"><i :style="{ width: `${g.percent}%` }"></i></div>
        </div>
      </div>
      <div class="supply">
        <p class="draws-line">
          <span>可共鸣</span>
          <b :class="{ empty: draws < 1, abundant: draws >= 10 }">{{ draws }}</b>
          <span>次</span>
          <em v-if="!complete && res && draws < 1" class="short-pill">碎片不足</em>
        </p>
        <p v-if="!complete && res && draws < 1 && onceShort > 0" class="today short" :title="income ? nextTapText(income) : undefined">
          <Icon name="shard" :size="13" />还差<b>{{ formatCount(onceShort) }}</b>碎片
        </p>
        <p v-else-if="income" class="today" :title="nextTapText(income)">
          <Icon name="shard" :size="13" />今日已获得<b>{{ formatCount(income.today) }}</b>
          <i v-if="!complete && res && draws >= 1 && draws < 10 && tenShort > 0" class="ten-gap">· 差 {{ formatCount(tenShort) }} 满十次</i>
        </p>
      </div>
      <b v-if="complete" class="done">已集齐</b>
      <div class="keys">
        <button
          type="button" class="ui-btn large act once"
          :class="{ primary: canOnce && !canTen, pulse: canOnce && !canTen && !reducedMotion }"
          :disabled="!canOnce"
          @keydown="guardDrawKey" @keyup="guardDrawKeyUp" @click="draw(1)"
        >
          <span class="act-label">共鸣一次</span>
          <small class="act-cost"><Icon name="shard" :size="11" />{{ cost }}</small>
        </button>
        <button
          type="button" class="ui-btn act ten primary" :class="{ pulse: canTen && !reducedMotion }"
          :disabled="!canTen"
          @keydown="guardDrawKey" @keyup="guardDrawKeyUp" @click="draw(10)"
        >
          <span class="act-label">共鸣十次</span>
          <small class="act-cost"><Icon name="shard" :size="11" />{{ cost * 10 }}</small>
        </button>
        <span class="side-keys">
          <button type="button" class="ui-btn ghost small side-key" title="概率说明" aria-label="概率说明" @click="probabilities = true">
            <Icon name="info" :size="16" />
          </button>
          <button type="button" class="ui-btn ghost small side-key" title="共鸣记录" aria-label="共鸣记录" :disabled="!online" @click="history = true">
            <Icon name="clock" :size="16" />
          </button>
        </span>
      </div>
    </footer>
    <Modal v-if="probabilities" :title="banner ? `${banner.name}概率` : '共鸣概率'" heading @close="probabilities = false">
      <table v-if="res" class="rates"><thead><tr><th>档位</th><th>基础概率</th><th>当前概率</th><th>保底</th></tr></thead><tbody>
        <tr v-if="banner?.rate" class="featured-row" :class="{ zero: rates.featured === 0 }">
          <td><span class="tier-cell"><i class="swatch" aria-hidden="true"></i>{{ featuredWord }}</span></td>
          <td class="num">{{ banner.rate }}%</td>
          <td class="num cur">{{ rates.featured }}%</td>
          <td class="pity-col"><span v-if="banner.pity" class="pity-pill">{{ banner.pity }} 次</span><template v-else>—</template></td>
        </tr>
        <tr v-for="r in tiers" :key="r" :class="[r, { zero: rates.tiers[r] === 0 && base[r] > 0, boosted: rates.tiers[r] > base[r] }]">
          <td><span class="tier-cell"><i class="swatch" aria-hidden="true"></i>{{ RARITY_LABEL[r] }}</span></td>
          <td class="num">{{ base[r] }}%</td>
          <td class="num cur">{{ rates.tiers[r] }}%</td>
          <td class="pity-col"><span v-if="r === 'legendary' || r === 'skin'" class="pity-pill">{{ res.pity[r] }} 次</span><template v-else>—</template></td>
        </tr>
        <tr v-for="{ rarity, rate } in rates.shared" :key="`shared-${rarity}`" class="featured-row">
          <td><span class="tier-cell"><i class="swatch" aria-hidden="true"></i>{{ featuredWord }}</span></td>
          <td colspan="2" class="holo-odds">抽到{{ RARITY_LABEL[rarity] }}时 <b>{{ rate }}%</b></td>
          <td class="pity-col"><span v-if="banner!.pity" class="pity-pill">{{ banner!.pity }} 次</span><template v-else>—</template></td>
        </tr>
        <tr v-if="res.holoChance" class="holo-row">
          <td><span class="tier-cell"><i class="swatch" aria-hidden="true"></i>镭射款</span></td>
          <td colspan="2" class="holo-odds">抽到对应卡片时 <b>{{ +res.holoChance.toFixed(2) }}%</b></td>
          <td class="pity-col">—</td>
        </tr>
      </tbody></table>
      <p v-else class="rates-wait" role="status">连接服务器后显示</p>
      <p v-if="banner && res" class="rates-note">卡池结束后，{{ featuredWord }}进入此间共鸣。</p>
    </Modal>
    <HistoryDialog v-if="history" @close="history = false" />
    <CardDetail v-if="detail" :card="detail" preview @close="detail = null" />
    <SkinDetail v-if="skin" :name="skin.ref" @close="skin = null" />
    <PlateDetail v-if="plate" :plate="plate" @close="plate = null" />
    <RevealScene v-if="revealing" :load="nextBatch" :remaining="pending" :again="again" @again="drawAgain" @close="onRevealClose" />
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
  padding: 12px 16px 13px 24px;
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
  --near-glow: rgba(var(--c-500-rgb), 0.65);
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
.pity.legendary {
  --near-glow: rgba(var(--gold-rgb), 0.72);
}
.pity.legendary svg {
  color: var(--gold);
}
/* A limited pool's own promise, in its pearl. */
.pity.featured {
  --near-glow: color-mix(in srgb, var(--holo-lilac) 85%, transparent);
}
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
.pity.legendary .ui-bar > i {
  background: var(--grad-gold);
}
/* Nearly there: past 90% of hard pity the gauge glows in its material, sweeps a soft sheen and breathes slowly. */
.near-tag {
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--c-100);
  color: var(--c-700);
  font: 800 10px/1.2 var(--font);
  font-style: normal;
}
.pity.legendary .near-tag {
  background: color-mix(in oklab, var(--gold-soft) 55%, var(--surface));
  color: var(--ink);
}
.pity.featured .near-tag {
  background: color-mix(in srgb, var(--holo-lilac) 28%, var(--surface));
  color: var(--night);
}
.pity.near b {
  color: var(--c-700);
}
.pity.legendary.near b {
  color: color-mix(in oklab, var(--gold) 65%, var(--ink));
}
.pity.featured.near b {
  color: var(--night);
}
.pity.near .ui-bar {
  overflow: visible;
}
.pity.near .ui-bar > i {
  position: relative;
  box-shadow: 0 0 10px 1px var(--near-glow);
  animation: near-breathe 2.8s var(--ease-in-out) infinite;
}
.pity.near .ui-bar > i::before {
  content: "";
  position: absolute;
  right: -2px;
  top: 50%;
  width: 7px;
  height: 7px;
  translate: 0 -50%;
  border-radius: 50%;
  background: #fff;
  box-shadow: 0 0 8px 2px var(--near-glow);
}
.pity.near .ui-bar > i::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: linear-gradient(90deg, transparent 20%, rgba(255, 255, 255, 0.72) 50%, transparent 80%) 150% 0 / 220% 100% no-repeat;
  animation: near-sheen 2.8s var(--ease-in-out) infinite;
}
.calm .pity.near .ui-bar > i,
.calm .pity.near .ui-bar > i::after {
  animation: none;
}
@keyframes near-breathe {
  50% {
    box-shadow: 0 0 4px 0 color-mix(in srgb, var(--near-glow) 45%, transparent);
  }
}
@keyframes near-sheen {
  0%, 45% { background-position: 150% 0; }
  100% { background-position: -60% 0; }
}
.supply {
  flex: 1;
  min-width: 0;
  overflow: hidden;
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
  transition: color var(--dur-fast);
}
.supply b.empty {
  color: var(--ink-3);
}
.supply b.abundant {
  color: var(--c-700);
}
.short-pill {
  margin-left: 2px;
  padding: 2px 6px;
  border-radius: var(--radius-s);
  background: var(--c-100);
  color: var(--ink-3);
  font: 700 var(--fs-caption)/1.2 var(--font);
  font-style: normal;
}
/* Today's tap shards, set like the pity counts beside them. */
.supply .today {
  gap: 4px;
  font-size: var(--fs-label);
}
.supply .today.short {
  color: var(--ink-3);
}
.supply .today svg {
  align-self: center;
  color: var(--c-700);
}
.supply .today.short svg {
  color: var(--ink-3);
}
.supply .today b {
  margin-left: 2px;
  font: 800 var(--fs-strong)/1 var(--font-latin);
}
.supply .today.short b {
  color: var(--ink-2);
}
.ten-gap {
  margin-left: 2px;
  font-size: var(--fs-caption);
  font-weight: 600;
  font-style: normal;
  color: var(--ink-3);
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
  padding-bottom: 4px;
}
.act {
  flex-direction: column;
  gap: 3px;
}
.once {
  min-width: 112px;
}
/* The space bar of the row: taller, wider, and set over a deeper 4px lip with a top catchlight. */
.ten {
  height: 60px;
  min-width: clamp(144px, 20cqw, 214px);
  padding: 0 26px;
  font-size: 18px;
}
.ten:not(:disabled) {
  --key-lip-h: 4px;
}
.ten:not(:disabled):active {
  --key-y: 4px;
  --key-lip-h: 0px;
}
.ten:not(:disabled)::before {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.38);
  pointer-events: none;
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
  opacity: 0.78;
}
.once:not(.primary):not(:disabled) .act-cost svg {
  color: var(--c-500);
}
.act.primary:not(:disabled) .act-cost svg {
  color: var(--c-800);
  fill: rgba(255, 255, 255, 0.42);
}
/* Two small keys in the height of the ten-draw key: the odds, and the save's own record. */
.side-keys {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.side-keys .side-key {
  width: 28px;
  padding: 0;
}
@container panel (max-width: 920px) {
  .console {
    gap: 14px;
    padding-left: 18px;
  }
  .pities {
    flex: 0 1 162px;
  }
  .short-pill,
  .ten-gap {
    display: none;
  }
  .ten {
    min-width: 148px;
    padding: 0 20px;
  }
  .once {
    min-width: 0;
    padding: 0 16px;
  }
}
@container panel (max-width: 820px) {
  .console {
    gap: 12px;
    padding-left: 16px;
  }
  .pities {
    flex: 0 1 152px;
  }
  .supply .today {
    display: none;
  }
  .ten {
    min-width: 136px;
    padding: 0 16px;
  }
  .once {
    min-width: 0;
    padding: 0 14px;
  }
}
/* Narrow: the keys keep their row; the supply line gives way first. */
@container panel (max-width: 720px) {
  .console {
    gap: 8px;
    padding: 10px 10px 11px 14px;
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
  .side-keys {
    gap: 0;
  }
  .console {
    padding-top: 8px;
    padding-bottom: 9px;
  }
}

/* Probabilities table: tonal material bars, right-aligned Barlow percentages, and flat pity pills. */
.rates {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--fs-body);
}
.rates th {
  padding: 2px 8px 9px;
  border-bottom: 1px solid var(--c-200);
  font: 700 var(--fs-caption)/1 var(--font);
  color: var(--ink-3);
  text-align: right;
  white-space: nowrap;
}
.rates th:first-child {
  text-align: left;
}
.rates td {
  padding: 9px 8px;
  border-bottom: 1px solid var(--c-100);
  font-weight: 700;
  color: var(--ink);
  white-space: nowrap;
}
.rates tbody tr:last-child td {
  border-bottom: 0;
}
.tier-cell {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}
.swatch {
  flex: none;
  width: 4px;
  height: 13px;
  border-radius: 2px;
  background: var(--swatch, var(--c-200));
}
.rates .featured-row {
  --swatch: var(--grad-pearl);
  background: linear-gradient(90deg, color-mix(in srgb, var(--holo-lilac) 18%, var(--surface)), transparent 80%);
}
.rates .featured-row .tier-cell {
  font-weight: 800;
  color: var(--night);
}
.rates .legendary {
  --swatch: var(--grad-gold);
  background: linear-gradient(90deg, color-mix(in oklab, var(--gold-soft) 28%, var(--surface)), transparent 80%);
}
.rates .legendary .tier-cell {
  font-weight: 800;
}
.rates .skin { --swatch: var(--c-500); }
.rates .epic { --swatch: var(--c-800); }
.rates .limited { --swatch: var(--pearl); }
.rates .rare { --swatch: var(--c-400); }
.rates .uncommon { --swatch: var(--c-300); }
.rates .common { --swatch: var(--c-200); }
.rates .holo-row {
  --swatch: var(--grad-holo);
  background: linear-gradient(90deg, color-mix(in srgb, var(--holo-lilac) 12%, var(--surface)),
    color-mix(in srgb, var(--holo-mint) 12%, var(--surface)) 55%, transparent);
}
.rates .num {
  text-align: right;
  font: 800 var(--fs-strong)/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink-2);
}
.rates .num.cur {
  color: var(--ink);
}
.rates .boosted .num.cur {
  color: var(--c-700);
}
.rates .zero .tier-cell,
.rates .zero .num.cur {
  color: var(--ink-3);
}
.rates .holo-odds {
  text-align: right;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.rates .holo-odds b {
  margin-left: 3px;
  font: 800 var(--fs-strong)/1 var(--font-latin);
  color: var(--night);
}
.rates .pity-col {
  text-align: right;
  font: 800 var(--fs-label)/1 var(--font-latin);
  color: var(--ink-3);
}
.pity-pill {
  display: inline-block;
  padding: 3px 7px;
  border-radius: var(--radius-s);
  background: var(--c-100);
  color: var(--ink-2);
  font: 800 var(--fs-caption)/1 var(--font);
  font-variant-numeric: tabular-nums;
}
.rates .featured-row .pity-pill {
  background: color-mix(in srgb, var(--holo-lilac) 24%, var(--surface));
  color: var(--night);
}
.rates .legendary .pity-pill {
  background: color-mix(in oklab, var(--gold-soft) 45%, var(--surface));
  color: var(--ink);
}
.rates-wait {
  margin: 0;
  padding: 16px 0 8px;
  text-align: center;
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--ink-3);
}
.rates-note {
  margin: 12px 0 0;
  padding: 8px 12px;
  border-radius: var(--radius-s);
  background: var(--c-50);
  font-size: var(--fs-label);
  line-height: 1.5;
  color: var(--ink-2);
}
</style>
