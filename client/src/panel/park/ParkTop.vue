<script setup lang="ts">
// The park's top block (docs/design/amusement-park.md §2, §4, §8.3, §11): a coral head with the name, the
// server-wide jackpot and the coin; under it the coins held, the keys that buy more, today's result and the stamps.
// Before the park opens for the save the sheet holds only how far there is to go.
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { manifest } from "../../manifest";
import { online, shards, status } from "../../stores/player";
import { buyCoins, park, parkError } from "../../stores/park";
import { reducedMotion } from "../../stores/theme";
import Icon from "../../ui/Icon.vue";
import { COIN, COIN_SMALL } from "./coin";

/** [gift]: coins of today's free coin just taken, shown as a +n on the balance whenever [giftKey] changes. */
const props = defineProps<{ gift: number; giftKey: number }>();
const emit = defineEmits<{ redeem: [] }>();

// The bundled manifest always has the park; the server checks every number again.
const CFG = manifest.economy.park!.coin;
const PACKS = [1, 5, 10];
const BADGES = ["铜驼", "银驼", "金驼"];
const fmt = (n: number) => n.toLocaleString("en-US");

const calm = computed(() => reducedMotion.value);
const state = computed(() => park.value);
const coins = computed(() => state.value?.coins ?? status.value?.park?.coins ?? 0);
const taps = computed(() => status.value?.totals.taps ?? 0);
/** Known before the park is loaded: the taps in all are in every status. */
const locked = computed(() => (state.value ? !state.value.unlocked : !!status.value && taps.value < CFG.minTaps));
const lockPercent = computed(() => Math.min(100, (taps.value / CFG.minTaps) * 100));
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

// ---- +n over the balance: today's free coin, and coins just bought
const pops = ref<{ id: number; n: number }[]>([]);
let popId = 0;
const popTimers = new Set<ReturnType<typeof setTimeout>>();
function pop(n: number) {
  const id = ++popId;
  pops.value = [...pops.value, { id, n }];
  const t = setTimeout(() => {
    popTimers.delete(t);
    pops.value = pops.value.filter((p) => p.id !== id);
  }, 1100);
  popTimers.add(t);
}
watch(() => props.giftKey, () => { if (props.gift > 0) pop(props.gift); });
onBeforeUnmount(() => popTimers.forEach(clearTimeout));

async function buy(n: number) {
  if (blocked(n) !== null) return;
  busy.value = n;
  buyError.value = "";
  const ok = await buyCoins(n);
  busy.value = 0;
  if (ok) pop(n);
  else buyError.value = parkError.value?.message ?? "";
}
// A reason from the server holds until the state it was about changes.
watch(() => [state.value?.buyLeft, state.value?.coins, shards.value, online.value], () => { if (!busy.value) buyError.value = ""; });

/** The coin pictures step aside when they cannot load: the big one leaves, the small one turns into the glyph. */
const coinShown = ref(true);
const smallFailed = ref(false);
</script>

<template>
  <section class="top" :class="{ calm }" aria-label="游乐园">
    <header class="head" data-rise>
      <div class="title">
        <span class="eyebrow" aria-hidden="true">PARK</span>
        <h2 class="name">游乐园</h2>
      </div>
      <p class="jackpot" :class="{ roomy: coinShown }">
        <span>全服奖池</span>
        <b><Icon name="shard" :size="18" />{{ state ? fmt(state.jackpot) : "—" }}</b>
      </p>
      <img v-if="coinShown" class="big-coin" :src="COIN" alt="" draggable="false" @error="coinShown = false" />
    </header>

    <div v-if="locked" class="sheet lock" data-rise>
      <Icon name="lock" :size="22" />
      <p class="lock-text">累计敲击 1 万下后开放</p>
      <div class="lock-bar">
        <div class="ui-bar"><i :style="{ width: `${lockPercent}%` }"></i></div>
        <span><b>{{ fmt(taps) }}</b> / {{ fmt(CFG.minTaps) }}</span>
      </div>
    </div>

    <div v-else class="sheet" data-rise>
      <div class="wallet">
        <div class="balance">
          <img v-if="!smallFailed" class="coin" :src="COIN_SMALL" alt="" draggable="false" @error="smallFailed = true" />
          <Icon v-else class="coin glyph" name="coin" :size="20" />
          <b class="count">{{ fmt(coins) }}</b>
          <span class="unit">驼币</span>
          <span class="pops" aria-hidden="true">
            <i v-for="p in pops" :key="p.id" class="pop">+{{ p.n }}</i>
          </span>
          <button type="button" class="ui-btn small redeem" @click="emit('redeem')">兑换码</button>
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

      <dl class="ledger">
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
            <span v-if="badge" class="badge" :class="`metal-${badge}`">
              <img v-if="!smallFailed" :src="COIN_SMALL" alt="" draggable="false" />{{ BADGES[badge - 1] }}
            </span>
          </dd>
        </div>
      </dl>
    </div>
  </section>
</template>

<style scoped>
/* The same build as the scratch stall and the check-in calendar: a coral head over one sheet of paper. */
.top {
  flex: none;
  display: flex;
  flex-direction: column;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: var(--shadow-paper);
}
.head {
  --coin-size: 112px;
  position: relative;
  display: flex;
  align-items: flex-end;
  gap: 20px;
  min-height: 92px;
  padding: 14px 22px;
  box-sizing: border-box;
  border-radius: var(--radius-l) var(--radius-l) 0 0;
  background: var(--grad-sky);
}
/* Halftone printed faintly into the coral, growing toward the right. */
.head::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: #fff;
  pointer-events: none;
  opacity: 0.32;
  mask:
    url("../../assets/patterns/halftone.svg") 0 -28px / 280px 140px repeat-x,
    linear-gradient(90deg, transparent 34%, #000 72%);
  mask-composite: intersect;
}
.title,
.jackpot,
.big-coin {
  position: relative;
  z-index: 1;
}
.title {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.eyebrow {
  font: 800 12px/1 var(--font-latin);
  letter-spacing: 0.26em;
  color: var(--ink);
  opacity: 0.72;
}
.name {
  margin: 0;
  font: 800 38px/1 var(--font);
  letter-spacing: 0.06em;
  color: #fff;
  white-space: nowrap;
}
.jackpot {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  margin: 0 0 0 auto;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink);
  white-space: nowrap;
}
.jackpot.roomy {
  margin-right: calc(var(--coin-size) - 4px);
}
.jackpot b {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font: 800 30px/1 var(--font-latin);
}
.jackpot svg {
  color: #fff;
}
/* The coin is a thing: it leans, casts a shadow and hangs over the sheet's edge. */
.big-coin {
  position: absolute;
  right: 16px;
  bottom: -30px;
  width: var(--coin-size);
  height: var(--coin-size);
  object-fit: contain;
  rotate: 8deg;
  filter: drop-shadow(0 6px 8px rgba(var(--c-900-rgb), 0.3));
  pointer-events: none;
  user-select: none;
}

.sheet {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px 22px 20px;
  border-radius: 0 0 var(--radius-l) var(--radius-l);
}

/* ---- coins held, and buying more */
.wallet {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 14px 20px;
}
.balance {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 52px;
}
.coin {
  width: 20px;
  height: 20px;
  flex: none;
  filter: drop-shadow(0 1px 1px rgba(var(--c-900-rgb), 0.25));
}
.coin.glyph {
  color: var(--gold);
  filter: none;
}
.count {
  font: 800 40px/1 var(--font-latin);
  color: var(--ink);
}
.unit {
  align-self: flex-end;
  margin-bottom: 7px;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.redeem {
  margin-left: 8px;
}
/* +n rises off the balance and fades. */
.pops {
  position: absolute;
  left: 28px;
  top: -6px;
  pointer-events: none;
}
.pop {
  position: absolute;
  left: 0;
  bottom: 0;
  font: 800 22px/1 var(--font-latin);
  font-style: normal;
  color: var(--c-700);
  white-space: nowrap;
  animation: pop-up 1100ms var(--ease-out) both;
}
.calm .pop {
  animation: none;
}
@keyframes pop-up {
  0% { opacity: 0; transform: translateY(10px) scale(0.8); }
  20% { opacity: 1; transform: translateY(0) scale(1.08); }
  70% { opacity: 1; transform: translateY(-8px); }
  100% { opacity: 0; transform: translateY(-14px); }
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
/* The badge is the same coin struck in another metal. */
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
.metal-1 img {
  filter: sepia(0.6) hue-rotate(-18deg) saturate(1.3) brightness(0.86);
}
.metal-2 img {
  filter: grayscale(1) brightness(1.18) contrast(1.05);
}

/* ---- the lock */
.lock {
  flex-direction: row;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px 16px;
  padding: 26px 22px 28px;
  color: var(--c-700);
}
.lock-text {
  margin: 0;
  font: 800 var(--fs-strong)/1.4 var(--font);
  color: var(--ink);
}
.lock-bar {
  flex: 1;
  min-width: 200px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.lock-bar .ui-bar {
  flex: 1;
}
.lock-bar span {
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: var(--ink-2);
  white-space: nowrap;
}
.lock-bar b {
  color: var(--ink);
}

@container panel (max-width: 760px) {
  .head {
    --coin-size: 92px;
  }
  .name {
    font-size: 32px;
  }
  .jackpot b {
    font-size: 26px;
  }
  .pack {
    min-width: 72px;
    padding: 0 12px;
  }
}
</style>
