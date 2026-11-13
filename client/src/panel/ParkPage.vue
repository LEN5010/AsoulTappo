<script setup lang="ts">
// The park (乐园, docs/design/amusement-park.md §11, docs/design/park-ui-rebuild.md §4): one sheet of paper whose top
// edge is a coral band with the four pages (coins, scratch cards, the race and the lottery), the page's timer and
// its host; the page picked fills the white body. The coins held and the server-wide jackpot are in the panel's top
// bar (ParkChips). The games open at manifest economy.park.coin.minTaps taps in all; until then the body shows how far
// there is to go. Today's free coin is taken on the first visit of the day (§2.2). While the page is open it loads
// again with the status every RELOAD_MS at most: race and lottery prizes, the jackpot and a new day change without
// coins moving.
import { computed, onActivated, onBeforeUnmount, onDeactivated, ref, watch } from "vue";
import { manifest } from "../manifest";
import { status } from "../stores/player";
import { claimGift, loadPark, noPark, park, parkError } from "../stores/park";
import { reducedMotion } from "../stores/theme";
import { ACHAO } from "../ui/achao";
import { bandOf, clearFlash, flashedHost, flashHost, parkTab, type ParkTab } from "./park/band";
import { popCoins } from "./park/pops";
import ParkBand from "./park/ParkBand.vue";
import ParkCoin from "./park/ParkCoin.vue";
import CoinSection from "./park/CoinSection.vue";
import ScratchSection from "./park/ScratchSection.vue";
import RaceSection from "./park/RaceSection.vue";
import LotterySection from "./park/LotterySection.vue";
import "./park/park.css";

const TABS: { id: ParkTab; label: string }[] = [
  { id: "coin", label: "驼币" },
  { id: "scratch", label: "刮刮乐" },
  { id: "race", label: "赛跑" },
  { id: "lottery", label: "夺宝" },
];
const MIN_TAPS = manifest.economy.park!.coin.minTaps;
const RELOAD_MS = 15000;
/** 阿草 takes today's free coin for this long. */
const GIFT_HOST_MS = 1000;
/** The host while no page has put one up: the park still shut, or not on this server. */
const HOST_IDLE = ACHAO["招商"];
const HOST_CLOSED = ACHAO["拒绝"];
const fmt = (n: number) => n.toLocaleString("en-US");

// Shared through band.ts so a section can switch pages; a fresh park page opens on the coins, as before.
const tab = parkTab;
tab.value = "coin";
const taps = computed(() => status.value?.totals.taps ?? 0);
/** Known before the park is loaded: the taps in all are in every status. */
const locked = computed(() => (park.value ? !park.value.unlocked : !!status.value && taps.value < MIN_TAPS));
const lockPercent = computed(() => Math.min(100, (taps.value / MIN_TAPS) * 100));
/** The park could not be loaded: why, while there is nothing to show. */
const loadError = ref("");

const entry = computed(() => (noPark.value || locked.value ? {} : bandOf(tab.value)));
const host = computed(() => {
  if (noPark.value) return HOST_CLOSED;
  return flashedHost.value || entry.value.host || HOST_IDLE;
});
const hostKind = computed(() => (!noPark.value && !flashedHost.value && entry.value.host ? entry.value.hostKind : undefined));

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
    if (got) {
      popCoins(got);
      if (ACHAO["收到"]) flashHost(ACHAO["收到"], GIFT_HOST_MS);
    }
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
onBeforeUnmount(clearFlash);
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
    <div class="sheet">
      <ParkBand
        v-model="tab" :tabs="TABS" :disabled="locked || noPark" :host="host" :host-kind="hostKind"
        :timer="entry.timer" :info="entry.info"
      />

      <div class="park-body ui-scroll">
        <p v-if="noPark" class="closed" role="status">当前服务器未开放乐园</p>
        <template v-else>
          <p v-if="loadError" class="ui-error park-error" role="alert">{{ loadError }}</p>
          <div v-if="locked" class="lock" data-rise>
            <ParkCoin :size="120" grey />
            <p class="lock-text">累计敲击 <b>1</b> 万下后开放</p>
            <div class="lock-bar">
              <div class="ui-bar"><i :style="{ width: `${lockPercent}%` }"></i></div>
              <span><b>{{ fmt(taps) }}</b> / {{ fmt(MIN_TAPS) }}</span>
            </div>
          </div>
          <KeepAlive v-else>
            <CoinSection v-if="tab === 'coin'" @bought="popCoins" />
            <ScratchSection v-else-if="tab === 'scratch'" />
            <RaceSection v-else-if="tab === 'race'" />
            <LotterySection v-else />
          </KeepAlive>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* The top padding is the host's headroom: its head rises over the band into it. */
.park-page {
  height: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  padding: 28px 20px 14px 16px;
}
.sheet {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: var(--shadow-paper);
}
/* The white body covers the host from the waist down. */
.park-body {
  position: relative;
  z-index: 1;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  border-radius: 0 0 var(--radius-l) var(--radius-l);
  background: var(--surface);
}
/* A page stretches to the body's height, so its bottom bar (.park-actions) sits at the foot of the sheet. */
.park-body > :not(.park-error) {
  flex: 1 0 auto;
}
.park-error {
  flex: none;
  margin: 16px 22px 0;
}
.closed {
  margin: 0;
  padding: 28px 22px;
  font: 700 var(--fs-strong)/1.5 var(--font);
  color: var(--ink-2);
  text-align: center;
}

/* ---- the lock: a grey coin, and how far there is to go */
.lock {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 18px;
  padding: 32px 22px 40px;
}
.lock-text {
  margin: 4px 0 0;
  font: 800 var(--fs-section)/1.4 var(--font);
  color: var(--ink);
}
.lock-text b {
  font: 800 24px/1 var(--font-latin);
}
.lock-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  width: min(360px, 100%);
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

@container panel (max-height: 560px) {
  .park-page {
    padding-top: 10px;
  }
  .lock {
    gap: 12px;
    padding-block: 16px 20px;
  }
}
@container panel (max-width: 680px) {
  .park-page {
    padding: 10px 12px 10px 10px;
  }
}
</style>
