<script setup lang="ts">
// The park's two numbers in the panel's top bar, left of the shard balance, while the park is shown: the coins held
// (with the +n of coins just come in rising into it) and the server-wide pool on a sunlit gold-foil key, the top prize
// of the next lottery draw. The coins are plain paper; the pool is a button (the top bar's drag skips buttons) that
// turns to the lottery page while the park is open.
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { status } from "../../stores/player";
import { park } from "../../stores/park";
import { reducedMotion } from "../../stores/theme";
import Icon from "../../ui/Icon.vue";
import { parkTab } from "./band";
import ParkCoin from "./ParkCoin.vue";
import { coinPops } from "./pops";

const ROLL_MS = 380;
const fmt = (n: number) => n.toLocaleString("en-US");
const coins = computed(() => park.value?.coins ?? status.value?.park?.coins ?? 0);
const jackpot = computed(() => park.value?.jackpot ?? null);
const open = computed(() => !!park.value?.unlocked);

const shownCoins = ref(coins.value);
const coinFlash = ref(0);
let coinPrimed = status.value !== null || park.value !== null;
let coinFrame = 0;

watch(coins, (to, from) => {
  cancelAnimationFrame(coinFrame);
  if (!coinPrimed || reducedMotion.value) {
    coinPrimed = true;
    shownCoins.value = to;
    return;
  }
  if (to > from) coinFlash.value++;
  const base = shownCoins.value;
  const start = performance.now();
  const step = (now: number) => {
    const t = Math.min(1, (now - start) / ROLL_MS);
    shownCoins.value = Math.round(base + (to - base) * (1 - (1 - t) ** 3));
    if (t < 1) coinFrame = requestAnimationFrame(step);
  };
  coinFrame = requestAnimationFrame(step);
});

const shownPot = ref(jackpot.value ?? 0);
const potFlash = ref(0);
let potFrame = 0;

watch(jackpot, (to, from) => {
  cancelAnimationFrame(potFrame);
  if (to == null) return;
  if (from == null || reducedMotion.value) {
    shownPot.value = to;
    return;
  }
  if (to > from) potFlash.value++;
  const base = shownPot.value;
  const start = performance.now();
  const step = (now: number) => {
    const t = Math.min(1, (now - start) / ROLL_MS);
    shownPot.value = Math.round(base + (to - base) * (1 - (1 - t) ** 3));
    if (t < 1) potFrame = requestAnimationFrame(step);
  };
  potFrame = requestAnimationFrame(step);
});

onBeforeUnmount(() => {
  cancelAnimationFrame(coinFrame);
  cancelAnimationFrame(potFrame);
});

const heldTip = computed(() => `持有驼币 ${fmt(coins.value)}`);
const potTip = computed(() =>
  jackpot.value != null ? `全服奖池 ${fmt(jackpot.value)}${open.value ? "" : " · 未开放"}` : "全服奖池",
);

function toLottery() {
  if (open.value) parkTab.value = "lottery";
}
</script>

<template>
  <span class="park-chips" :class="{ calm: reducedMotion }">
    <span class="chip held" :title="heldTip" :aria-label="heldTip">
      <ParkCoin :size="22" sheen />
      <b :key="coinFlash" :class="{ gain: coinFlash > 0 }">{{ fmt(shownCoins) }}</b>
      <span class="pops" aria-hidden="true">
        <i v-for="p in coinPops" :key="p.id" class="pop">+{{ p.n }}</i>
      </span>
    </span>
    <button
      type="button" class="chip pot" :class="{ live: open }" :title="potTip"
      :aria-label="`全服奖池 ${jackpot != null ? fmt(jackpot) : ''}`"
      :aria-disabled="open ? undefined : 'true'" @click="toLottery"
    >
      <small>奖池</small>
      <Icon name="shard" :size="14" />
      <b :key="potFlash" :class="{ gain: potFlash > 0 }">{{ jackpot != null ? fmt(shownPot) : "—" }}</b>
    </button>
  </span>
</template>

<style scoped>
.park-chips {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-right: 8px;
}
.chip {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 30px;
  padding: 0 12px 0 8px;
  box-sizing: border-box;
  border-radius: var(--radius-key);
  white-space: nowrap;
  cursor: default;
}
.chip b {
  min-width: 1ch;
  font: 800 18px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}
.held {
  background: var(--surface);
  box-shadow: inset 0 1px 0 #fff, var(--shadow-paper);
}
.held b.gain {
  animation: chip-gain 600ms var(--ease-out);
}

/* The server-wide top prize: a sunlit gold-foil plaque with crisp dark type. Only when unlocked (.live) does it gain
 * a pressable keycap lip and sink on press. */
.pot {
  --pot-face: linear-gradient(
    180deg,
    color-mix(in oklab, var(--gold-soft) 28%, #fff) 0%,
    var(--gold-soft) 64%,
    color-mix(in oklab, var(--gold-soft) 72%, var(--gold)) 100%
  );
  --key-lip-h: 0px;
  --key-y: 0px;
  isolation: isolate;
  margin: 0;
  padding-left: 10px;
  border: 0;
  font: inherit;
  background: none;
  color: var(--ink);
  -webkit-tap-highlight-color: transparent;
  transform: translateY(var(--key-y));
  transition: transform var(--dur-release) var(--ease-spring);
}
.pot::before,
.pot::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
}
.pot::before {
  z-index: -2;
  background: transparent;
  box-shadow: var(--shadow-paper);
  transform: translateY(var(--key-lip-h));
  transition:
    transform var(--dur-release) var(--ease-spring),
    box-shadow var(--dur-release) var(--ease-spring);
}
.pot::after {
  z-index: -1;
  background: var(--pot-face);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.86), inset 0 0 0 1px rgba(var(--gold-rgb), 0.45);
}
.pot svg {
  color: color-mix(in oklab, var(--gold) 68%, var(--c-700));
}
.pot small {
  margin-right: 1px;
  font: 800 var(--fs-label)/1 var(--font);
  color: var(--ink-2);
}
.pot b.gain {
  animation: chip-gain 600ms var(--ease-out);
}
.pot.live {
  --key-lip-h: 2px;
  margin-bottom: 2px;
  cursor: pointer;
}
.pot.live::before {
  background: var(--gold);
  box-shadow: 0 3px 8px -3px rgba(var(--gold-rgb), 0.55);
}
.pot.live:hover {
  --pot-face: linear-gradient(180deg, #fff 0%, var(--gold-soft) 78%);
  --key-y: -1px;
  --key-lip-h: 3px;
}
.pot.live:active {
  --key-y: 2px;
  --key-lip-h: 0px;
  transition-duration: var(--dur-press);
}
.pot.live:active::before {
  transition-duration: var(--dur-press);
}
@keyframes chip-gain {
  0%, 32% {
    color: var(--c-700);
  }
}

/* +n comes up from under the chip into the count and fades: there is no room above the panel's edge. */
.pops {
  position: absolute;
  left: 26px;
  top: 100%;
  z-index: 4;
  pointer-events: none;
}
.pop {
  position: absolute;
  left: 0;
  top: 0;
  padding: 1px 6px 2px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 2px 6px -2px rgba(var(--c-900-rgb), 0.25);
  font: 800 18px/1 var(--font-latin);
  font-style: normal;
  font-variant-numeric: tabular-nums;
  color: var(--c-700);
  white-space: nowrap;
  animation: pop-in 1100ms var(--ease-out) both;
}
.calm .pot,
.calm .pot::before {
  transition: none;
}
.calm .held b.gain,
.calm .pot b.gain,
.calm .pop {
  animation: none;
}
@keyframes pop-in {
  0% { opacity: 0; transform: translateY(14px) scale(0.8); }
  22% { opacity: 1; transform: translateY(2px) scale(1.06); }
  72% { opacity: 1; transform: translateY(-5px); }
  100% { opacity: 0; transform: translateY(-13px); }
}
</style>
