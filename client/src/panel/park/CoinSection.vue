<script setup lang="ts">
// The coin page of the park (docs/design/amusement-park.md §2, §4, §8.3, §10): the coins held and the keys that buy
// more, today's result and the stamps on one band, and the redeem code field.
import { computed, ref, watch } from "vue";
import { manifest } from "../../manifest";
import { online, shards, status } from "../../stores/player";
import { buyCoins, park, parkError } from "../../stores/park";
import { ACHAO } from "../../ui/achao";
import Icon from "../../ui/Icon.vue";
import { useBand } from "./band";
import { BADGE_ART, COIN } from "./coin";
import RedeemForm from "./RedeemForm.vue";

const emit = defineEmits<{ bought: [count: number] }>();
useBand("coin", () => ({ host: ACHAO["招商"] }));

// The bundled manifest always has the park; the server checks every number again.
const CFG = manifest.economy.park!.coin;
const PACKS = [1, 5, 10];
const BADGES = ["铜驼", "银驼", "金驼"];
const fmt = (n: number) => n.toLocaleString("en-US");

const state = computed(() => park.value);
const coins = computed(() => state.value?.coins ?? status.value?.park?.coins ?? 0);
const badge = computed(() => Math.min(BADGES.length, state.value?.badge ?? 0));
const stampPercent = computed(() => ((state.value?.stamps ?? 0) / CFG.stampsPerCoin) * 100);

const busy = ref(0);
const buyError = ref("");

/** Why [n] coins cannot be bought now: a short reason, "" for a state that needs none (loading, busy), null when they can. */
function blocked(n: number): string | null {
  if (!online.value) return "未连接";
  const s = state.value;
  if (!s || busy.value) return "";
  if (s.buyLeft === 0) return "今日已买满";
  if (n > s.buyLeft) return "";
  if (s.coins + n > CFG.hold) return `最多持有 ${CFG.hold} 枚`;
  if (shards.value < n * CFG.price) return "碎片不足";
  return null;
}
const note = computed(() => {
  if (buyError.value) return buyError.value;
  const why = blocked(1);
  if (why) return why;
  return state.value ? `今日还可买 ${state.value.buyLeft} 枚` : "";
});

async function buy(n: number) {
  if (blocked(n) !== null) return;
  busy.value = n;
  buyError.value = "";
  const ok = await buyCoins(n);
  busy.value = 0;
  if (ok) emit("bought", n);
  else buyError.value = parkError.value?.message ?? "";
}
// A reason from the server holds until the state it was about changes.
watch(() => [state.value?.buyLeft, state.value?.coins, shards.value, online.value], () => { if (!busy.value) buyError.value = ""; });

/** The big coin steps aside when it cannot load. */
const coinShown = ref(true);
</script>

<template>
  <section class="coins" aria-label="驼币">
    <div class="wallet" data-rise>
      <div class="balance">
        <img v-if="coinShown" class="big-coin" :src="COIN" alt="" draggable="false" @error="coinShown = false" />
        <b class="count">{{ fmt(coins) }}</b>
        <span class="unit">驼币</span>
      </div>

      <div class="buy">
        <div class="packs" role="group" aria-label="买驼币">
          <button
            v-for="n in PACKS" :key="n" type="button" class="ui-btn pack"
            :disabled="blocked(n) !== null" :aria-busy="busy === n" @click="buy(n)"
          >
            <span class="pack-n">{{ n }} 枚</span>
            <small class="pack-cost"><Icon name="shard" :size="11" />{{ fmt(n * CFG.price) }}</small>
          </button>
        </div>
        <p class="note" :class="{ warn: !!buyError || !!blocked(1) }" role="status">{{ note }}</p>
      </div>
    </div>

    <dl class="ledger" data-rise>
      <div>
        <dt>今日花费</dt>
        <dd><Icon name="shard" :size="13" />{{ fmt(state?.today.spent ?? 0) }}</dd>
      </div>
      <div>
        <dt>今日赢得</dt>
        <dd><Icon name="shard" :size="13" />{{ fmt(state?.today.won ?? 0) }}</dd>
      </div>
      <div class="stamps">
        <dt>印章</dt>
        <dd>
          <span class="stamp-count"><b>{{ state?.stamps ?? 0 }}</b> / {{ CFG.stampsPerCoin }}</span>
          <span class="ui-bar stamp-bar"><i :style="{ width: `${stampPercent}%` }"></i></span>
          <span v-if="badge" class="badge">
            <img :src="BADGE_ART[badge - 1]" alt="" draggable="false" />{{ BADGES[badge - 1] }}
          </span>
        </dd>
      </div>
    </dl>

    <div class="redeem" data-rise>
      <h3 class="ui-label">兑换码</h3>
      <RedeemForm />
    </div>
  </section>
</template>

<style scoped>
/* On the park's sheet, under the coral band. */
.coins {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px 22px 22px;
}

/* ---- coins held, and buying more */
.wallet {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 14px 20px;
}
.balance {
  display: flex;
  align-items: center;
  gap: 12px;
}
/* The coin is a thing: it leans and casts a shadow. */
.big-coin {
  width: 72px;
  height: 72px;
  flex: none;
  object-fit: contain;
  rotate: -8deg;
  filter: drop-shadow(0 5px 6px rgba(var(--c-900-rgb), 0.28));
  user-select: none;
}
.count {
  font: 800 44px/1 var(--font-latin);
  color: var(--ink);
}
.unit {
  align-self: flex-end;
  margin-bottom: 8px;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}

.buy {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
  margin-left: auto;
}
.packs {
  display: flex;
  gap: 10px;
  padding-bottom: 3px;
}
.pack {
  flex-direction: column;
  gap: 3px;
  height: 52px;
  min-width: 84px;
  padding: 0 16px;
}
.pack-n {
  font-size: var(--fs-strong);
}
.pack-cost {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font: 800 var(--fs-label)/1 var(--font-latin);
  letter-spacing: 0.04em;
  opacity: 0.75;
}
.note {
  min-height: 16px;
  margin: 0;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-3);
}
.note.warn {
  color: var(--c-700);
}

/* ---- today's result and the stamps, on one tonal band */
.ledger {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px 28px;
  margin: 0;
  padding: 12px 16px;
  border-radius: var(--radius-m);
  background: var(--c-100);
}
.ledger > div {
  display: flex;
  align-items: center;
  gap: 8px;
}
.ledger dt {
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.ledger dd {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin: 0;
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: var(--ink);
}
.ledger dd svg {
  color: var(--c-600);
}
.ledger .stamps {
  flex: 1;
  min-width: 220px;
}
.stamps dd {
  flex: 1;
  gap: 10px;
}
.stamp-count {
  white-space: nowrap;
  color: var(--ink-2);
}
.stamp-count b {
  color: var(--ink);
}
.stamp-bar {
  flex: 1;
  min-width: 60px;
  max-width: 200px;
}
/* The badge is the coin struck in copper, silver or gold (BADGE_ART). */
.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font: 700 var(--fs-label)/1 var(--font);
  color: var(--ink);
  white-space: nowrap;
}
.badge img {
  width: 18px;
  height: 18px;
}

/* ---- the redeem code */
.redeem {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.redeem h3 {
  margin: 0;
}

@container panel (max-width: 760px) {
  .pack {
    min-width: 72px;
    padding: 0 12px;
  }
}
</style>
