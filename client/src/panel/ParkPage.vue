<script setup lang="ts">
// The park (乐园, protocol/PROTOCOL.md 乐园): one sheet of paper whose top
// edge is a coral band with the four pages (coins, scratch cards, the race and the lottery), the page's timer and
// its host; the page picked fills the white body. The coins held and the server-wide pool (the lottery's top prize)
// are in the panel's top bar (ParkChips). The games open at economy.park.coin.minTaps taps in all; until then
// the body shows how far there is to go. Today's free coin is granted by the server with a status (`park.gifted`, in
// that one status only); when the park is shown at that moment, +1 rises into the coins and 阿草 takes it. A server
// that still waits for the first visit of the day (`gift` in the park's state) is asked for it here. While the page is
// open it loads again with the status every RELOAD_MS at most: race and lottery prizes, the pool and a new day change
// without coins moving.
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from "vue";
import { economy } from "../stores/economy";
import { status } from "../stores/player";
import { claimGift, loadPark, noPark, park, parkError } from "../stores/park";
import { reducedMotion } from "../stores/theme";
import { ACHAO } from "../ui/achao";
import Icon from "../ui/Icon.vue";
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
/** The sections read the park's numbers from the server's economy: they open once it is known. */
const ready = computed(() => !!economy.value?.park);
const minTaps = computed(() => economy.value?.park?.coin.minTaps ?? 0);
const RELOAD_MS = 15000;
/** 阿草 takes today's free coin for this long. */
const GIFT_HOST_MS = 1000;
/** The last free coin shown or passed by (save and day), shared with every window: a grant plays once at most. */
const GIFT_SEEN_KEY = "asoultappo.parkGift.v1";
/** The host while no page has put one up: the park still shut, or not on this server. */
const HOST_IDLE = ACHAO["招商"];
const HOST_CLOSED = ACHAO["拒绝"];
const fmt = (n: number) => n.toLocaleString("en-US");

// Shared through band.ts so a section can switch pages; a fresh park page opens on the coins, as before.
const tab = parkTab;
tab.value = "coin";
const taps = computed(() => status.value?.totals.taps ?? 0);
/** Known before the park is loaded: the taps in all are in every status. */
const locked = computed(() => (park.value ? !park.value.unlocked : !!status.value && taps.value < minTaps.value));
const lockPercent = computed(() => (minTaps.value ? Math.min(100, (taps.value / minTaps.value) * 100) : 0));
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

function celebrateGift(n: number) {
  popCoins(n);
  if (ACHAO["收到"]) flashHost(ACHAO["收到"], GIFT_HOST_MS);
}
let lastGift = "";
/** Marks [key] as the last grant seen; false when it was already. */
function firstSight(key: string): boolean {
  try {
    if (localStorage.getItem(GIFT_SEEN_KEY) === key) return false;
    localStorage.setItem(GIFT_SEEN_KEY, key);
  } catch {
    /* storage unavailable: the in-memory mark below still keeps this window from playing it twice */
  }
  if (lastGift === key) return false;
  lastGift = key;
  return true;
}
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
    if (got) celebrateGift(got);
  } finally {
    entering = false;
  }
}

/**
 * Booth shortcuts while the park is shown and unlocked: `[` / `]` cycle booths and `Alt+1`..`Alt+4` jump directly,
 * standing down when an overlay is up or focus is inside an editable field (and leaving plain `0`–`9` free for
 * `MainPanel`'s sidebar nav and `LotterySection`'s number picker).
 */
function onPageKey(e: KeyboardEvent) {
  if (!active || locked.value || noPark.value || !ready.value || e.isComposing || e.repeat) return;
  if (document.querySelector("[data-overlay]")) return;
  const el = (e.target as HTMLElement | null) ?? (document.activeElement as HTMLElement | null);
  if (el?.closest?.("input, textarea, select, [contenteditable]")) return;
  if (e.altKey && !e.ctrlKey && !e.metaKey) {
    const m = /^Digit([1-4])$/.exec(e.code);
    if (m) {
      e.preventDefault();
      tab.value = TABS[Number(m[1]) - 1]!.id;
    }
    return;
  }
  if (!e.ctrlKey && !e.metaKey && !e.altKey && (e.key === "[" || e.key === "]")) {
    e.preventDefault();
    const at = TABS.findIndex((t) => t.id === tab.value);
    const next = ((at < 0 ? 0 : at) + (e.key === "]" ? 1 : -1) + TABS.length) % TABS.length;
    tab.value = TABS[next]!.id;
  }
}

let listening = false;
function setListening(on: boolean) {
  if (on === listening) return;
  listening = on;
  if (on) window.addEventListener("keydown", onPageKey);
  else window.removeEventListener("keydown", onPageKey);
}

onMounted(() => setListening(true));
onActivated(() => {
  active = true;
  setListening(true);
  void enter();
});
onDeactivated(() => {
  active = false;
  setListening(false);
});
onBeforeUnmount(() => {
  setListening(false);
  clearFlash();
});
// Another save, a server that has just been reached, or the taps that open the park: load it again.
watch(() => [status.value?.player, taps.value >= minTaps.value] as const, ([player, enough], [was, before]) => {
  if (active && player && (player !== was || (enough && !before))) void enter();
});
// Each heartbeat brings a new status; the page follows it, not faster than RELOAD_MS.
watch(status, () => {
  if (active && Date.now() - loadedAt >= RELOAD_MS) void enter();
});
// The status that granted today's free coin. The same status can come again (the desk sends it on along with other
// changes), so each grant is marked by save and day; one that arrives while the park is not shown is only marked.
watch(() => status.value?.park?.gifted, (n) => {
  const s = status.value;
  if (!s || !n || n <= 0) return;
  const key = `${s.player}|${s.dailyTaps?.day ?? new Date().toDateString()}`;
  if (firstSight(key) && active && !locked.value && !noPark.value) celebrateGift(n);
});
</script>

<template>
  <div class="park-page" :class="{ calm: reducedMotion }">
    <div class="sheet">
      <ParkBand
        v-model="tab" :tabs="TABS" :disabled="locked || noPark || !ready" :host="host" :host-kind="hostKind"
        :timer="entry.timer" :info="entry.info"
      />

      <div class="park-body ui-scroll">
        <p v-if="noPark" class="closed" role="status">当前服务器未开放乐园</p>
        <template v-else>
          <p v-if="loadError" class="ui-error park-error" role="alert">{{ loadError }}</p>
          <p v-if="!ready" class="closed" role="status">连接服务器后开放</p>
          <div v-else-if="locked" class="lock" data-rise>
            <div class="lock-medallion" aria-hidden="true">
              <ParkCoin :size="112" grey />
              <span class="lock-seal"><Icon name="lock" :size="15" /></span>
            </div>
            <p class="lock-text">累计敲击 <b>{{ fmt(minTaps) }}</b> 下后开放</p>
            <div class="lock-card" role="progressbar" :aria-valuenow="taps" :aria-valuemin="0" :aria-valuemax="minTaps">
              <div class="lock-meta">
                <span><b>{{ fmt(taps) }}</b> / {{ fmt(minTaps) }}</span>
                <em>{{ Math.floor(lockPercent) }}%</em>
              </div>
              <div class="ui-bar"><i :style="{ width: `${lockPercent}%` }"></i></div>
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
  padding: 26px 20px 14px 16px;
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

/* ---- The lock: a sealed medallion well, the tap threshold, and a tonal progress plaque. */
.lock {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 28px 22px 34px;
}
.lock-medallion {
  position: relative;
  display: grid;
  place-items: center;
  width: 152px;
  height: 152px;
  border-radius: 50%;
  background: var(--c-100);
  box-shadow: inset 0 2px 5px rgba(var(--c-900-rgb), 0.08);
}
.lock-medallion::before {
  content: "";
  position: absolute;
  inset: 9px;
  border: 2px dashed var(--c-200);
  border-radius: 50%;
  pointer-events: none;
}
.lock-seal {
  position: absolute;
  right: 12px;
  bottom: 8px;
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--surface);
  box-shadow: 0 2px 6px -2px rgba(var(--c-900-rgb), 0.25);
  color: var(--c-700);
}
.lock-text {
  margin: 2px 0 0;
  font: 800 var(--fs-section)/1.4 var(--font);
  color: var(--ink);
  text-align: center;
}
.lock-text b {
  margin: 0 2px;
  font: 800 26px/1 var(--font-latin);
  color: var(--c-700);
}
.lock-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: min(380px, 100%);
  padding: 12px 16px 14px;
  box-sizing: border-box;
  border-radius: var(--radius-m);
  background: var(--c-100);
}
.lock-meta {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  font: 800 var(--fs-number)/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink-2);
}
.lock-meta b {
  font-size: 20px;
  color: var(--ink);
}
.lock-meta em {
  font-style: normal;
  color: var(--c-700);
}
.lock-card .ui-bar {
  height: 10px;
  border-radius: 5px;
}
.lock-card .ui-bar > i {
  background: linear-gradient(90deg, var(--c-400), var(--c-500) 70%, var(--c-600));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.4);
}
.calm .lock-card .ui-bar > i {
  transition: none;
}

@container panel (max-height: 640px) {
  .park-page {
    padding: 20px 18px 12px 14px;
  }
  .lock {
    gap: 12px;
    padding-block: 18px 22px;
  }
  .lock-medallion {
    width: 132px;
    height: 132px;
  }
}
@container panel (max-height: 560px) {
  .park-page {
    padding-top: 10px;
  }
  .lock {
    gap: 10px;
    padding-block: 12px 16px;
  }
  .lock-medallion {
    width: 112px;
    height: 112px;
  }
  .lock-medallion :deep(.park-coin) {
    --size: 86px !important;
  }
}
@container panel (max-width: 680px) {
  .park-page {
    padding: 10px 12px 10px 10px;
  }
}
</style>
