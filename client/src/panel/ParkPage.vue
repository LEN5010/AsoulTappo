<script setup lang="ts">
// The park (乐园, docs/design/amusement-park.md §11): a bar with the four pages (coins, scratch cards, the race and
// the lottery), the coins held and the server-wide jackpot, then the page picked. The games open at manifest
// economy.park.coin.minTaps taps in all; until then the page shows how far there is to go. Today's free coin is
// taken on the first visit of the day (§2.2). While the page is open it loads again with the status every RELOAD_MS
// at most: race and lottery prizes, the jackpot and a new day change without coins moving.
import { computed, onActivated, onBeforeUnmount, onDeactivated, ref, watch } from "vue";
import { manifest } from "../manifest";
import { status } from "../stores/player";
import { claimGift, loadPark, noPark, park, parkError } from "../stores/park";
import { reducedMotion } from "../stores/theme";
import Icon from "../ui/Icon.vue";
import SegTabs from "../ui/SegTabs.vue";
import { COIN_SMALL } from "./park/coin";
import CoinSection from "./park/CoinSection.vue";
import ScratchSection from "./park/ScratchSection.vue";
import RaceSection from "./park/RaceSection.vue";
import LotterySection from "./park/LotterySection.vue";

type Tab = "coin" | "scratch" | "race" | "lottery";
const TABS: { id: Tab; label: string }[] = [
  { id: "coin", label: "驼币" },
  { id: "scratch", label: "刮刮乐" },
  { id: "race", label: "赛跑" },
  { id: "lottery", label: "夺宝" },
];
const MIN_TAPS = manifest.economy.park!.coin.minTaps;
const RELOAD_MS = 15000;
const fmt = (n: number) => n.toLocaleString("en-US");

const tab = ref<Tab>("coin");
const taps = computed(() => status.value?.totals.taps ?? 0);
/** Known before the park is loaded: the taps in all are in every status. */
const locked = computed(() => (park.value ? !park.value.unlocked : !!status.value && taps.value < MIN_TAPS));
const lockPercent = computed(() => Math.min(100, (taps.value / MIN_TAPS) * 100));
const coins = computed(() => park.value?.coins ?? status.value?.park?.coins ?? 0);
/** The park could not be loaded: why, while there is nothing to show. */
const loadError = ref("");
const smallFailed = ref(false);

// ---- +n over the coins held: today's free coin, and coins just bought
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
onBeforeUnmount(() => popTimers.forEach(clearTimeout));

let active = false;
let entering = false;
let loadedAt = 0;
async function enter() {
  if (entering || noPark.value) return;
  entering = true;
  loadedAt = Date.now();
  try {
    const state = await loadPark();
    // Being offline already shows elsewhere; a refusal from the server shows here.
    const failed = state || park.value ? null : parkError.value;
    loadError.value = failed && failed.status > 0 ? failed.message : "";
    if (!state?.unlocked || !state.gift) return;
    const got = await claimGift();
    if (got) pop(got);
  } finally {
    entering = false;
  }
}

onActivated(() => {
  active = true;
  void enter();
});
onDeactivated(() => {
  active = false;
});
// Another save, a server that has just been reached, or the taps that open the park: load it again.
watch(() => [status.value?.player, taps.value >= MIN_TAPS] as const, ([player, enough], [was, before]) => {
  if (active && player && (player !== was || (enough && !before))) void enter();
});
// Each heartbeat brings a new status; the page follows it, not faster than RELOAD_MS.
watch(status, () => {
  if (active && Date.now() - loadedAt >= RELOAD_MS) void enter();
});
</script>

<template>
  <div class="park-page" :class="{ calm: reducedMotion }">
    <p v-if="noPark" class="ui-error" role="status">当前服务器未开放乐园</p>
    <template v-else>
      <div class="park-bar">
        <SegTabs v-model="tab" class="park-tabs" :tabs="TABS" label="乐园分页" :disabled="locked" />
        <span class="held" aria-label="驼币">
          <img v-if="!smallFailed" class="coin" :src="COIN_SMALL" alt="" draggable="false" @error="smallFailed = true" />
          <Icon v-else class="coin glyph" name="coin" :size="18" />
          <b>{{ fmt(coins) }}</b>
          <span class="pops" aria-hidden="true">
            <i v-for="p in pops" :key="p.id" class="pop">+{{ p.n }}</i>
          </span>
        </span>
        <span class="pot">
          全服奖池
          <b><Icon name="shard" :size="14" />{{ park ? fmt(park.jackpot) : "—" }}</b>
        </span>
      </div>
      <p v-if="loadError" class="ui-error" role="alert">{{ loadError }}</p>

      <div class="park-body ui-scroll">
        <div v-if="locked" class="lock" data-rise>
          <Icon name="lock" :size="22" />
          <p class="lock-text">累计敲击 1 万下后开放</p>
          <div class="lock-bar">
            <div class="ui-bar"><i :style="{ width: `${lockPercent}%` }"></i></div>
            <span><b>{{ fmt(taps) }}</b> / {{ fmt(MIN_TAPS) }}</span>
          </div>
        </div>
        <KeepAlive v-else>
          <CoinSection v-if="tab === 'coin'" @bought="pop" />
          <ScratchSection v-else-if="tab === 'scratch'" />
          <RaceSection v-else-if="tab === 'race'" />
          <LotterySection v-else />
        </KeepAlive>
      </div>
    </template>
  </div>
</template>

<style scoped>
.park-page {
  height: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  padding: 2px 20px 12px 16px;
}
.park-page > .ui-error {
  margin: 0 0 10px;
}

/* ---- the page's bar: the four pages, then the coins held and the jackpot, as on the codex */
.park-bar {
  flex: none;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px 18px;
  margin-bottom: 12px;
}
.park-tabs {
  flex: 0 1 340px;
  min-width: 0;
}
.held,
.pot {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
  white-space: nowrap;
}
.held {
  position: relative;
  margin-left: auto;
}
.held b,
.pot b {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font: 800 var(--fs-section)/1 var(--font-latin);
  color: var(--ink);
}
.pot svg {
  color: var(--c-600);
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
/* +n rises off the coins held and fades. */
.pops {
  position: absolute;
  left: 24px;
  top: -4px;
  pointer-events: none;
}
.pop {
  position: absolute;
  left: 0;
  bottom: 0;
  font: 800 20px/1 var(--font-latin);
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

.park-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 2px 2px 8px;
}

/* ---- the lock, on paper */
.lock {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px 16px;
  padding: 26px 22px 28px;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: var(--shadow-paper);
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
</style>
