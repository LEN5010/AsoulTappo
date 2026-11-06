<script setup lang="ts">
import { computed, ref } from "vue";
import { manifest, getCard, type ManifestCard, type Rarity } from "../manifest";
import { type Item, RARITY_LABEL } from "../items";
import { poolOf, effectiveRates, commonKindRates } from "../resonance";
import { collection, resonate, draws, shards, status, online, error } from "../stores/player";
import Icon from "../ui/Icon.vue";
import Modal from "../ui/Modal.vue";
import ShardCrystal from "../ui/ShardCrystal.vue";
import PoolStage from "./PoolStage.vue";
import RevealScene from "./RevealScene.vue";
import CardDetail from "./CardDetail.vue";
import SkinDetail from "./SkinDetail.vue";

const pool = poolOf();
const complete = computed(() => Object.values(pool).flat().every((i) => collection.owned[i.id]));
const rates = computed(() => effectiveRates(pool, collection.owned));
const commonRates = computed(() => commonKindRates(pool, collection.owned));
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
const missingTier = (r: "legendary" | "skin") => pool[r].some((i) => !collection.owned[i.id]);
function inspect(item: Item) {
  if (item.kind === "card") detail.value = getCard(item.ref) ?? null;
  else skin.value = item;
}
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
    <section class="dock">
      <div class="pities">
        <template v-for="r in pityTiers" :key="r">
          <div v-if="missingTier(r)" class="pity">
            <span>
              <Icon :name="r === 'legendary' ? 'crown' : 'shirt'" :size="15" />
              {{ r === 'legendary' ? '大隐藏' : '皮肤' }} <b>{{ status?.resonance.pity[r] ?? 0 }}</b> / {{ manifest.economy.resonance.pity[r] }}
            </span>
            <div class="ui-bar"><i :style="{ width: `${pityPercent(r)}%` }"></i></div>
          </div>
        </template>
        <button type="button" class="ui-btn small" @click="probabilities = true"><Icon name="info" :size="14" />概率说明</button>
      </div>
      <footer class="console">
        <ShardCrystal class="crystal" :size="58" />
        <div class="wallet">
          <p>碎片 <b>{{ shards }}</b></p>
          <small><Icon name="clock" :size="14" />收益 ×{{ status?.income.multiplier ?? 1 }} · 每分钟 {{ status?.income.perMinute ?? 16 }} 碎片</small>
        </div>
        <b v-if="complete" class="done">已集齐</b>
        <button v-if="draws >= 2" type="button" class="ui-btn ghost" :disabled="revealing || !online || complete" @click="draw(draws)">全部 ×{{ draws }}</button>
        <button type="button" class="ui-btn large act" :disabled="revealing || !online || draws < 1 || complete" @click="draw(1)">
          <Icon name="spark" :size="16" />共鸣一次
        </button>
        <button type="button" class="ui-btn large act primary pulse" :disabled="revealing || !online || draws < 10 || complete" @click="draw(10)">
          <Icon name="spark" :size="18" />共鸣十次
        </button>
      </footer>
    </section>
    <Modal v-if="probabilities" title="共鸣概率" @close="probabilities = false">
      <table class="rates"><thead><tr><th>档位</th><th>基础概率</th><th>当前概率</th><th>保底</th></tr></thead><tbody>
        <tr v-for="r in tiers" :key="r"><td>{{ RARITY_LABEL[r] }}</td><td>{{ manifest.economy.resonance.rates[r] }}%</td><td>{{ rates[r] }}%</td><td>{{ r === 'legendary' ? '400 次' : r === 'skin' ? '200 次' : '—' }}</td></tr>
      </tbody></table>
      <p class="ui-muted">当前单次共鸣：普卡 {{ commonRates.card.toFixed(2) }}%、普通表情 {{ commonRates.emote.toFixed(2) }}%。普通档先选类型，再在该类型内优先补缺；集齐后获得重复。</p>
      <p class="ui-muted">传说为大隐藏，史诗为小隐藏与跳舞卡，稀有为动态表情，罕见为绽放收藏集与脑洞波表情。高档集齐后概率并入普通档。重复表情返还 {{ manifest.economy.resonance.duplicateRefund }} 碎片，重复卡片累计数量。每次消耗 {{ manifest.economy.resonance.cost }} 碎片。</p>
      <p class="ui-muted">全角色共用一个池子。两个保底各自累计；同时到期时先触发大隐藏，下一次触发皮肤。对应档位集齐后保留进度，新增内容后可继续触发。</p>
    </Modal>
    <CardDetail v-if="detail" :card="detail" preview @close="detail = null" />
    <SkinDetail v-if="skin" :name="skin.ref" @close="skin = null" />
    <RevealScene v-if="revealing" :load="nextBatch" :remaining="pending" :again="again" @again="drawAgain" @close="revealing = false" />
  </div>
</template>

<style scoped>
.resonance-page {
  height: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px 20px 14px 16px;
  overflow-y: auto;
}
.dock {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px 12px;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line-2);
}
.pities {
  display: flex;
  align-items: center;
  gap: 20px;
  padding: 0 4px;
}
.pity {
  flex: 1;
  min-width: 0;
  font-size: var(--fs-label);
  color: var(--ink-2);
}
.pity + .pity {
  padding-left: 20px;
  border-left: 1px solid var(--line-2);
}
.pity span {
  display: flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
}
.pity b {
  font: 800 var(--fs-strong)/1 var(--font-latin);
  color: var(--ink);
}
.pity svg {
  color: var(--accent-deep);
}
.pity .ui-bar {
  margin-top: 5px;
}
.console {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  border-radius: var(--radius-m);
  background: linear-gradient(90deg, var(--accent-tint), var(--surface) 70%);
  box-shadow: inset 0 0 0 1px var(--line);
}
.wallet {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.wallet p {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin: 0;
  font: 800 var(--fs-heading)/1 var(--font);
  white-space: nowrap;
}
.wallet b {
  font: 800 34px/1 var(--font-latin);
  color: var(--accent-deep);
}
.wallet small {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: var(--fs-label);
  color: var(--ink-2);
  white-space: nowrap;
}
.done {
  font-size: var(--fs-strong);
  color: var(--accent-deep);
}
.act {
  min-width: clamp(116px, 15cqw, 158px);
  font-size: var(--fs-number);
}
.act:not(.primary):not(:disabled) svg {
  color: var(--accent);
}
@container panel (max-width: 820px) {
  .crystal,
  .wallet small {
    display: none;
  }
  .console {
    flex-wrap: wrap;
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
  border-bottom: 1px solid var(--line);
}
</style>
