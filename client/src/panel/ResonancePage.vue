<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { prime } from "../audio/sfx";
import { manifest, getCard, type ManifestCard, type Rarity } from "../manifest";
import { type Item, RARITY_LABEL } from "../items";
import { poolOf, effectiveRates } from "../resonance";
import { formatCount, nextTapText, todayIncome } from "../income";
import { collection, resonate, draws, status, online, error } from "../stores/player";
import Icon from "../ui/Icon.vue";
import Modal from "../ui/Modal.vue";
import PoolStage from "./PoolStage.vue";
import RevealScene from "./RevealScene.vue";
import CardDetail from "./CardDetail.vue";
import SkinDetail from "./SkinDetail.vue";

const pool = poolOf();
const complete = computed(() => Object.values(pool).flat().every((i) => collection.owned[i.id]));
const rates = computed(() => effectiveRates(pool, collection.owned));
// Decode the draw sounds while the page sits idle, so the first draw is not silent.
onMounted(prime);
const revealing = ref(false);
const pending = ref(0);
/** Size of the last request, offered again from the result board. */
const last = ref(0);
const again = computed(() =>
  (last.value === 1 || last.value === 10) && online.value && !complete.value && draws.value >= last.value ? last.value : 0);
const probabilities = ref(false);
const detail = ref<ManifestCard | null>(null);
const skin = ref<Item | null>(null);
const tiers: Rarity[] = ["legendary", "skin", "epic", "rare", "uncommon", "common"];
const pityTiers = ["legendary", "skin"] as const;
const cost = manifest.economy.resonance.cost;
const income = computed(() => todayIncome(status.value));
const missingTier = (r: "legendary" | "skin") => pool[r].some((i) => !collection.owned[i.id]);
function inspect(item: Item) {
  if (item.kind === "card") detail.value = getCard(item.ref) ?? null;
  else skin.value = item;
}
/** Past this share of the hard pity the legendary gauge glows. */
const PITY_NEAR = 90;
const pityPercent = (r: "legendary" | "skin") =>
  Math.min(100, (status.value?.resonance.pity[r] ?? 0) / manifest.economy.resonance.pity[r] * 100);
function draw(count: number) {
  if (revealing.value || !online.value || complete.value || draws.value < count) return;
  pending.value = count;
  last.value = count;
  revealing.value = true;
}
function drawAgain() {
  pending.value = last.value;
}
async function nextBatch() {
  const result = await resonate(Math.min(pending.value, 100));
  pending.value = result ? Math.max(0, pending.value - result.length) : 0;
  return result;
}
</script>

<template>
  <div class="resonance-page ui-scroll">
    <p v-if="error" class="ui-error" role="alert">{{ error }}</p>
    <PoolStage :busy="revealing" :paused="probabilities || !!detail || !!skin" @inspect="inspect" />
    <footer class="console">
      <div class="pities">
        <template v-for="r in pityTiers" :key="r">
          <div v-if="missingTier(r)" class="pity" :class="[r, { near: r === 'legendary' && pityPercent(r) >= PITY_NEAR }]">
            <span>
              <Icon :name="r === 'legendary' ? 'crown' : 'shirt'" :size="14" />
              {{ r === 'legendary' ? '大隐藏' : '皮肤' }} <b>{{ status?.resonance.pity[r] ?? 0 }}</b><i>/ {{ manifest.economy.resonance.pity[r] }}</i>
            </span>
            <div class="ui-bar"><i :style="{ width: `${pityPercent(r)}%` }"></i></div>
          </div>
        </template>
      </div>
      <div class="supply">
        <p><span>可共鸣</span><b>{{ draws }}</b><span>次</span></p>
        <p v-if="income" class="today" :title="nextTapText(income)">
          <Icon name="shard" :size="13" />今日已获得<b>{{ formatCount(income.today) }}</b>
        </p>
      </div>
      <b v-if="complete" class="done">已集齐</b>
      <div class="keys">
        <button type="button" class="ui-btn large act once" :disabled="revealing || !online || draws < 1 || complete" @click="draw(1)">
          <span class="act-label">共鸣一次</span>
          <small class="act-cost"><Icon name="shard" :size="11" />{{ cost }}</small>
        </button>
        <button type="button" class="ui-btn act ten primary pulse" :disabled="revealing || !online || draws < 10 || complete" @click="draw(10)">
          <span class="act-label">共鸣十次</span>
          <small class="act-cost"><Icon name="shard" :size="11" />{{ cost * 10 }}</small>
        </button>
        <button type="button" class="ui-btn ghost rates-btn" title="概率说明" aria-label="概率说明" @click="probabilities = true">
          <Icon name="info" :size="18" />
        </button>
      </div>
    </footer>
    <Modal v-if="probabilities" title="共鸣概率" heading @close="probabilities = false">
      <table class="rates"><thead><tr><th>档位</th><th>基础概率</th><th>当前概率</th><th>保底</th></tr></thead><tbody>
        <tr v-for="r in tiers" :key="r"><td>{{ RARITY_LABEL[r] }}</td><td>{{ manifest.economy.resonance.rates[r] }}%</td><td>{{ rates[r] }}%</td><td>{{ r === 'legendary' ? '400 次' : r === 'skin' ? '200 次' : '—' }}</td></tr>
      </tbody></table>
    </Modal>
    <CardDetail v-if="detail" :card="detail" preview @close="detail = null" />
    <SkinDetail v-if="skin" :name="skin.ref" @close="skin = null" />
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
