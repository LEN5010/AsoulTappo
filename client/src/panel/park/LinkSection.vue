<script setup lang="ts">
// The park's tile matching (docs/design/park-link.md): 阿草 keeps the stall from the park's coral band (band.ts: its
// face, the time left in a game, and the prizes behind the info key). Between games the day's levels lie in a row,
// the ones played showing their prize and how much was cleared, the next one raised; the bottom bar starts it for
// its shard price. In a game the board fills the sheet (LinkBoard) and the bottom bar shows the pairs cleared, the
// prize they are worth so far, the hints left and the end key. The game lives in stores/parkLink.ts: pairs are taken
// off locally at once and their moves go to the server in order. When a game is settled its result shows over the
// board; a result not seen yet shows again when the panel opens.
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from "vue";
import * as sfx from "../../audio/sfx";
import { assetUrl } from "../../asset";
import { emoteCover, getEmote } from "../../manifest";
import { economy } from "../../stores/economy";
import { online, shards } from "../../stores/player";
import {
  dismissResult, finishLink, linkError, linkFinishing, linkGame, linkHintsLeft, linkPlaying, linkResult, linkShownResult,
  linkShuffling, linkStarting, linkState, linkSyncing, linkTiles, loadLink, playPair, serverNow, showResult, startLink, takeHint,
} from "../../stores/parkLink";
import { reducedMotion } from "../../stores/theme";
import { ACHAO } from "../../ui/achao";
import Icon from "../../ui/Icon.vue";
import { flashHost, parkTab, useBand } from "./band";
import { countTo } from "./countTo";
import { EMPTY, connect } from "./link";
import LinkBoard, { type LinkGhost, type LinkLine } from "./LinkBoard.vue";
import LinkPrizes from "./LinkPrizes.vue";
import LinkResultCard from "./LinkResultCard.vue";
import { raceClock } from "./raceFeed";

/** The link and the pair it took stay on the board this long (LinkBoard runs them). */
const LINE_MS = 340;
/** The end key waits this long for its second press. */
const ARM_MS = 2500;
const REACT_MS = 1800;
/** Tiles keep this pitch at least (some 30 pixels a tile); the floor keeps room for the board at it. */
const MIN_PITCH = 32;
const fmt = (n: number) => n.toLocaleString("en-US");

const calm = computed(() => reducedMotion.value);
const cfg = computed(() => economy.value?.park?.link ?? null);
const levels = computed(() => cfg.value?.levels ?? []);
const entry = computed(() => cfg.value?.entry ?? 0);

const game = linkGame;
const state = linkState;
const result = linkShownResult;
/** The level of the game on the board. */
const level = computed(() => (game.value ? levels.value[game.value.level - 1] ?? null : null));
const prizeOf = (max: number, cleared: number, total: number) => (total ? Math.floor((max * cleared * cleared) / (total * total)) : 0);
/** The prize the pairs cleared so far are worth. */
const prizeNow = computed(() => {
  const g = game.value;
  return g ? prizeOf(g.max ?? level.value?.max ?? 0, g.cleared, g.total) : 0;
});
const progress = computed(() => (game.value?.total ? (game.value.cleared / game.value.total) * 100 : 0));

// ---- the page is shown: kept alive and its booth picked
const active = ref(false);
const visible = computed(() => active.value && parkTab.value === "link");

// ---- the clock: the server's time, ticking while a game has time left. The store ends the game when it runs out.
const now = ref(serverNow());
let tick: ReturnType<typeof setInterval> | undefined;
function stopTick() {
  clearInterval(tick);
  tick = undefined;
}
watch(() => [linkPlaying.value, game.value?.deadline] as const, ([on, deadline]) => {
  stopTick();
  now.value = serverNow();
  if (!on || !deadline || deadline <= now.value) return;
  tick = setInterval(() => {
    now.value = serverNow();
    if (now.value >= deadline) stopTick();
  }, 200);
}, { immediate: true });
const leftMs = computed(() => (game.value ? game.value.deadline - now.value : 0));
const timeUp = computed(() => linkPlaying.value && leftMs.value <= 0);

/** The board takes a press. */
const canPlay = computed(() => linkPlaying.value && !timeUp.value && !linkShuffling.value && !linkFinishing.value && !linkSyncing.value);

// ---- 阿草 and the band
const done = computed(() => !!state.value && state.value.played >= state.value.levels);
const short = computed(() => shards.value < entry.value);
const hostFace = computed(() => {
  if (linkPlaying.value) return linkShuffling.value ? "流汗" : "观察";
  if (done.value) return "晚安";
  return short.value ? "拒绝" : "招商";
});
const clockText = computed(() => raceClock(Math.max(0, leftMs.value) / 1000));
const prizes = ref(false);
useBand("link", () => ({
  host: ACHAO[hostFace.value],
  timer: linkPlaying.value ? { label: "剩余", time: clockText.value } : undefined,
  info: { label: "奖励", open: () => (prizes.value = true) },
}));

// ---- tiles
const faces = computed(() => game.value?.kinds.map((k) => assetUrl(emoteCover(k))) ?? []);
const names = computed(() => game.value?.kinds.map((k) => getEmote(k)?.name ?? "") ?? []);
/** The tile picked first, by its id. */
const selected = ref<number | null>(null);
/** The pair a hint points at, by tile id. */
const hint = ref<number[]>([]);
const lines = ref<LinkLine[]>([]);
const ghosts = ref<LinkGhost[]>([]);
const shake = ref<number | null>(null);
/** Counts the shuffles that came in while in sight: each turns the tiles over (LinkBoard). */
const flips = ref(0);
let lineKey = 0;
let timers: ReturnType<typeof setTimeout>[] = [];
function later(ms: number, fn: () => void) {
  const t = setTimeout(() => {
    timers = timers.filter((x) => x !== t);
    fn();
  }, ms);
  timers.push(t);
}

function pick(id: number) {
  const g = game.value;
  if (!g || !canPlay.value) return;
  const at = linkTiles.value.indexOf(id);
  if (at < 0 || g.board[at] === EMPTY) return;
  const first = selected.value;
  if (first === null || first === id) {
    selected.value = first === id ? null : id;
    return;
  }
  const from = linkTiles.value.indexOf(first);
  const path = from >= 0 && g.board[from] === g.board[at] ? connect(g.board, g.rows, g.cols, from, at) : null;
  if (!path) {
    if (!calm.value) {
      shake.value = first;
      later(340, () => { if (shake.value === first) shake.value = null; });
    }
    selected.value = id;
    return;
  }
  const kind = g.board[at]!;
  selected.value = null;
  hint.value = [];
  if (!playPair(from, at)) return;
  sfx.cardSlide();
  const key = ++lineKey;
  lines.value = [...lines.value, { key, points: path }];
  if (!calm.value) ghosts.value = [...ghosts.value, { id: first, kind, at: from }, { id, kind, at }];
  later(LINE_MS, () => {
    lines.value = lines.value.filter((l) => l.key !== key);
    ghosts.value = ghosts.value.filter((x) => x.id !== first && x.id !== id);
  });
}

function showHint() {
  if (!canPlay.value) return;
  const pair = takeHint();
  if (!pair) return;
  hint.value = pair.map((i) => linkTiles.value[i]!);
  selected.value = null;
}
// A hint's tiles gone (a resync, a shuffle): the hint goes too.
watch(linkTiles, (tiles) => {
  if (hint.value.length && !hint.value.every((id) => tiles.includes(id))) hint.value = [];
  if (selected.value !== null && !tiles.includes(selected.value)) selected.value = null;
});
watch(linkShuffling, (on, was) => {
  if (on) {
    selected.value = null;
    hint.value = [];
  } else if (was && linkPlaying.value) {
    hint.value = [];
    if (!visible.value) return;
    sfx.flip(true);
    flips.value++;
  }
});

// ---- the end key: a second press within ARM_MS ends the game
const armed = ref(false);
let armTimer: ReturnType<typeof setTimeout> | undefined;
function pressEnd() {
  if (!linkPlaying.value || linkFinishing.value) return;
  if (!armed.value) {
    armed.value = true;
    clearTimeout(armTimer);
    armTimer = setTimeout(() => (armed.value = false), ARM_MS);
    return;
  }
  armed.value = false;
  clearTimeout(armTimer);
  void finishLink();
}
watch(linkPlaying, (on) => {
  if (!on) armed.value = false;
});

// ---- the prize badge counts up as pairs go
const badge = ref(prizeNow.value);
let stopBadge = () => {};
const bump = ref(false);
watch(prizeNow, (to, from) => {
  stopBadge();
  if (calm.value || to < from) {
    badge.value = to;
    return;
  }
  stopBadge = countTo(badge, to, 360);
  if (to > from) {
    bump.value = false;
    requestAnimationFrame(() => (bump.value = true));
  }
});

// ---- the result
/** A game settled while on the board and in sight: 阿草 reacts. */
watch(linkResult, (r, was) => {
  if (!r || was) return;
  selected.value = null;
  hint.value = [];
  if (!visible.value || !game.value) return;
  const face = r.reason === "clear" ? "欢呼" : r.prize >= entry.value ? "打call" : r.prize > 0 ? "肯定" : "安慰";
  if (ACHAO[face]) flashHost(ACHAO[face], REACT_MS);
  if (r.reason === "clear") sfx.pageTurn();
  else sfx.flip();
});

// ---- between games: the day's levels
const slots = computed(() => {
  const s = state.value;
  const today = s?.today ?? [];
  const played = s?.played ?? 0;
  return levels.value.map((l, i) => {
    const r = today[i];
    const pct = r?.total ? Math.floor((r.cleared * 100) / r.total) : 0;
    return { n: i + 1, max: l.max, result: r ?? null, pct, kind: r ? "done" : i === played ? "next" : "later" };
  });
});
const nextLevel = computed(() => (state.value && !done.value ? levels.value[state.value.played] ?? null : null));
/** Why a game cannot start: a short reason, "" while there is nothing to say (loading, starting), null when it can. */
const blocked = computed<string | null>(() => {
  if (!online.value) return "未连接";
  if (!state.value || linkStarting.value) return "";
  if (done.value) return "明天再来";
  if (short.value) return "碎片不足";
  return null;
});

async function start() {
  if (blocked.value !== null) return;
  selected.value = null;
  hint.value = [];
  lines.value = [];
  ghosts.value = [];
  if (await startLink()) sfx.flip();
}

// A result first in sight is marked seen; it stays until closed.
watch(() => [visible.value, linkShownResult.value] as const, ([shown, r]) => {
  if (shown && r) showResult(r);
}, { immediate: true });

// ---- the page comes and goes; another save or server is followed by the store. Between games the park page's
// regular reload reads this page's state, with the park in it (ParkPage, refreshLink).
function enter() {
  if (active.value) return;
  active.value = true;
  sfx.prime();
  void loadLink();
}
// A server that turned the link off is asked again only when the page comes back or its economy changes.
watch(() => JSON.stringify(cfg.value), (key, was) => {
  if (active.value && cfg.value && key !== was) void loadLink();
});
onMounted(enter);
onActivated(enter);
onDeactivated(() => (active.value = false));
onBeforeUnmount(() => {
  active.value = false;
  stopTick();
  clearTimeout(armTimer);
  timers.forEach(clearTimeout);
  timers = [];
  stopBadge();
});
watch(linkState, (s) => {
  if (s) return;
  selected.value = null;
  hint.value = [];
});
</script>

<template>
  <section class="link" :class="{ calm }" aria-label="连连看">
    <div class="floor" :style="game ? { minHeight: `${(game.rows + 1) * MIN_PITCH}px` } : undefined">
      <!-- A game on the board, in play or settled. -->
      <template v-if="game">
        <LinkBoard
          :rows="game.rows" :cols="game.cols" :board="game.board" :tiles="linkTiles" :faces="faces" :names="names"
          :selected="selected" :min-pitch="MIN_PITCH" :hint="hint" :lines="lines" :ghosts="ghosts" :shake="shake" :deal="game.id" :flip="flips"
          :dim="!!linkResult || linkShuffling || timeUp" :disabled="!canPlay" :calm="calm" @pick="pick"
        />
        <p v-if="linkShuffling && linkPlaying" class="veil" role="status">
          <Icon name="refresh" :size="22" class="spin" /><b>洗牌中</b>
        </p>
        <div v-if="result" class="over">
          <LinkResultCard :key="result.id" :result="result" :calm="calm" @close="dismissResult" />
        </div>
      </template>

      <!-- Between games: the result not seen yet (or a fan of tiles), over the day's levels. -->
      <div v-else class="levels" data-rise>
        <LinkResultCard v-if="result" :key="result.id" :result="result" :calm="calm" @close="dismissResult" />
        <div v-else class="fan" aria-hidden="true">
          <span v-for="(face, i) in ['比心', '打call', '欢呼']" :key="face" class="fan-tile" :style="{ '--i': i - 1 }">
            <img :src="ACHAO[face]" alt="" draggable="false" />
          </span>
        </div>
        <ol class="slots">
          <li v-for="s in slots" :key="s.n" class="slot" :class="[s.kind, { clear: s.result?.reason === 'clear' }]">
            <span class="slot-no">{{ s.n }}</span>
            <template v-if="s.result">
              <span class="slot-prize"><Icon name="shard" :size="15" /><b>{{ fmt(s.result.prize) }}</b></span>
              <span class="slot-bar" :title="`${s.result.cleared} / ${s.result.total}`"><i :style="{ width: `${s.pct}%` }"></i></span>
            </template>
            <span v-else class="slot-max"><Icon name="shard" :size="14" />{{ fmt(s.max) }}</span>
          </li>
        </ol>
      </div>

    </div>

    <LinkPrizes v-if="prizes" :levels="levels" :played="state?.played ?? 0" @close="prizes = false" />

    <div class="park-actions">
      <!-- In play: the pairs cleared and what they are worth, the hints left, the end key. -->
      <template v-if="linkPlaying && game">
        <div class="progress" role="progressbar" :aria-valuenow="game.cleared" :aria-valuemin="0" :aria-valuemax="game.total">
          <span class="count"><b>{{ game.cleared }}</b>/{{ game.total }}</span>
          <div class="ui-bar"><i :style="{ width: `${progress}%` }"></i></div>
          <span class="badge" :class="{ bump, top: game.cleared === game.total }" @animationend="bump = false">
            <Icon name="shard" :size="16" /><b>{{ fmt(badge) }}</b>
          </span>
        </div>
        <div class="park-actions-main">
          <button
            type="button" class="ui-btn ghost hint-key" aria-label="提示" :disabled="!canPlay || linkHintsLeft <= 0"
            @click="showHint"
          >
            <Icon name="spark" :size="16" /><b>{{ linkHintsLeft }}</b>
          </button>
          <button
            type="button" class="ui-btn end-key" :class="{ on: armed }" :disabled="linkFinishing" :aria-busy="linkFinishing"
            @click="pressEnd"
          >{{ armed ? "确认结束" : "结束" }}</button>
        </div>
      </template>

      <!-- Between games: the next level's top prize and time, and the start key. -->
      <template v-else>
        <p v-if="linkError" class="ui-error link-error" role="alert">{{ linkError }}</p>
        <span v-else-if="nextLevel" class="next-info">
          <span class="top"><small>最高</small><Icon name="shard" :size="18" /><b>{{ fmt(nextLevel.max) }}</b></span>
          <span class="time"><Icon name="clock" :size="16" /><b>{{ raceClock(nextLevel.seconds) }}</b></span>
        </span>
        <div class="park-actions-main">
          <span v-if="blocked" class="why">{{ blocked }}</span>
          <button
            type="button" class="ui-btn primary large start" :class="{ pulse: blocked === null && !result && !calm }"
            :disabled="blocked !== null" :aria-busy="linkStarting" :title="blocked || undefined"
            @keydown.space.prevent @keyup.space.prevent @click="start"
          >
            <span>开始</span>
            <small class="cost"><Icon name="shard" :size="15" />{{ fmt(entry) }}</small>
          </button>
        </div>
      </template>
    </div>
  </section>
</template>

<style scoped>
/* The stall, on the park's sheet under the coral band: the floor (board or levels), then the bottom bar. */
.link {
  display: flex;
  flex-direction: column;
}
/* The board measures this box (LinkBoard fills it from outside the flow): its size never depends on the board's. */
.floor {
  position: relative;
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 220px;
  margin: 4px 12px 6px;
}

/* ---- shuffling: a quiet veil over the dimmed board */
.veil {
  position: absolute;
  inset: 0;
  z-index: 4;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: 0;
  pointer-events: none;
  font: 800 var(--fs-section)/1 var(--font);
  color: var(--c-700);
}
.spin {
  animation: spin 900ms linear infinite;
}
@keyframes spin {
  to { rotate: 360deg; }
}

/* ---- between games: a fan of three tiles over the day's levels */
.levels {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 26px;
  padding: 8px 0;
}
.fan {
  position: relative;
  width: 200px;
  height: 92px;
}
.fan-tile {
  position: absolute;
  left: 50%;
  top: 6px;
  display: grid;
  place-items: center;
  width: 76px;
  height: 76px;
  border-radius: 16px;
  background: linear-gradient(180deg, #fff 55%, var(--c-50));
  box-shadow: 0 0 0 1px rgba(var(--c-900-rgb), 0.05), 0 2px 3px rgba(var(--c-900-rgb), 0.12), 0 10px 18px -8px rgba(var(--c-900-rgb), 0.34);
  transform: translateX(calc(-50% + var(--i) * 62px)) translateY(calc(var(--i) * var(--i) * 8px)) rotate(calc(var(--i) * 12deg));
}
.fan-tile:nth-child(2) {
  z-index: 1;
}
.fan-tile img {
  width: 84%;
  height: 84%;
  object-fit: contain;
}

.slots {
  display: flex;
  gap: 12px;
  margin: 0;
  padding: 0 16px;
  list-style: none;
}
/* A level is a card on the sheet: played ones white with their prize, the next one raised with a coral ring. */
.slot {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  width: 104px;
  height: 118px;
  box-sizing: border-box;
  padding: 10px 10px 12px;
  border-radius: var(--radius-m);
  background: var(--c-100);
  color: var(--ink-3);
}
.slot-no {
  font: 800 34px/1 var(--font-latin);
  color: var(--c-300);
}
.slot-max {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font: 800 var(--fs-number)/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
}
.slot.done {
  background: var(--surface);
  box-shadow: 0 0 0 1px rgba(var(--c-900-rgb), 0.05), 0 1px 2px rgba(var(--c-900-rgb), 0.1), 0 6px 12px -8px rgba(var(--c-900-rgb), 0.3);
}
.slot.done .slot-no {
  font-size: 22px;
  color: var(--ink-3);
}
.slot-prize {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  color: var(--c-600);
}
.slot-prize b {
  font: 800 24px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}
.slot-bar {
  width: 100%;
  height: 6px;
  border-radius: 3px;
  background: var(--c-100);
  overflow: hidden;
}
.slot-bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--c-400), var(--c-500));
  transform-origin: left center;
  animation: bar-fill 700ms var(--ease-out) 120ms both;
}
@keyframes bar-fill {
  from { transform: scaleX(0); }
}
.slot.clear {
  box-shadow: inset 0 0 0 2px var(--gold), 0 6px 12px -8px rgba(var(--gold-rgb), 0.6);
  background: linear-gradient(180deg, #FFFBF1, var(--gold-soft));
}
.slot.clear .slot-bar i {
  background: var(--grad-gold);
}
.slot.next {
  background: var(--surface);
  color: var(--ink-2);
  box-shadow: 0 0 0 3px var(--c-500), 0 10px 18px -8px rgba(var(--c-500-rgb), 0.7);
  transform: translateY(-4px);
}
.slot.next .slot-no {
  color: var(--c-700);
}
.slot.next .slot-max svg {
  color: var(--c-600);
}

.over {
  position: absolute;
  inset: 0;
  z-index: 5;
  display: grid;
  place-items: center;
}

/* ---- the bottom bar */
.link-error {
  min-width: 0;
  margin: 0;
}
.progress {
  flex: 1;
  min-width: 200px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.count {
  font: 800 var(--fs-number)/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink-2);
  white-space: nowrap;
}
.count b {
  font-size: 22px;
  color: var(--ink);
}
.progress .ui-bar {
  flex: 1;
  height: 10px;
  border-radius: 5px;
}
.progress .ui-bar > i {
  transition: width var(--dur-base) var(--ease-out);
}
/* The prize so far, at the bar's tail. */
.badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  min-width: 64px;
  height: 32px;
  padding: 0 10px 0 8px;
  box-sizing: border-box;
  border-radius: 999px;
  background: var(--surface);
  box-shadow: 0 0 0 2px var(--c-300), 0 2px 6px -2px rgba(var(--c-900-rgb), 0.25);
  color: var(--c-600);
}
.badge b {
  font: 800 20px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}
.badge.top {
  box-shadow: 0 0 0 2px var(--gold), 0 2px 8px -2px rgba(var(--gold-rgb), 0.6);
}
.badge.bump {
  animation: bump 320ms var(--ease-spring);
}
@keyframes bump {
  40% { scale: 1.12; }
}
.hint-key {
  gap: 4px;
  min-width: 64px;
  padding: 0 12px;
}
.hint-key svg {
  color: var(--c-600);
}
.hint-key b {
  font: 800 var(--fs-number)/1 var(--font-latin);
}
.end-key {
  min-width: 96px;
}

.next-info {
  display: inline-flex;
  align-items: center;
  gap: 18px;
}
.top,
.time {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.top small {
  margin-right: 4px;
  font: 700 var(--fs-label)/1 var(--font);
  color: var(--ink-2);
}
.top svg,
.time svg {
  color: var(--c-600);
}
.top b {
  font: 800 26px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}
.time b {
  font: 800 20px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink-2);
}
.why {
  font: 700 var(--fs-body)/1.3 var(--font);
  color: var(--ink-2);
}
.start {
  min-width: 176px;
}
.cost {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin-left: 6px;
  font: 800 var(--fs-number)/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
}

.calm .spin,
.calm .badge.bump,
.calm .slot-bar i {
  animation: none;
}
.calm .progress .ui-bar > i {
  transition: none;
}

@container panel (max-height: 640px) {
  .levels {
    gap: 18px;
  }
  .fan {
    height: 76px;
    scale: 0.85;
  }
  .slot {
    height: 104px;
  }
}
@container panel (max-height: 560px) {
  .floor {
    min-height: 200px;
    margin-block: 2px 4px;
  }
  .levels {
    gap: 10px;
  }
  .fan {
    display: none;
  }
  .start {
    height: 40px;
  }
}
@container panel (max-width: 680px) {
  .slots {
    gap: 8px;
  }
  .slot {
    width: 84px;
    height: 100px;
  }
  .slot-prize b {
    font-size: 20px;
  }
  .progress {
    min-width: 0;
  }
  .start {
    min-width: 140px;
  }
}
</style>
