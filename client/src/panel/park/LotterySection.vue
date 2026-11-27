<script setup lang="ts">
// 每日夺宝 (protocol/PROTOCOL.md 每日夺宝), laid out like a lottery's
// draw broadcast: on the left the draw machine (a globe with a ring of the ten numbered balls over a coral cabinet with
// the three number keys in its windows) and the tray of my stubs of the day under it; on the right the pool (the top prize, server-wide,
// which rolls over until a draw has a top winner, with the second and the third under it) and the board of the latest
// draws (day, number, top prize winners, the top prize). The bottom bar has my result of the draw on the table and the
// buy keys; 往期 there opens the full list with what I won each day, and the last draw's stubs once today has its
// own. There is no push: while the page is open the state loads every POLL_MS, and every few seconds once the close
// or the draw is due. The countdown and 阿草 go up in the park's coral band (band.ts).
// The number keys double as reels: 机选 spins them onto the number bought, and a draw's first showing spins them onto
// the drawn number, one digit at a time from the right, while the ring of balls turns and each digit's ball drops onto
// its key.
import { computed, nextTick, onBeforeUnmount, ref, useId, watch } from "vue";
import { usePageActive } from "../../composables/usePageActive";
import { economy } from "../../stores/economy";
import { online, status } from "../../stores/player";
import { park, parkTry } from "../../stores/park";
import { reducedMotion } from "../../stores/theme";
import { ACHAO } from "../../ui/achao";
import Icon from "../../ui/Icon.vue";
import { EASE_IN_OUT, EASE_OUT } from "../../ui/motion";
import { useBand } from "./band";
import { Drum } from "./lotteryDrum";
import { COIN_SMALL } from "./coin";
import {
  cleanNumber, drawLabel, dropDigit, markDrawSeen, NO_PICKS, pickedNumber, pickLabel, pickTarget, putDigit,
  revealDigits, seenDraw, shortDay, stepDigit, type LotteryBuy, type LotteryTier, type Picks,
} from "./lottery";
import LotteryBoard from "./LotteryBoard.vue";
import { createPlays } from "./lotteryPlays";
import LotteryPrizes from "./LotteryPrizes.vue";
import { useReels } from "./lotteryReels";
import { useDrawReveal } from "./lotteryReveal";
import { onKeys, spotOf, type Spot } from "./lotterySpots";
import { useLotteryState } from "./lotteryState";
import TicketStub from "./TicketStub.vue";

/** A key pressed by typing stays down this long. */
const PRESS_MS = 140;
/** Wheel travel (px) per digit step. */
const WHEEL_STEP = 40;
/** 机选: once the keys have stopped (lotteryReels.ts), the number rests this long on them. */
const BUY_HOLD_MS = 240;
/** A drawn ball runs down the tube and along the track in ROLL_S plus ROLL_S_PER_PX a px, speeding up then slowing;
 * drops into its window in BALL_DROP_S and squashes and springs back there in BALL_SQUASH_S. With no globe shown it
 * just appears after BALL_DROP_MS. */
const ROLL_S = 0.16;
const ROLL_S_PER_PX = 1 / 620;
const BALL_DROP_S = 0.22;
const BALL_SQUASH_S = 0.26;
const BALL_DROP_MS = 300;
/** The number's flight from the keys into its stub; the other stubs bought with it follow this far apart. */
const FLY_MS = 560;
const DROP_MS = 480;
const DROP_STAGGER_MS = 70;
const fmt = (n: number) => n.toLocaleString("en-US");

const {
  state, loadError, now, load, startClock, stopClock, clockRunning, drawTime, left, waiting, closed,
  last, winning, drawnHere, lastName, lastOnTable, table, tableDay, showCount, slots, past, lastAside, hasPast,
} = useLotteryState();
const plays = createPlays();
const calm = computed(() => reducedMotion.value);
/** The page is shown: the clock runs and a new draw may play its reveal. */
const active = ref(false);
/** The pop-up open over the bottom bar. */
const pop = ref<"" | "past">("");
const rootEl = ref<HTMLElement>();

// ---- the clock (lotteryState.ts) and the page's own keys run while the page is shown
const pageActive = usePageActive();
function start() {
  if (active.value) return;
  active.value = true;
  window.addEventListener("keydown", onPageKey, true);
  startClock();
}
function stop() {
  if (!active.value) return;
  active.value = false;
  window.removeEventListener("keydown", onPageKey, true);
  stopClock();
  pop.value = "";
  settle();
}
// The page is kept alive: mounting, returning, or unhiding the panel starts the clock; hiding or deactivating stops it.
watch(pageActive, (on) => (on ? start() : stop()), { immediate: true });
onBeforeUnmount(() => {
  stop();
  pressTimers.forEach(clearTimeout);
});
// Another save: its numbers.
watch(() => status.value?.player, (player, was) => {
  if (player === was) return;
  settle();
  state.value = null;
  fresh.value = [];
  picks.value = NO_PICKS;
  at.value = null;
  pop.value = "";
  if (clockRunning()) void load();
});

// ---- the next draw
useBand("lottery", () => {
  const s = state.value;
  const label = waiting.value ? "开奖中" : drawLabel(drawTime.value, now.value);
  return { host: ACHAO["观察"], timer: s ? { label, time: waiting.value ? undefined : left.value } : undefined };
});

// ---- buying
const coins = computed(() => park.value?.coins ?? status.value?.park?.coins ?? 0);
const busy = ref<"pick" | "random" | "">("");
const buyError = ref("");
/** Indexes of the tickets just bought, for their flight from the keys. */
const fresh = ref<number[]>([]);
/** The stubs just bought stay unseen until their flight takes them. */
const held = ref(false);

/** Why [n] tickets cannot be bought now: a short reason, "" when none is worth showing, null when they can. */
function blocked(n: number): string | null {
  if (!online.value) return "未连接";
  const s = state.value;
  if (!s || busy.value || reveal.value) return "";
  if (closed.value) return "已停售";
  if (s.left === 0) return "今日已买满";
  if (n > s.left) return "";
  if (coins.value < n) return "驼币不足";
  return null;
}

// ---- the number keys: a digit or blank each; a key clicked is the one the next digit changes
const picks = ref<Picks>(NO_PICKS);
const at = ref<number | null>(null);
const pressed = ref([false, false, false]);
/** The hidden field under the keys has the keyboard. */
const typing = ref(false);
const field = ref<HTMLInputElement>();
const keysEl = ref<HTMLElement>();
const stubsEl = ref<HTMLElement>();
/** How the faces come onto the keys: a pop when picked, a fade when the keys go back after a spin, or at once. */
const faceIn = ref<"" | "fade" | "still">("");

const typed = computed(() => pickedNumber(picks.value) ?? "");
const pickFaces = computed(() => pickLabel(picks.value));
/** Today is drawn: the windows show the drawn number's balls and the keys are gone. */
const showDraw = computed(() => !!state.value?.drawn && drawnHere.value);
const faces = computed<readonly string[]>(() => (showDraw.value ? winning.value : picks.value));
/** Keys stay pressable while coins are short: picking is free, only the pick key waits. */
const keysOff = computed(() => !online.value || closed.value || state.value?.left === 0);
/** Something is playing on the keys or a number is being bought: the keys take no input. */
const locked = computed(() => !!busy.value || !!reeling.value || !!reveal.value);
/** The windows hold the draw's balls instead of the keys: while a draw plays, and once today is drawn. */
const drum = computed(() => !!reveal.value || showDraw.value);
/** Whether window [i] has its ball in: all three at rest, from the right one by one while a draw plays. */
const inSlot = (i: number) => !reveal.value || i >= 3 - stopped.value;
/** Where the caret shows: the key the next typed digit goes to, and the active column highlighted while picking. */
const activeCol = computed(() => (!drum.value && !keysOff.value && !locked.value ? pickTarget(picks.value, at.value) : null));
const target = computed(() => (typing.value ? activeCol.value : null));
const pickReady = computed(() => typed.value.length === 3 && blocked(1) === null);
const note = computed(() => buyError.value || blocked(1) || "");
const fieldLabel = computed(() => {
  const cur = pickFaces.value.join(" ");
  const pos = activeCol.value !== null ? `，第 ${activeCol.value + 1} 位` : "";
  return `号码 ${cur}${pos}`;
});

const pressTimers: ReturnType<typeof setTimeout>[] = [];
function press(i: number) {
  if (calm.value) return;
  pressed.value = pressed.value.map((p, j) => p || j === i);
  clearTimeout(pressTimers[i]);
  pressTimers[i] = setTimeout(() => (pressed.value = pressed.value.map((p, j) => p && j !== i)), PRESS_MS);
}
function put(d: string) {
  let col: number | null;
  let next: [string, string, string];
  if (at.value !== null) {
    col = at.value;
    next = [...picks.value];
    next[col] = d;
    at.value = col < 2 ? col + 1 : null;
  } else if (picks.value.every(Boolean)) {
    col = 0;
    next = [d, "", ""];
  } else {
    const r = putDigit(picks.value, null, d);
    if (r.key === null) return;
    col = r.key;
    next = [...r.picks];
  }
  faceIn.value = "";
  stepped.value = stepped.value.map((s, j) => (j === col ? 0 : s));
  picks.value = next;
  press(col);
  field.value?.focus({ preventScroll: true });
}
function backOne(mode: "back" | "del") {
  faceIn.value = "";
  const next: [string, string, string] = [...picks.value];
  if (mode === "del") {
    picks.value = dropDigit(picks.value, at.value);
    return;
  }
  if (at.value !== null) {
    if (next[at.value]) {
      next[at.value] = "";
      picks.value = next;
    } else if (at.value > 0) {
      const prev = at.value - 1;
      next[prev] = "";
      picks.value = next;
      at.value = prev;
    }
    return;
  }
  for (let i = 2; i >= 0; i--) {
    if (next[i]) {
      next[i] = "";
      picks.value = next;
      at.value = i;
      return;
    }
  }
}
/** Typed or pasted digits go onto the keys; the field itself stays empty. */
function onType(e: Event) {
  const input = e.target as HTMLInputElement;
  if (!keysOff.value && !locked.value) for (const d of cleanNumber(input.value)) put(d);
  input.value = "";
}
function onKey(e: KeyboardEvent) {
  if (e.isComposing || e.ctrlKey || e.metaKey || e.altKey) return;
  if (e.key === "Escape") {
    if (pop.value) {
      pop.value = "";
      e.stopPropagation();
    } else if (at.value !== null) {
      at.value = null;
      e.stopPropagation();
    } else if (!keysOff.value && !locked.value && picks.value.some(Boolean)) {
      faceIn.value = "";
      picks.value = NO_PICKS;
      e.stopPropagation();
    }
    return;
  }
  if (e.key === "Enter") {
    e.preventDefault();
    if (!e.repeat && !locked.value) buyPicked();
    return;
  }
  if (e.key === "r" || e.key === "R") {
    e.preventDefault();
    if (!e.repeat && !locked.value) buyRandom(1);
    return;
  }
  if (keysOff.value || locked.value) return;
  if (e.key === "Backspace" || e.key === "Delete") {
    e.preventDefault();
    backOne(e.key === "Backspace" ? "back" : "del");
    field.value?.focus({ preventScroll: true });
  } else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
    e.preventDefault();
    const fallback = e.key === "ArrowLeft" ? 2 : 0;
    const from = at.value ?? pickTarget(picks.value, null) ?? fallback;
    at.value = Math.min(2, Math.max(0, from + (e.key === "ArrowLeft" ? -1 : 1)));
    field.value?.focus({ preventScroll: true });
  } else if (e.key === "ArrowUp" || e.key === "ArrowDown") {
    e.preventDefault();
    const col = at.value ?? pickTarget(picks.value, null) ?? 0;
    at.value = col;
    step(col, e.key === "ArrowUp" ? 1 : -1);
    press(col);
    field.value?.focus({ preventScroll: true });
  }
}
/**
 * Keys typed anywhere on the shown page while picking is open go to the number keys, ahead of the panel's digit page
 * shortcuts (a window listener in the bubble phase). Editable fields keep their keys (the hidden field has its own
 * handler), a focused tab keeps its left/right arrows and a focused key its Enter; with picking closed or an overlay
 * open everything passes through.
 */
function onPageKey(e: KeyboardEvent) {
  if (e.isComposing || e.ctrlKey || e.metaKey || e.altKey) return;
  if (document.querySelector("[data-overlay]")) return;
  if (pop.value) {
    if (e.key === "Escape") {
      pop.value = "";
      e.stopImmediatePropagation();
      e.preventDefault();
    }
    return;
  }
  const s = state.value;
  if (!s || s.drawn || keysOff.value) return;
  const el = document.activeElement;
  if (el === field.value) return;
  const focused = (sel: string) => !!el?.closest?.(sel);
  if (focused("input, textarea, select, [contenteditable]")) return;
  const digit = /^[0-9]$/.test(e.key);
  const arrow = e.key.startsWith("Arrow");
  const rKey = e.key === "r" || e.key === "R";
  const back = e.key === "Backspace" || e.key === "Delete";
  if (!digit && !arrow && !rKey && !back && e.key !== "Enter" && e.key !== "Escape") return;
  if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && focused("[role=tab]")) return;
  if (e.key === "Enter" && focused("button, a, [role=button]")) return;
  if (e.key === "Escape" && at.value === null && !picks.value.some(Boolean)) return;
  e.stopImmediatePropagation();
  if (digit) {
    e.preventDefault();
    if (!locked.value) put(e.key);
  } else {
    onKey(e);
  }
}
/** The direction the last step went, per key: its new digit comes in from that side. */
const stepped = ref<number[]>([0, 0, 0]);
function step(i: number, by: 1 | -1) {
  const next: [string, string, string] = [...picks.value];
  next[i] = stepDigit(next[i]!, by);
  faceIn.value = "";
  stepped.value = stepped.value.map((s, j) => (j === i ? by : s));
  picks.value = next;
}
/** The small ▲/▼ keys on a number key's edges. */
function stepKey(i: number, by: 1 | -1) {
  if (keysOff.value || locked.value) return;
  step(i, by);
  field.value?.focus({ preventScroll: true });
}
function pickKey(i: number) {
  if (keysOff.value || locked.value) return;
  at.value = at.value === i ? null : i;
  field.value?.focus({ preventScroll: true });
}
let wheel = { key: -1, sum: 0 };
function onWheel(i: number, e: WheelEvent) {
  if (keysOff.value || locked.value) return;
  if (wheel.key !== i) wheel = { key: i, sum: 0 };
  wheel.sum += e.deltaY;
  if (Math.abs(wheel.sum) < WHEEL_STEP && Math.abs(e.deltaY) < WHEEL_STEP) return;
  step(i, wheel.sum < 0 ? 1 : -1);
  wheel.sum = 0;
}

// ---- what plays on the keys runs under one generation (plays, lotteryPlays.ts): settle() ends it all at once, on the
// state it was heading for.
const blowing = ref(false);
function settle() {
  plays.bump();
  if (reeling.value) endReels("still");
  haltGlobe();
  ghosts.value = [];
  held.value = false;
  resetReveal();
}

// ---- the reels on the number keys (lotteryReels.ts)
const { reeling, startReels, stopReels, endReels, reelSpots } = useReels({ plays, keysEl, faceIn, press, airOn, airOff });

// ---- the draw machine. The globe's balls are a live simulation (lotteryDrum.ts): at rest they lie where they fell;
// while the keys spin or a draw plays the air blows them about, and they collide and spin. One animation frame loop
// runs the simulation and the balls on their way out, writes every transform in one go and reads no layout; it stops
// once everything is still, and when the page is left. A drawn ball is pulled to the outlet on the globe's rim, runs
// down the tube and along the track (the tube's own SVG path), turning by the way it has come, drops into its window,
// squashes and springs back, and stays there; it is gone from the globe until the air next comes on. A digit drawn
// twice comes out again: the machine holds more than one ball of each number, as the real ones do. Everything is laid
// out from the rendered boxes when their size changes; with no globe shown (the smallest panel) the balls just appear
// in their windows.

const DIGITS = "0123456789".split("");
const odd = (d: string | undefined) => Number(d) % 2 === 1;

const machineEl = ref<HTMLElement>();
const uid = useId();
const tubeMask = `tube-${uid}`;
const boreMask = `bore-${uid}`;
const globeEl = ref<HTMLElement>();
const cabinetEl = ref<HTMLElement>();
const tubePathEl = ref<SVGPathElement>();
/** Cached `.gball` and `.drop` elements so the rAF loop never queries the DOM. */
const gballEls = new Map<string, HTMLElement>();
const dropEls = new Map<number, HTMLElement>();
function setBallEl(d: string, el: unknown) {
  if (el instanceof HTMLElement) gballEls.set(d, el);
  else gballEls.delete(d);
}
function setDropEl(id: number, el: unknown) {
  if (el instanceof HTMLElement) dropEls.set(id, el);
  else dropEls.delete(id);
}

/** Cached tube path arc-length & sample lookup table, rebuilt only when `tube.d` changes. */
interface TubePathCache { d: string; length: number; xs: Float32Array; ys: Float32Array; steps: number }
const TUBE_PATH_STEPS = 128;
let tubePathCache: TubePathCache | null = null;
function getTubePathCache(): TubePathCache | null {
  const d = tube.value?.d;
  const path = tubePathEl.value;
  if (!d || !path) return null;
  if (tubePathCache && tubePathCache.d === d) return tubePathCache;
  const length = path.getTotalLength();
  const steps = TUBE_PATH_STEPS;
  const xs = new Float32Array(steps + 1);
  const ys = new Float32Array(steps + 1);
  for (let i = 0; i <= steps; i++) {
    const pt = path.getPointAtLength((length * i) / steps);
    xs[i] = pt.x;
    ys[i] = pt.y;
  }
  tubePathCache = { d, length, xs, ys, steps };
  return tubePathCache;
}
function sampleTubePath(cache: TubePathCache, dist: number): Pt {
  if (cache.length <= 0) return { x: cache.xs[0]!, y: cache.ys[0]! };
  const clamped = Math.max(0, Math.min(dist, cache.length));
  const f = (clamped / cache.length) * cache.steps;
  const i = Math.min(cache.steps - 1, Math.floor(f));
  const u = f - i;
  return {
    x: cache.xs[i]! + (cache.xs[i + 1]! - cache.xs[i]!) * u,
    y: cache.ys[i]! + (cache.ys[i + 1]! - cache.ys[i]!) * u,
  };
}

/** The tube and the track, from the rendered machine: the path to draw and the points a ball runs through. */
interface Pt { x: number; y: number }
interface Tube {
  w: number; h: number; d: string; width: number; ball: number; exit: Pt; entry: Pt; end: number; y: number;
  /** Horizontal centres of the three cabinet windows, where drawn balls drop out of the track. */
  ports: number[];
  /** The globe's centre and inner radius, and the outlet's angle on its rim. */
  cx: number; cy: number; R: number; angle: number;
}
const tube = ref<Tube | null>(null);
function layoutTube() {
  const m = machineEl.value;
  const g = globeEl.value;
  const cab = cabinetEl.value;
  const cols = keysEl.value?.querySelectorAll<HTMLElement>(".key-col");
  if (!m || !g || !cab || !cols || cols.length < 3 || !g.offsetWidth) {
    tube.value = null;
    tubePathCache = null;
    // The globe is gone (a short panel): a ball on its way out leaves now, so its draw goes on without it.
    const sim = globeSim;
    globeSim = null;
    globeKey = "";
    if (sim?.pulling) {
      sim.release();
      wake();
    }
    return;
  }
  const mb = m.getBoundingClientRect();
  const gb = g.getBoundingClientRect();
  const cb = cab.getBoundingClientRect();
  const first = cols[0]!.getBoundingClientRect();
  const midCol = cols[1]!.getBoundingClientRect();
  const lastCol = cols[2]!.getBoundingClientRect();
  const ports = [first, midCol, lastCol].map((b) => b.left + b.width / 2 - mb.left);
  const ball = parseFloat(getComputedStyle(g).getPropertyValue("--ball")) || 26;
  const r = gb.width / 2;
  const cx = gb.left + r - mb.left;
  const cy = gb.top + r - mb.top;
  const y = cb.top - mb.top + parseFloat(getComputedStyle(cab).paddingTop) / 2;
  const left = first.left - mb.left + ball / 2;
  const right = lastCol.right - mb.left - ball / 2;
  // Over the cabinet the tube leaves the globe low on its right and comes down onto the track's right end; beside it,
  // it leaves high on the right and runs across onto the track's left end.
  const above = gb.bottom <= cb.top + 8;
  const angle = ((above ? 38 : -42) * Math.PI) / 180;
  const exit = { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
  const entry = above ? { x: right, y } : { x: left, y };
  const c1 = above ? { x: exit.x + 44, y: exit.y + 4 } : { x: exit.x + (left - exit.x) * 0.55, y: exit.y };
  const c2 = above ? { x: right, y: y - 38 } : { x: left - 26, y };
  const end = above ? left : right;
  const f = (p: Pt) => `${p.x.toFixed(1)} ${p.y.toFixed(1)}`;
  tube.value = {
    w: mb.width, h: mb.height, d: `M ${f(exit)} C ${f(c1)} ${f(c2)} ${f(entry)} H ${end.toFixed(1)}`,
    width: ball + 4, ball, exit, entry, end, y, ports, cx, cy, R: r - 2, angle,
  };
  fillGlobe(r - 2, ball / 2, angle);
}
const machineObserver = new ResizeObserver(() => layoutTube());
watch(machineEl, (el) => {
  machineObserver.disconnect();
  if (el) machineObserver.observe(el);
});
onBeforeUnmount(() => machineObserver.disconnect());

// The simulation and its frame loop.
let globeSim: Drum | null = null;
let globeKey = "";
let loopFrame = 0;
let loopAt = 0;
/** The digits in the globe now (the rest are out, in a window or on the way), and whether it has been filled. */
const present = ref<Record<string, boolean>>({});
const globeReady = ref(false);
/** The digits that sit out of the globe at rest: today's drawn ones, in their windows (not while their draw plays). */
const restOut = computed(() => (!reveal.value && showDraw.value ? [...new Set(winning.value)].sort().join("") : ""));

function syncPresent() {
  present.value = Object.fromEntries((globeSim?.balls ?? []).map((b) => [b.d, true]));
}
/** A new simulation for a globe of inner radius [R] and balls of radius [r], filled and fallen still. */
function fillGlobe(R: number, r: number, angle: number) {
  const key = [R, r, angle].map((n) => n.toFixed(2)).join("|");
  if (globeSim && key === globeKey) return;
  globeKey = key;
  const old = globeSim;
  globeSim = new Drum(R, r, angle);
  if (old && (old.pulling || old.airTarget > 0 || old.air > 0)) {
    // Resized while the air is on or a ball is on its way out: the new globe takes over the same balls, the air and
    // the pulls, so the draw goes on.
    old.handOver(globeSim);
    syncPresent();
    globeReady.value = true;
    wake();
    return;
  }
  for (const d of DIGITS) if (!restOut.value.includes(d)) globeSim.add(d);
  globeSim.settle();
  syncPresent();
  globeReady.value = true;
  void nextTick(paintFrame);
}
/** Puts back the balls that belong in the globe at rest and takes out the ones that do not; they fall in live. */
function restockGlobe() {
  const sim = globeSim;
  if (!sim) return;
  for (const d of DIGITS) {
    const want = !restOut.value.includes(d);
    if (want && !sim.has(d)) sim.add(d);
    if (!want && sim.has(d)) sim.remove(d);
  }
  syncPresent();
  if (calm.value || !active.value) {
    sim.settle();
    void nextTick(paintFrame);
  } else {
    wake();
  }
}

/** The air on: the balls out of the globe come back in first. */
function airOn() {
  const sim = globeSim;
  if (!sim || calm.value) return;
  for (const d of DIGITS) if (!sim.has(d)) sim.add(d);
  syncPresent();
  sim.airTarget = 1;
  blowing.value = true;
  wake();
}
function airOff() {
  blowing.value = false;
  if (!globeSim) return;
  globeSim.airTarget = 0;
  wake();
}
/** Everything stops where it should end up: the air off, the pile fallen still, no ball on its way. */
function haltGlobe() {
  blowing.value = false;
  cancelAnimationFrame(loopFrame);
  loopFrame = 0;
  runs = [];
  drops.value = [];
  const sim = globeSim;
  if (!sim) return;
  for (const d of DIGITS) {
    const want = !restOut.value.includes(d);
    if (want && !sim.has(d)) sim.add(d);
    if (!want && sim.has(d)) sim.remove(d);
  }
  sim.settle();
  syncPresent();
  void nextTick(paintFrame);
}
function wake() {
  if (loopFrame || calm.value || !active.value) return;
  loopAt = performance.now();
  loopFrame = requestAnimationFrame(loop);
}
function loop(now: number) {
  loopFrame = 0;
  const dt = Math.min(0.05, Math.max(0, (now - loopAt) / 1000));
  loopAt = now;
  globeSim?.update(dt);
  advanceRuns(now);
  paintFrame();
  if ((globeSim && !globeSim.settled) || runs.length) loopFrame = requestAnimationFrame(loop);
}
onBeforeUnmount(() => cancelAnimationFrame(loopFrame));

/** Writes every ball's transform: the globe's, then the ones on their way. */
function paintFrame() {
  if (globeSim) {
    for (const b of globeSim.balls) {
      const el = gballEls.get(b.d);
      if (el) el.style.transform = `translate(${b.x.toFixed(2)}px, ${b.y.toFixed(2)}px) rotate(${b.a.toFixed(3)}rad)`;
    }
  }
  for (const run of runs) if (run.el) run.el.style.transform = run.transform;
}

// The balls on their way out: pulled to the outlet by the simulation, then along the tube and into a window.
interface Drop { id: number; d: string; size: number }
const drops = ref<Drop[]>([]);
let dropId = 0;
interface Run {
  id: number;
  el: HTMLElement | null;
  /** When it left the globe (ms), where from (machine px), and its turn so far. */
  t0: number;
  from: Pt;
  a: number;
  /** The lead from the outlet into the tube, the way along the tube and the track to above the window, the window. */
  lead: number;
  way: number;
  slot: Pt;
  dur: number;
  /** The scale of the ball in the tube against its size in the window. */
  small: number;
  size: number;
  /** The way come so far, the x it was last at, and which way it turns. */
  s: number;
  px: number;
  dir: number;
  transform: string;
  done: () => void;
}
let runs: Run[] = [];

/** Draws the ball of [d] out of the globe into window [i]; [done] once it is in. */
function sendBall(i: number, d: string, done: () => void) {
  const t = tube.value;
  const sim = globeSim;
  const col = keysEl.value?.querySelectorAll<HTMLElement>(".key-col")[i];
  const pathCache = getTubePathCache();
  const m = machineEl.value;
  if (!t || !sim || !col || !pathCache || !m || calm.value) {
    plays.later(BALL_DROP_MS, done);
    return;
  }
  // Read now, while nothing moves: the window's centre and the size of its ball.
  const mb = m.getBoundingClientRect();
  const cb = col.getBoundingClientRect();
  const slot = { x: cb.left + cb.width / 2 - mb.left, y: cb.top + cb.height / 2 - mb.top };
  const size = parseFloat(getComputedStyle(col).getPropertyValue("--slot-ball")) || 64;
  const track = Math.abs(t.entry.x - t.end);
  const curve = pathCache.length - track;
  if (!sim.has(d)) sim.add(d);
  const g = plays.gen;
  sim.pull(d, (b) => {
    if (g !== plays.gen) return;
    syncPresent();
    // The globe may have been resized since the pull began: the ball leaves from where it is now.
    const now = tube.value ?? t;
    const from = { x: now.cx + b.x, y: now.cy + b.y };
    const lead = Math.hypot(now.exit.x - from.x, now.exit.y - from.y);
    const way = curve + Math.abs(t.entry.x - slot.x);
    const id = ++dropId;
    drops.value = [...drops.value, { id, d, size }];
    runs.push({
      id, el: null, t0: loopAt, from, a: b.a, lead, way, slot, dur: ROLL_S + (lead + way) * ROLL_S_PER_PX,
      small: t.ball / size, size, s: 0, px: from.x, dir: 1, transform: "", done,
    });
  });
  wake();
}

/** Moves each ball on its way to where it is at [now]; hands it to its window once it has settled there. */
function advanceRuns(now: number) {
  const t = tube.value;
  if (!runs.length) return;
  const pathCache = getTubePathCache();
  if (!t || !pathCache) {
    runs.forEach((r) => r.done());
    runs = [];
    drops.value = [];
    return;
  }
  const finished: Run[] = [];
  for (const run of runs) {
    run.el ??= dropEls.get(run.id) ?? null;
    const sec = (now - run.t0) / 1000;
    const r = t.ball / 2;
    let x: number;
    let y: number;
    let scale = run.small;
    let sx = 1;
    let sy = 1;
    if (sec < run.dur) {
      // Speeding up down the tube, slowing to a stop over the window.
      const u = sec / run.dur;
      const k = u < 0.5 ? 2 * u * u : 1 - 2 * (1 - u) * (1 - u);
      const s = (run.lead + run.way) * k;
      let p: Pt;
      if (s < run.lead) {
        const v = run.lead ? s / run.lead : 1;
        p = { x: run.from.x + (t.exit.x - run.from.x) * v, y: run.from.y + (t.exit.y - run.from.y) * v };
      } else {
        p = sampleTubePath(pathCache, s - run.lead);
      }
      // It rolls: turned by the way come, clockwise when going right.
      const dx = p.x - run.px;
      if (Math.abs(dx) > 0.05) run.dir = dx > 0 ? 1 : -1;
      run.px = p.x;
      run.a += (run.dir * (s - run.s)) / r;
      run.s = s;
      x = p.x;
      y = p.y;
    } else if (sec < run.dur + BALL_DROP_S) {
      // Falling into the window, growing to its full size and coming upright.
      const v = (sec - run.dur) / BALL_DROP_S;
      x = run.slot.x;
      y = t.y + (run.slot.y - t.y) * v * v;
      scale = run.small + (1 - run.small) * v;
      const upright = Math.round(run.a / (2 * Math.PI)) * 2 * Math.PI;
      run.a += (upright - run.a) * Math.min(1, v * 1.6);
    } else {
      // Landed: squashed, then a spring back.
      const w = Math.min(1, (sec - run.dur - BALL_DROP_S) / BALL_SQUASH_S);
      const k = 0.14 * Math.cos(Math.PI * 1.5 * w) * (1 - w);
      run.a = Math.round(run.a / (2 * Math.PI)) * 2 * Math.PI;
      x = run.slot.x;
      y = run.slot.y + (run.size * k) / 2;
      scale = 1;
      sx = 1 + k;
      sy = 1 - k;
      if (w >= 1) finished.push(run);
    }
    run.transform = `translate(${x.toFixed(2)}px, ${y.toFixed(2)}px) rotate(${run.a.toFixed(3)}rad) scale(${(scale * sx).toFixed(4)}, ${(scale * sy).toFixed(4)})`;
  }
  if (finished.length) {
    runs = runs.filter((r) => !finished.includes(r));
    const ids = new Set(finished.map((r) => r.id));
    drops.value = drops.value.filter((x) => !ids.has(x.id));
    finished.forEach((r) => r.done());
  }
}

// ---- a number bought leaves the keys: its digits fly into the new stub, which grows out of the keys around them
// (spots: lotterySpots.ts).
interface Ghost { id: number; d: string; x: number; y: number; size: number }
const ghosts = ref<Ghost[]>([]);
let ghostId = 0;
/** Where the digits picked are on the keys. */
function faceSpots(): Spot[] {
  const keys = keysEl.value ? Array.from(keysEl.value.querySelectorAll(".numkey")) : [];
  return onKeys(keysEl.value, keys.map((k, i) => spotOf(k.querySelector(".face"), picks.value[i] ?? "")));
}
function drop(el: HTMLElement, x: number, y: number, delay: number) {
  const to = el.getBoundingClientRect();
  const move = `translate(${x - (to.left + to.width / 2)}px, ${y - (to.top + to.height / 2)}px) scale(1.2)`;
  el.animate(
    [{ transform: move, opacity: 0 }, { opacity: 1, offset: 0.2 }, { transform: "none", opacity: 1 }],
    { duration: DROP_MS, delay, easing: EASE_OUT, fill: "backwards" },
  );
}
/** The digits at [spots] fly into the last stub just bought; the other new stubs drop from the keys after it. */
async function fly(spots: Spot[]) {
  const g = plays.gen;
  const root = rootEl.value;
  const stubs = Array.from(stubsEl.value?.querySelectorAll<HTMLElement>(".cell.fresh .ticket-stub") ?? []);
  const main = stubs[stubs.length - 1];
  // On a short panel the second rope can be under the bar: the body scrolls just far enough to show where it lands.
  const cell = main?.closest<HTMLElement>(".cell");
  if (cell) {
    cell.style.scrollMarginBottom = `${(barEl.value?.offsetHeight ?? 0) + 8}px`;
    cell.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "instant" });
  }
  const keys = keysEl.value?.getBoundingClientRect();
  if (!root || !keys || !main || spots.length !== 3) {
    held.value = false;
    return;
  }
  const from = spots.map((p) => ({ ...p, x: p.x + keys.left, y: p.y + keys.top }));
  const base = root.getBoundingClientRect();
  ghosts.value = from.map((p) => ({ id: ++ghostId, d: p.d, x: p.x - base.left, y: p.y - base.top, size: p.size }));
  await nextTick();
  if (g !== plays.gen) return;
  const kx = keys.left + keys.width / 2;
  const ky = keys.top + keys.height / 2;
  const opts = { duration: FLY_MS, easing: EASE_IN_OUT, fill: "backwards" as const };
  const digits = Array.from(main.querySelectorAll<HTMLElement>(".digit"));
  root.querySelectorAll<HTMLElement>(".flyer").forEach((el, j) => {
    const p = from[j]!;
    const to = spotOf(digits[j], "");
    if (!to) return;
    const end = `translate(calc(-50% + ${to.x - p.x}px), calc(-50% + ${to.y - p.y}px)) scale(${to.size / p.size})`;
    el.animate(
      [{ transform: "translate(-50%, -50%)", opacity: 1 }, { opacity: 1, offset: 0.82 }, { transform: end, opacity: 0 }],
      { ...opts, fill: "forwards" },
    );
  });
  const to = main.getBoundingClientRect();
  const grow = Math.min(2.4, keys.width / to.width);
  const move = `translate(${kx - (to.left + to.width / 2)}px, ${ky - (to.top + to.height / 2)}px) scale(${grow})`;
  main.animate([{ transform: move, opacity: 0 }, { opacity: 1, offset: 0.3 }, { transform: "none", opacity: 1 }], opts);
  digits.forEach((el) => el.animate([{ opacity: 0 }, { opacity: 0, offset: 0.82 }, { opacity: 1 }], opts));
  stubs.slice(0, -1).forEach((el, n) => drop(el, kx, ky, (n + 1) * DROP_STAGGER_MS));
  held.value = false;
  plays.later(FLY_MS, () => (ghosts.value = []));
}

async function buy(body: { numbers?: string[]; random?: number }, kind: "pick" | "random") {
  settle();
  const g = plays.gen;
  const base = picks.value;
  const spinning = kind === "random" && !calm.value;
  // A picked number leaves from the faces it is on: where they are, before the keys clear.
  const from = kind === "pick" && !calm.value ? faceSpots() : [];
  if (spinning) startReels(base);
  busy.value = kind;
  buyError.value = "";
  const r = await parkTry<LotteryBuy>("POST", "/api/park/lottery", body);
  busy.value = "";
  if (!r.ok) {
    buyError.value = r.error.message;
    // The reels come back to what the keys showed.
    if (spinning && g === plays.gen) stopReels(base, () => endReels("still"));
    return;
  }
  const s = r.data.lottery;
  const bought = r.data.bought;
  state.value = s;
  const first = s.tickets.length - bought.length;
  fresh.value = bought.map((_, i) => first + i);
  if (kind === "pick") {
    faceIn.value = "fade";
    picks.value = NO_PICKS;
    at.value = null;
  }
  if (calm.value || g !== plays.gen) return;
  held.value = true;
  await nextTick();
  if (g !== plays.gen) return;
  if (kind === "pick") {
    void fly(from);
    return;
  }
  // The keys show the last number bought.
  stopReels((bought[bought.length - 1] ?? "").split(""), () => plays.later(BUY_HOLD_MS, () => {
    const spots = reelSpots();
    endReels("fade");
    void fly(spots);
  }));
}
function buyPicked() {
  if (pickReady.value) void buy({ numbers: [typed.value] }, "pick");
}
function buyRandom(n: number) {
  if (blocked(n) === null) void buy({ random: n }, "random");
}
// A reason from the server holds until the state it was about changes.
watch(() => [state.value?.left, closed.value, coins.value, online.value], () => { if (!busy.value) buyError.value = ""; });
// Picking stops with the sales: no key held, no caret.
watch(keysOff, (off) => { if (off) at.value = null; });

// ---- the pool card (LotteryPrizes.vue). The top prize is the server-wide pool of the next draw (after today's draw,
// the pool it rolled over into or started again from). The park's state carries the same pool and loads again on
// every coin spent anywhere in the park, so the card takes it from there when it can and always matches the pool in
// the top bar.
const pool = computed(() => (state.value ? park.value?.jackpot ?? state.value.prize.top : null));
/** The second prize is what each ticket wins, as the third is; on servers before it, a share of the sales. */
const secondEach = computed(() => !!economy.value?.park?.lottery?.secondEach);

/** A ticket's digits, each marked when it is one of the trailing digits matched among the [stopped] at rest. */
function digits(number: string, tier: LotteryTier | null, stopped = 3) {
  const { lit } = revealDigits(tier, stopped);
  return number.split("").map((d, i) => ({ d, hit: lit[i]! }));
}

// ---- tray multipliers (倍投) & interactive stub picking
const hoverNum = ref("");
const stubMeta = computed(() => {
  const totals = new Map<string, number>();
  for (const t of table.value) totals.set(t.number, (totals.get(t.number) ?? 0) + 1);
  const seen = new Map<string, number>();
  return table.value.map((t) => {
    const rank = (seen.get(t.number) ?? 0) + 1;
    seen.set(t.number, rank);
    const total = totals.get(t.number) ?? 1;
    return { total, rank, latestMulti: total > 1 && rank === total };
  });
});
const samePickedCount = computed(() =>
  !lastOnTable.value && typed.value.length === 3
    ? (state.value?.tickets.filter((n) => n === typed.value).length ?? 0)
    : 0,
);
const echoNum = computed(() =>
  hoverNum.value || (!lastOnTable.value && typed.value.length === 3 ? typed.value : ""),
);
function stubTitle(num: string, total: number, rank: number): string {
  const multi = total > 1 ? ` · 共 ${total} 注（第 ${rank} 注）` : "";
  return `号码 ${num}${multi}`;
}
function loadStubNumber(num: string) {
  if (lastOnTable.value || keysOff.value || locked.value || num.length !== 3) return;
  faceIn.value = "";
  stepped.value = [0, 0, 0];
  picks.value = [num[0]!, num[1]!, num[2]!];
  at.value = null;
  [0, 1, 2].forEach(press);
  field.value?.focus({ preventScroll: true });
}
function focusEmptySlot() {
  if (lastOnTable.value || keysOff.value || locked.value) return;
  at.value = pickTarget(picks.value, null) ?? 0;
  field.value?.focus({ preventScroll: true });
}

/** Personal participation & shard winnings summary for the 往期 popover. */
const pastSummary = computed(() => {
  const hist = state.value?.history ?? [];
  if (!hist.length) return null;
  const hitsCount = hist.filter((h) => h.won > 0).length;
  const totalWon = hist.reduce((sum, h) => sum + h.won, 0);
  return { days: hist.length, hits: hitsCount, total: totalWon };
});

// ---- the first showing of a draw (lotteryReveal.ts); the watch that starts it is below, after everything it ends.
const { reveal, stopped, stamped, wonShown, startReveal, resetReveal } = useDrawReveal({
  plays, last, showDraw, faceIn, settle, layoutTube, airOn, airOff, sendBall,
});
watch(() => [active.value, last.value?.day ?? ""] as const, ([on, day]) => {
  if (!on || !day || seenDraw() === day) return;
  markDrawSeen(day);
  if (!calm.value) startReveal(day);
}, { immediate: true });
// The windows change between keys and balls: the track follows the keys' windows.
watch(drum, () => void nextTick(layoutTube));
// A new day puts its balls back in the globe; a drawn day keeps its drawn balls out.
watch(restOut, () => {
  if (!runs.length && !reveal.value) restockGlobe();
});
// The drawn number gives the keys back to a new day softly.
watch(showDraw, (on) => { if (!on && !reeling.value) faceIn.value = "fade"; });

// ---- the pop-up (pop, above): the earlier days, from the bar
const barEl = ref<HTMLElement>();
function toggle(p: "past") {
  pop.value = pop.value === p ? "" : p;
}
function onOutside(e: PointerEvent) {
  if (!barEl.value?.contains(e.target as Node)) pop.value = "";
}
watch(pop, (open) => {
  if (open) document.addEventListener("pointerdown", onOutside, true);
  else document.removeEventListener("pointerdown", onOutside, true);
});
onBeforeUnmount(() => document.removeEventListener("pointerdown", onOutside, true));
function onPopKey(e: KeyboardEvent) {
  if (e.key === "Escape" && pop.value) {
    pop.value = "";
    e.stopPropagation();
  }
}
</script>


<template>
  <section ref="rootEl" class="lottery" :class="{ calm, reveal: !!reveal, inactive: !pageActive }" aria-label="每日夺宝">
    <div class="stage" :class="{ empty: !state }">
      <p v-if="loadError" class="ui-error" role="alert">{{ loadError }}</p>

      <template v-if="state">
        <!-- The draw machine: the glass globe of numbered balls on its base, the tube from its rim to the track along
             the cabinet's top, and the three windows: the number keys, or the draw's balls. -->
        <div ref="machineEl" class="machine" :class="{ drum }">
          <!-- The tube is clear glass: a channel shadow, drop-port collars over the three windows, a bore-clipped line
               of light along its inside, its two walls and an outlet flange at the globe's rim. -->
          <svg v-if="tube" class="tube" :width="tube.w" :height="tube.h" aria-hidden="true">
            <defs>
              <mask :id="tubeMask" maskUnits="userSpaceOnUse" x="0" y="0" :width="tube.w" :height="tube.h">
                <path :d="tube.d" stroke="#fff" :stroke-width="tube.width + 3" />
                <path :d="tube.d" stroke="#000" :stroke-width="tube.width" />
              </mask>
              <mask :id="boreMask" maskUnits="userSpaceOnUse" x="0" y="0" :width="tube.w" :height="tube.h">
                <path :d="tube.d" stroke="#fff" :stroke-width="tube.width - 3" />
              </mask>
            </defs>
            <path class="tube-shadow" :d="tube.d" :stroke-width="tube.width + 4" transform="translate(0 2)" />
            <rect
              v-for="(px, pi) in tube.ports" :key="pi" class="tube-port"
              :x="px - tube.ball * 0.48" :y="tube.y + tube.width * 0.34"
              :width="tube.ball * 0.96" :height="6" rx="2.5"
            />
            <path class="tube-tint" :d="tube.d" :stroke-width="tube.width" />
            <path ref="tubePathEl" class="tube-glass" :d="tube.d" :stroke-width="tube.width" />
            <g :mask="`url(#${boreMask})`">
              <path class="tube-shine" :d="tube.d" :transform="`translate(-1.5 ${-tube.width * 0.3})`" />
            </g>
            <path class="tube-edge" :d="tube.d" :stroke-width="tube.width + 3" :mask="`url(#${tubeMask})`" />
            <circle class="tube-collar" :cx="tube.exit.x" :cy="tube.exit.y" :r="tube.width * 0.54" />
          </svg>
          <!-- The drawn balls on their way from the globe to their windows (placed by script). -->
          <i
            v-for="b in drops" :key="b.id" :ref="(el) => setDropEl(b.id, el)" class="drop lball" :class="{ odd: odd(b.d) }" :data-id="b.id" aria-hidden="true"
            :style="{ '--s': `${b.size}px` }"
          ><b>{{ b.d }}</b></i>
          <div class="stand" :class="{ blowing }" aria-hidden="true">
            <div ref="globeEl" class="globe" :class="{ ready: globeReady, blowing }">
              <i class="air-plume"></i>
              <i
                v-for="d in DIGITS" :key="d" :ref="(el) => setBallEl(d, el)" class="gball lball" :class="{ odd: odd(d), out: !present[d] }" :data-d="d"
              ><b>{{ d }}</b></i>
              <svg class="glass" viewBox="0 0 100 100">
                <path d="M14 45 A36 36 0 0 1 45 14" />
                <circle class="spark-dot" cx="54" cy="13.5" r="1.8" />
                <path class="far" d="M84 61 A36 36 0 0 1 67 83" />
              </svg>
            </div>
            <i class="base"></i>
          </div>
          <div ref="cabinetEl" class="cabinet">
            <!-- The keys take clicks, the wheel and their ▲/▼ keys; the keyboard goes to the hidden field under them. -->
            <div ref="keysEl" class="keys" :class="[faceIn, { drum }]">
              <div
                v-for="(d, i) in faces" :key="i" class="key-col"
                :class="{ filled: drum && inSlot(i), selected: !drum && at === i, active: !drum && at === null && activeCol === i }"
              >
                <span v-if="drum" class="socket">
                  <i v-if="inSlot(i)" class="lball slot-ball" :class="{ odd: odd(winning[i]), pop: !tube }"><b>{{ winning[i] }}</b></i>
                </span>
                <template v-else>
                  <button
                    type="button" class="ui-btn numkey" tabindex="-1" aria-hidden="true"
                    :class="{ on: at === i, down: pressed[i], target: target === i }"
                    :disabled="keysOff" :style="{ '--from': stepped[i]! > 0 ? '12px' : '-10px' }"
                    @mousedown.prevent @click="pickKey(i)" @wheel.prevent="onWheel(i, $event)"
                  >
                    <span v-if="reeling" class="reel"><span class="rc"></span><span class="rc"></span></span>
                    <template v-else>
                      <span v-if="d" :key="d" class="face">{{ d }}</span>
                      <i v-else-if="target !== i" class="blank"></i>
                      <i v-if="target === i" class="caret"></i>
                    </template>
                  </button>
                  <button
                    type="button" class="ui-btn step up" tabindex="-1" aria-hidden="true" :disabled="keysOff"
                    @mousedown.prevent @click.stop="stepKey(i, 1)"
                  ><Icon name="down" :size="14" /></button>
                  <button
                    type="button" class="ui-btn step down" tabindex="-1" aria-hidden="true" :disabled="keysOff"
                    @mousedown.prevent @click.stop="stepKey(i, -1)"
                  ><Icon name="down" :size="14" /></button>
                </template>
              </div>
              <input
                ref="field" class="field" type="text" inputmode="numeric" autocomplete="off"
                :aria-label="fieldLabel"
                aria-keyshortcuts="0 1 2 3 4 5 6 7 8 9 ArrowUp ArrowDown ArrowLeft ArrowRight Backspace Enter R"
                :disabled="keysOff" @input="onType" @keydown="onKey" @focus="typing = true" @blur="typing = false; at = null"
              />
            </div>
          </div>
        </div>

        <!-- The tray under the machine: my stubs in a fixed grid, an empty place for each still to buy, and the count. -->
        <div class="tray" :class="{ drawn: lastOnTable }">
          <ol ref="stubsEl" class="stubs" aria-label="我的号码">
            <li
              v-for="(t, i) in table" :key="`${tableDay}-${i}`" class="cell"
              :class="{
                fresh: fresh.includes(i), held: held && fresh.includes(i),
                out: lastOnTable && revealDigits(t.tier, stopped).out,
                'top-win': lastOnTable && stamped && t.tier === 'top',
                multi: stubMeta[i]!.total > 1,
                echo: echoNum === t.number && (stubMeta[i]!.total > 1 || typed === t.number),
                interactive: !lastOnTable && !keysOff && !locked,
              }"
              :title="stubTitle(t.number, stubMeta[i]!.total, stubMeta[i]!.rank)"
              @mouseenter="hoverNum = t.number" @mouseleave="hoverNum = ''"
              @click="loadStubNumber(t.number)"
            >
              <TicketStub size="s">
                <span
                  v-for="(c, j) in digits(t.number, t.tier, lastOnTable ? stopped : 3)" :key="j" class="digit"
                  :class="{ on: c.hit }"
                >{{ c.d }}</span>
              </TicketStub>
              <b v-if="t.prize && stamped" class="stamp" :class="{ top: t.tier === 'top' }">+{{ fmt(t.prize) }}</b>
              <b v-else-if="stubMeta[i]!.latestMulti" class="mult-tag">×{{ stubMeta[i]!.total }}</b>
              <small v-if="t.prize && stamped && stubMeta[i]!.total > 1 && stubMeta[i]!.latestMulti" class="mult-sub">×{{ stubMeta[i]!.total }}</small>
            </li>
            <li
              v-for="n in slots" :key="`slot-${n}`" class="slot"
              :class="{ ready: !lastOnTable && !keysOff && !locked }"
              aria-hidden="true" @click="focusEmptySlot"
            ></li>
          </ol>
          <span class="count"><template v-if="showCount"><b>{{ state.tickets.length }}</b>/{{ state.daily }}</template></span>
        </div>

        <!-- The pool and the board of the latest draws. -->
        <aside class="side" :class="{ only: !past.length }">
          <LotteryPrizes
            :pool="pool" :second="state.prize.second" :third="state.prize.third" :second-each="secondEach" :calm="calm"
          />
          <LotteryBoard :past="past" :reveal="reveal" :stopped="stopped" :calm="calm" />
        </aside>
      </template>
    </div>

    <!-- The digits of a number bought, on their way from the keys into its stub. -->
    <span
      v-for="g in ghosts" :key="g.id" class="flyer" aria-hidden="true"
      :style="{ left: `${g.x}px`, top: `${g.y}px`, fontSize: `${g.size}px` }"
    >{{ g.d }}</span>

    <div v-if="state" ref="barEl" class="park-actions" @keydown="onPopKey">
      <button
        v-if="hasPast" type="button" class="ui-btn small past-key" :class="{ aside: !!lastAside }" title="往期"
        aria-label="往期" :aria-expanded="pop === 'past'" @click="toggle('past')"
      >
        <Icon name="clock" :size="15" /><span>往期</span>
        <i v-if="lastAside" class="past-dot" aria-hidden="true"></i>
      </button>
      <!-- My result of the draw whose stubs are in the tray. -->
      <div v-if="last && lastOnTable && last.mine.length" class="last">
        <span class="when">{{ lastName }}</span>
        <span class="result" :class="{ won: last.won > 0, hide: !stamped, in: !!reveal && stamped }">
          <template v-if="last.won > 0"><Icon name="shard" :size="16" />+{{ fmt(reveal ? wonShown : last.won) }}</template>
          <template v-else>未中奖</template>
        </span>
      </div>

      <Transition :css="!calm" name="pop-up">
        <div v-if="pop === 'past'" class="pop past ui-scroll" role="dialog" aria-label="往期开奖">
          <div v-if="pastSummary" class="past-summary">
            <span class="past-stat">共 <b>{{ pastSummary.days }}</b> 期 · 中奖 <b>{{ pastSummary.hits }}</b> 次</span>
            <span class="past-total" :class="{ on: pastSummary.total > 0 }">
              <span>合计</span>
              <Icon name="shard" :size="13" />
              <b>{{ pastSummary.total > 0 ? `+${fmt(pastSummary.total)}` : "0" }}</b>
            </span>
          </div>
          <div v-if="lastAside" class="past-aside">
            <div class="past-aside-head">
              <span>{{ lastName }}</span>
              <span class="aside-balls" :aria-label="`开奖号码 ${lastAside.number}`">
                <i v-for="(d, di) in lastAside.number.split('')" :key="di">{{ d }}</i>
              </span>
              <span class="past-aside-won" :class="{ on: lastAside.won > 0 }">
                <template v-if="lastAside.won > 0"><Icon name="shard" :size="13" />+{{ fmt(lastAside.won) }}</template>
                <template v-else>未中奖</template>
              </span>
            </div>
            <ul class="past-stubs">
              <li v-for="(t, i) in lastAside.mine" :key="i" :class="{ out: !t.tier }">
                <TicketStub size="s">
                  <span v-for="(c, j) in digits(t.number, t.tier)" :key="j" class="digit" :class="{ on: c.hit }">{{ c.d }}</span>
                </TicketStub>
                <b v-if="t.prize" class="stamp" :class="{ top: t.tier === 'top' }">+{{ fmt(t.prize) }}</b>
              </li>
            </ul>
          </div>
          <div v-if="past.length" class="history-wrap">
            <div class="history-head" aria-hidden="true">
              <span>日期</span><span>号码</span><span>头奖</span><span>奖金</span><span>我的</span>
            </div>
            <ul class="history">
              <li v-for="h in past" :key="h.day" :class="{ 'mine-hit': (h.won ?? 0) > 0, played: h.won !== null }">
                <span class="h-day">{{ shortDay(h.day) }}</span>
                <b>{{ h.number }}</b>
                <span class="winners" :class="{ none: !h.top.length }">{{ h.winners }}</span>
                <span class="prize" :class="{ none: !h.top.length }">
                  <template v-if="h.top.length"><Icon name="shard" :size="13" />{{ fmt(h.each) }}</template>
                  <template v-else>—</template>
                </span>
                <span v-if="h.won !== null && h.won > 0" class="won on">
                  <Icon name="shard" :size="12" />+{{ fmt(h.won) }}
                </span>
                <span v-else-if="h.won === 0" class="won">未中奖</span>
                <span v-else class="won none">—</span>
              </li>
            </ul>
          </div>
        </div>
      </Transition>

      <!-- The buy keys, all alike: what they do, then the coins they take. -->
      <div v-if="!state.drawn" class="park-actions-main">
        <p v-if="note" class="note" :class="{ warn: !!buyError }" role="status">{{ note }}</p>
        <button
          type="button" class="ui-btn buy-key" :disabled="blocked(1) !== null" :aria-busy="busy === 'random'"
          aria-keyshortcuts="R"
          @keydown.space.prevent @keyup.space.prevent @keydown="(e) => e.repeat && e.preventDefault()"
          @click="buyRandom(1)"
        >
          <span>机选</span>
          <small class="buy-cost"><img :src="COIN_SMALL" alt="" draggable="false" />1</small>
        </button>
        <button
          v-if="state.left > 1" type="button" class="ui-btn buy-key"
          :disabled="blocked(state.left) !== null"
          @keydown.space.prevent @keyup.space.prevent @keydown="(e) => e.repeat && e.preventDefault()"
          @click="buyRandom(state.left)"
        >
          <span>机选 {{ state.left }} 注</span>
          <small class="buy-cost"><img :src="COIN_SMALL" alt="" draggable="false" />{{ state.left }}</small>
        </button>
        <button
          type="button" class="ui-btn primary buy-key" :class="{ pulse: pickReady && !calm && pageActive }" :disabled="!pickReady"
          :aria-busy="busy === 'pick'" aria-keyshortcuts="Enter"
          :title="samePickedCount > 0 ? `已选 ${samePickedCount} 注，再买共 ${samePickedCount + 1} 注` : undefined"
          @keydown.space.prevent @keyup.space.prevent @keydown="(e) => e.repeat && e.preventDefault()"
          @click="buyPicked"
        >
          <span class="pick-num">买<b
            v-for="(d, i) in pickFaces" :key="i" :class="{ gap: d === '_' }" :aria-hidden="d === '_' || undefined"
          >{{ d }}</b><em v-if="samePickedCount > 0" class="mult-next">×{{ samePickedCount + 1 }}</em></span>
          <small class="buy-cost"><img :src="COIN_SMALL" alt="" draggable="false" />1</small>
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped src="./lottery-ball.css"></style>
<style scoped>
/* Fills the park's white body; the bottom bar (.park-actions) is the last child, so the root has no side padding. */
.lottery {
  position: relative;
  display: flex;
  flex-direction: column;
}
/*
 * Two columns: the machine with the tray of stubs under it, and the pool with the board beside them. The tray's row
 * is always as tall as two rows of stubs, so the side keeps its height when the tray has fewer.
 */
.stage {
  --tray-h: 116px;
  flex: 1 0 auto;
  display: grid;
  grid-template-columns: auto minmax(0, 360px);
  grid-template-rows: auto minmax(var(--tray-h), auto);
  grid-template-areas:
    "machine side"
    "tray side";
  justify-content: center;
  align-content: center;
  gap: 14px 20px;
  padding: 16px 18px 16px;
}
/* Nothing loaded: the error is the sheet's first line. */
.stage.empty {
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
}
.stage > .ui-error {
  align-self: stretch;
  margin: 0;
}

/* ---- the draw machine: the globe on its base over the cabinet; the tube and track drawn behind the globe */
.machine {
  grid-area: machine;
  justify-self: center;
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.tube {
  position: absolute;
  left: 0;
  top: 0;
  z-index: 2;
  overflow: visible;
  pointer-events: none;
}
.tube path {
  fill: none;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.tube-shadow {
  stroke: rgba(var(--c-900-rgb), 0.14);
}
.tube-port {
  fill: rgba(255, 255, 255, 0.58);
  stroke: var(--c-600);
  stroke-width: 1.4;
}
.tube-collar {
  fill: var(--c-100);
  stroke: var(--c-400);
  stroke-width: 2;
}
.tube-edge {
  stroke: var(--c-600);
  opacity: 0.72;
}
/* A touch of coral over the white page, then a white veil, so the glass shows on the page and on the cabinet alike. */
.tube-tint {
  stroke: rgba(var(--c-500-rgb), 0.12);
}
.tube-glass {
  stroke: rgba(255, 255, 255, 0.54);
}
.tube-shine {
  stroke: #fff;
  stroke-width: 2.4;
  opacity: 0.9;
}
.stand {
  position: relative;
  z-index: 3;
  display: flex;
  flex-direction: column;
  align-items: center;
}
/* Sunlit blown-glass vessel: bright dome bloom top-left, crisp inner meniscus, warm caustics along the bottom cup. */
.globe {
  --globe: 140px;
  --ball: 27px;
  position: relative;
  z-index: 1;
  width: var(--globe);
  height: var(--globe);
  overflow: hidden;
  border-radius: 50%;
  background: radial-gradient(
    circle at 32% 26%,
    #fff 0%,
    color-mix(in srgb, var(--c-50) 95%, transparent) 38%,
    color-mix(in srgb, var(--c-100) 91%, transparent) 74%,
    color-mix(in srgb, var(--c-200) 96%, transparent) 100%
  );
  box-shadow:
    0 0 0 2px var(--c-300),
    0 10px 20px -12px rgba(var(--c-900-rgb), 0.28),
    inset 0 2px 1px #fff,
    inset 0 0 0 2px rgba(255, 255, 255, 0.88),
    inset 0 -16px 22px -10px rgba(var(--c-500-rgb), 0.42);
}
/* Upward warm air jet while the blower runs. */
.air-plume {
  position: absolute;
  inset: 38% 18% 0;
  border-radius: 50% 50% 44% 44%;
  background: radial-gradient(
    50% 92% at 50% 100%,
    rgba(255, 255, 255, 0.9) 0%,
    rgba(var(--c-500-rgb), 0.22) 52%,
    transparent 100%
  );
  opacity: 0;
  transform: scaleY(0.75);
  transform-origin: 50% 100%;
  transition: opacity var(--dur-base), transform var(--dur-base) var(--ease-out);
  pointer-events: none;
}
.globe.blowing .air-plume {
  opacity: 1;
  animation: air-gust 520ms var(--ease-in-out) infinite alternate;
}
@keyframes air-gust {
  from { transform: scale(0.94, 0.88); }
  to { transform: scale(1.06, 1.08); }
}
.glass {
  position: absolute;
  inset: 0;
  z-index: 1;
  overflow: visible;
  pointer-events: none;
}
.glass path {
  fill: none;
  stroke: #fff;
  stroke-width: 3.4;
  stroke-linecap: round;
}
.glass .spark-dot {
  fill: #fff;
  opacity: 0.92;
}
.glass .far {
  stroke-width: 2;
  opacity: 0.74;
}
/* A ball in the globe sits at its centre; the simulation moves and turns it. */
.gball {
  --s: var(--ball);
  position: absolute;
  left: 50%;
  top: 50%;
  margin: calc(var(--ball) / -2) 0 0 calc(var(--ball) / -2);
  will-change: transform;
}
/* Out of the globe (in its window, or on the way there), or not placed yet. */
.gball.out,
.globe:not(.ready) .gball {
  opacity: 0;
}
/* The base the globe sits in: a coral collar with a blower lamp on its front and its thickness showing below. */
.base {
  position: relative;
  width: 64%;
  height: 18px;
  margin-top: -9px;
  border-radius: 9px 9px 5px 5px;
  background: linear-gradient(180deg, var(--c-400), var(--c-500));
  box-shadow:
    inset 0 4px 5px -2px rgba(var(--c-900-rgb), 0.22),
    inset 0 -1px 0 rgba(255, 255, 255, 0.35),
    0 5px 0 var(--c-600);
}
.base::after {
  content: "";
  position: absolute;
  left: 50%;
  bottom: 3px;
  width: 22px;
  height: 4px;
  margin-left: -11px;
  border-radius: 999px;
  background: rgba(var(--c-900-rgb), 0.22);
  box-shadow: inset 0 1px 1px rgba(var(--shadow-rgb), 0.2);
  transition: background var(--dur-base), box-shadow var(--dur-base);
}
.stand.blowing .base::after {
  background: var(--gold-soft);
  box-shadow: 0 0 8px 1px rgba(255, 255, 255, 0.8);
}
/* The cabinet: a molded coral console with a bottom lip; the track runs in its top band, the windows under it. */
.cabinet {
  margin-top: 5px;
  padding: 37px 14px 12px;
  border-radius: 20px;
  background: var(--grad-sky);
  box-shadow:
    inset 0 2px 0 rgba(255, 255, 255, 0.45),
    0 5px 0 var(--c-600),
    0 14px 26px -14px rgba(var(--shadow-rgb), 0.48);
}
/* A drawn ball between the globe and its window, placed by script from the machine's top left corner. */
.drop {
  position: absolute;
  left: 0;
  top: 0;
  z-index: 4;
  margin: calc(var(--s) / -2) 0 0 calc(var(--s) / -2);
  transform: scale(0);
  pointer-events: none;
  will-change: transform;
}
/* With no globe shown, a drawn ball pops into its window. */
.reveal .slot-ball.pop {
  animation: stamp-in 320ms var(--ease-pop) both;
}

/* ---- the number keys: three tall keycaps, each sunk in its own pale window in the cabinet; typing presses them */
.keys {
  --key-w: 84px;
  --key-h: 84px;
  --slot-ball: 70px;
  position: relative;
  display: flex;
  gap: 10px;
}
.key-col {
  position: relative;
  display: flex;
  padding: 10px 10px;
  border-radius: 14px;
  background: var(--c-100);
  box-shadow: inset 0 3px 6px rgba(var(--c-900-rgb), 0.2), 0 1px 0 rgba(255, 255, 255, 0.38);
  transition: background var(--dur-slow), box-shadow var(--dur-slow);
}
.key-col.active {
  box-shadow:
    inset 0 0 0 1.5px var(--c-400),
    inset 0 3px 6px rgba(var(--c-900-rgb), 0.18),
    0 1px 0 rgba(255, 255, 255, 0.42);
}
.key-col.selected {
  box-shadow:
    inset 0 0 0 2px var(--c-500),
    inset 0 3px 6px rgba(var(--c-900-rgb), 0.16),
    0 1px 0 rgba(255, 255, 255, 0.45);
}
/* The draw readies the windows in cream, then lights each one white as its ball lands. */
.keys.drum .key-col {
  background: var(--c-50);
  box-shadow: inset 0 0 0 2px var(--c-300), inset 0 3px 6px rgba(var(--c-900-rgb), 0.12);
}
.keys.drum .key-col.filled {
  background: var(--surface);
  box-shadow: inset 0 0 0 3px var(--c-300), 0 0 16px 3px rgba(255, 255, 255, 0.72);
}
.socket {
  display: grid;
  place-items: center;
  width: var(--key-w);
  height: var(--key-h);
}
.socket::before {
  content: "";
  grid-area: 1 / 1;
  width: var(--slot-ball);
  height: var(--slot-ball);
  border-radius: 50%;
  background: var(--c-100);
  box-shadow: inset 0 2px 5px rgba(var(--c-900-rgb), 0.14);
}
.slot-ball {
  --s: var(--slot-ball);
  grid-area: 1 / 1;
}
.numkey {
  --key-lip-h: 4px;
  width: var(--key-w);
  height: var(--key-h);
  padding: 0;
  border-radius: 12px;
}
.numkey.down:not(:disabled) {
  --key-y: 4px;
  --key-lip-h: 0px;
  --key-lift: 0px;
  transition-duration: var(--dur-press);
  transition-timing-function: ease-out;
}
/* Latched (the key being changed): a step of the ramp under the white. */
.numkey.on:not(:disabled) {
  --key-top: var(--c-200);
  --key-bottom: var(--c-200);
  --key-lip: var(--c-300);
}
/* Sales over: the keys sit flat in their windows. */
.numkey:disabled {
  --key-top: var(--c-50);
  --key-bottom: var(--c-50);
}
.numkey:disabled .face {
  color: var(--ink-3);
}
/* Low-profile rocker tabs on a number key's top and bottom bezel: quiet at rest, crisp on hover or selection. */
.step {
  --key-top: var(--c-50);
  --key-bottom: var(--c-100);
  --key-lip-h: 1.5px;
  position: absolute;
  left: 50%;
  z-index: 1;
  width: 38px;
  height: 18px;
  margin-left: -19px;
  padding: 0;
  border-radius: var(--radius-s);
  color: var(--ink-3);
  opacity: 0.78;
  transition:
    transform var(--dur-release) var(--ease-spring),
    box-shadow var(--dur-release) var(--ease-spring),
    color var(--dur-fast),
    opacity var(--dur-base);
}
.key-col:hover .step:not(:disabled),
.key-col.selected .step:not(:disabled),
.step:focus-visible {
  --key-top: #fff;
  --key-bottom: var(--key-white-shade);
  opacity: 1;
}
.step:hover:not(:disabled) {
  color: var(--ink);
}
.step.up {
  top: 2px;
}
.step.up svg {
  rotate: 180deg;
}
.step.down {
  bottom: 1px;
}
/* Off with the sales. */
.step:disabled {
  opacity: 0;
  pointer-events: none;
}
/* The field to read the keyboard: there, focusable, never seen. */
.field {
  position: absolute;
  left: 50%;
  bottom: 0;
  width: 1px;
  height: 1px;
  padding: 0;
  border: 0;
  opacity: 0;
  pointer-events: none;
}
.face {
  font: 800 68px/1 var(--font-latin);
  color: var(--ink);
  animation: face-in 200ms var(--ease-pop) both;
}
/* A stepped digit comes in from the side it was stepped from; a typed one from above. */
@keyframes face-in {
  from { transform: translateY(var(--from, -10px)) scale(0.8); opacity: 0; }
}
/* A key with no digit yet: the empty place of a ball. */
.blank,
.rc.void::after {
  box-sizing: border-box;
  width: 36px;
  height: 36px;
  border: 3px dashed var(--c-300);
  border-radius: 50%;
}
.numkey:disabled .blank {
  border-color: var(--c-200);
}
.caret {
  position: absolute;
  left: 50%;
  top: 26px;
  width: 3px;
  height: 50px;
  margin-left: -1.5px;
  border-radius: 2px;
  background: var(--c-500);
  animation: caret 1.1s steps(1) infinite;
}
.inactive .caret,
.inactive .globe.blowing .air-plume {
  animation-play-state: paused;
}
@keyframes caret {
  50% { opacity: 0; }
}
/* After a spin the keys go back softly, once the number has left them; after the draw they keep it as it landed. */
.keys.fade .face,
.keys.fade .blank {
  animation: face-back 320ms ease-out 120ms both;
}
@keyframes face-back {
  from { opacity: 0; }
}
.keys.still .face,
.calm .keys .face,
.calm .keys .blank,
.calm .caret {
  animation: none;
}

/* A spinning key: a window onto a curved drum of digits, the two in view placed by script. */
.reel {
  position: absolute;
  inset: 0;
  overflow: hidden;
  border-radius: inherit;
  -webkit-mask: linear-gradient(180deg, transparent, #000 22%, #000 78%, transparent);
  mask: linear-gradient(180deg, transparent, #000 22%, #000 78%, transparent);
}
.reel::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  box-shadow:
    inset 0 12px 10px -8px rgba(var(--c-900-rgb), 0.18),
    inset 0 -12px 10px -8px rgba(var(--c-900-rgb), 0.18);
  pointer-events: none;
}
.rc {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  font: 800 68px/1 var(--font-latin);
  color: var(--ink);
  transition: color var(--dur-base);
  will-change: transform;
}
.rc.void::after {
  content: "";
}
.rc.landed {
  animation: rc-land 260ms var(--ease-out);
}
@keyframes rc-land {
  40% { translate: 0 5%; }
}
/* A digit of a number bought, between the keys and its stub (not `.ghost`: that is the quiet key of ui-btn). */
.flyer {
  position: absolute;
  z-index: 3;
  font-family: var(--font-latin);
  font-weight: 800;
  line-height: 1;
  color: var(--ink);
  transform: translate(-50%, -50%);
  pointer-events: none;
}

/* ---- the tray: my stubs in a grid of five, empty places in dashed coral outlines, the count at the end */
.tray {
  grid-area: tray;
  justify-self: center;
  align-self: start;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 12px 12px 14px;
  border-radius: var(--radius-l);
  background: var(--c-50);
}
.stubs {
  display: grid;
  grid-template-columns: repeat(5, 62px);
  grid-auto-rows: 40px;
  gap: 12px 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.cell {
  position: relative;
  display: flex;
  transition: opacity var(--dur-slow) var(--ease-out);
}
.cell.interactive {
  cursor: pointer;
}
.lottery:not(.calm) .cell:not(.held):not(.out):hover :deep(.ticket-stub),
.lottery:not(.calm) .cell.echo:not(.held):not(.out) :deep(.ticket-stub) {
  transform: translateY(-2px) rotate(-1deg);
}
.cell.multi :deep(.paper) {
  background: linear-gradient(90deg, var(--c-200) var(--x), var(--surface) var(--x));
}
.cell.echo:not(.held) :deep(.ticket-stub) {
  filter:
    drop-shadow(0 0 0 var(--c-500))
    drop-shadow(0 2px 6px rgba(var(--c-500-rgb), 0.45));
}
.cell.echo:not(.held) :deep(.paper) {
  box-shadow: inset 0 0 0 1.5px var(--c-500), inset 0 1px 0 rgba(255, 255, 255, 0.92);
}
.cell :deep(.paper) {
  width: 62px;
  min-width: 0;
  padding: 0 7px 0 calc(var(--tab) + 6px);
}
/* Bought, waiting for the number to leave the keys. */
.cell.held :deep(.ticket-stub),
.cell.held .mult-tag {
  opacity: 0;
}
/* Drawn and matching nothing: the stub steps back. */
.cell.out {
  opacity: 0.45;
}
/* Empty ticket slot: a flat dashed outline, never a pressable keycap or solid block. */
.slot {
  box-sizing: border-box;
  border: 2px dashed var(--c-200);
  border-radius: var(--radius-s);
  background: none;
  transition: border-color var(--dur-fast), background var(--dur-fast);
}
.slot.ready {
  cursor: pointer;
}
.slot.ready:hover {
  border-color: var(--c-300);
  background: rgba(255, 255, 255, 0.55);
}
.digit {
  position: relative;
  display: inline-block;
}
/* Drawn: what matched is coral (with a small mark beneath), the rest steps back. */
.drawn .digit {
  color: var(--ink-3);
}
.drawn .digit.on,
.past-stubs .digit.on {
  color: var(--c-700);
}
.drawn .digit.on::after {
  content: "";
  position: absolute;
  left: 50%;
  bottom: -4px;
  width: 4px;
  height: 2.5px;
  margin-left: -2px;
  border-radius: 999px;
  background: var(--c-500);
}
.cell.top-win .digit.on::after {
  background: var(--gold);
}
/* What a stub won, on its corner; gold foil for the top jackpot. */
.stamp {
  position: absolute;
  top: -9px;
  right: -7px;
  z-index: 2;
  padding: 2px 5px 1px;
  border-radius: 999px;
  background: var(--surface);
  box-shadow: inset 0 0 0 2px var(--c-400), 0 2px 4px -1px rgba(var(--shadow-rgb), 0.2);
  font: 800 14px/1 var(--font-latin);
  color: var(--c-700);
  white-space: nowrap;
}
.stamp.top {
  background: var(--grad-gold);
  box-shadow: 0 0 0 2px var(--surface), 0 4px 12px rgba(var(--gold-rgb), 0.68);
  color: var(--ink);
}
/* Multiplier badge (×2, ×3...) when the same number is stacked in the tray. */
.mult-tag {
  position: absolute;
  top: -8px;
  right: -6px;
  z-index: 2;
  padding: 2px 5px 1px;
  border-radius: 999px;
  background: var(--c-500);
  box-shadow: 0 0 0 1.5px var(--surface), 0 2px 4px -1px rgba(var(--c-900-rgb), 0.25);
  font: 800 12px/1 var(--font-latin);
  color: var(--ink);
  white-space: nowrap;
  animation: mult-pop 280ms var(--ease-pop) both;
}
.mult-sub {
  position: absolute;
  top: -8px;
  left: -4px;
  z-index: 2;
  padding: 1px 4px;
  border-radius: 999px;
  background: var(--c-200);
  box-shadow: 0 0 0 1.5px var(--surface);
  font: 800 11px/1 var(--font-latin);
  color: var(--c-800);
}
@keyframes mult-pop {
  from { transform: scale(0.5); opacity: 0; }
}
.count {
  flex: none;
  min-width: 36px;
  font: 800 var(--fs-number)/40px var(--font-latin);
  color: var(--ink-3);
  white-space: nowrap;
}
.count b {
  font-size: 24px;
  color: var(--ink);
}

/*
 * ---- the side: the gold pool plaque, then the board of the latest draws. It takes the height the machine and the tray
 * give the row (size containment keeps it from adding its own), and the board's rows scroll inside it when short.
 */
.side {
  grid-area: side;
  position: relative;
  contain: size;
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}
.side.only {
  justify-content: center;
}
/* The 往期 list's winners and prize columns (the board has its own, LotteryBoard.vue). */
.winners {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--ink);
}
.winners.none {
  color: var(--ink-3);
}
.prize {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
  font: 800 15px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  color: var(--ink);
}
.prize svg {
  color: color-mix(in oklab, var(--gold) 72%, var(--c-700));
}
.prize.none {
  color: var(--ink-3);
}
/* Held back while the draw plays on the keys. */
.result.hide {
  visibility: hidden;
}

/* ---- the bottom bar: 往期 (with a dot when the last draw's stubs sit inside), my result, the buy keys */
.past-key {
  gap: 5px;
  padding: 0 11px 0 9px;
}
.past-key svg {
  color: var(--c-700);
}
.past-dot {
  position: absolute;
  top: -2px;
  right: -2px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--c-500);
  box-shadow: 0 0 0 1.5px var(--c-100);
  pointer-events: none;
}
.last {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.when {
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.result {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-3);
}
.result.won {
  font: 800 22px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--c-700);
}
.note {
  min-width: 0;
  margin: 0;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-3);
  white-space: nowrap;
}
.note:empty {
  display: none;
}
.note.warn {
  color: var(--c-700);
}
/* The buy keys: what the key does, then the coins it takes. */
.buy-key {
  gap: 6px;
  padding: 0 14px;
}
.buy-cost {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: inherit;
}
.buy-cost img {
  width: 18px;
  height: 18px;
  filter: drop-shadow(0 1px 1px rgba(var(--c-900-rgb), 0.25));
}
/* The number the pick key buys: a short line for each key still blank. */
.pick-num {
  display: inline-flex;
  align-items: baseline;
}
.pick-num b {
  display: inline-block;
  width: 0.62em;
  font: 800 var(--fs-number)/1 var(--font-latin);
  text-align: center;
}
.pick-num b:first-of-type {
  margin-left: 5px;
}
.pick-num b.gap {
  opacity: 0.55;
}
.mult-next {
  margin-left: 4px;
  padding: 1px 5px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.55);
  font: 800 12px/1.1 var(--font-latin);
  font-style: normal;
  color: var(--ink);
}

/* The pop-up: the full list rises from the bar. */
.pop {
  position: absolute;
  z-index: 3;
  margin: 0;
  padding: 12px 14px;
  box-sizing: border-box;
  overflow-y: auto;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: var(--shadow-paper), 0 12px 32px -12px rgba(var(--c-900-rgb), 0.34);
  transform-origin: 24px 100%;
}
.pop-up-enter-active {
  transition: transform var(--dur-base) var(--ease-spring), opacity var(--dur-fast) var(--ease-out);
}
.pop-up-leave-active {
  transition: transform var(--dur-fast) var(--ease-in), opacity var(--dur-fast) var(--ease-in);
}
.pop-up-enter-from,
.pop-up-leave-to {
  opacity: 0;
  transform: translateY(8px) scale(0.96);
}
.past {
  left: 16px;
  bottom: calc(100% + 8px);
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 444px;
  max-width: calc(100% - 32px);
  max-height: 292px;
}
/* Personal participation & shard winnings summary across recent drawn days. */
.past-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 7px 11px;
  border-radius: var(--radius-m);
  background: var(--c-100);
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.past-stat b {
  font: 800 var(--fs-strong)/1 var(--font-latin);
  color: var(--ink);
}
.past-total {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  color: var(--ink-3);
}
.past-total b {
  font: 800 var(--fs-number)/1 var(--font-latin);
}
.past-total.on {
  color: var(--c-700);
}
/* My stubs of the last draw, on a tinted card above the list. */
.past-aside {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 9px 11px 10px;
  border-radius: var(--radius-m);
  background: var(--c-50);
}
.past-aside-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.aside-balls {
  display: inline-flex;
  align-items: center;
  gap: 3px;
}
.aside-balls i {
  display: inline-grid;
  place-items: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--surface);
  box-shadow: inset 0 0 0 1.5px var(--c-300);
  font: 800 13px/1 var(--font-latin);
  font-style: normal;
  color: var(--c-700);
}
.past-aside-won {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  color: var(--ink-3);
}
.past-aside-won.on {
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: var(--c-700);
}
.past-stubs {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.past-stubs li {
  position: relative;
  display: flex;
}
.past-stubs li.out {
  opacity: 0.5;
}
.past-stubs .digit {
  color: var(--ink-3);
}
/* One draw a row: the day, the number, the top prize winners, the top prize, my result. */
.history-wrap {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.history-head,
.history li {
  display: grid;
  grid-template-columns: 4.5em 3em minmax(0, 1fr) 74px 72px;
  align-items: center;
  gap: 8px;
  padding: 0 6px;
}
.history-head {
  padding-bottom: 4px;
  border-bottom: 1px solid var(--c-100);
  font: 700 var(--fs-caption)/1 var(--font);
  color: var(--ink-3);
}
.history-head span:nth-child(4),
.history-head span:nth-child(5) {
  text-align: right;
}
.history {
  display: flex;
  flex-direction: column;
  margin: 0;
  padding: 0;
  list-style: none;
}
.history li {
  position: relative;
  min-height: 31px;
  border-radius: var(--radius-s);
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-3);
}
.history li + li {
  border-top: 1px solid var(--c-100);
}
.history li.played {
  color: var(--ink-2);
}
.history li.mine-hit {
  padding-left: 9px;
  background: var(--c-50);
  color: var(--ink);
}
.history li.mine-hit::before {
  content: "";
  position: absolute;
  left: 2px;
  top: 6px;
  bottom: 6px;
  width: 3px;
  border-radius: 2px;
  background: var(--c-500);
}
.history b {
  font: 800 var(--fs-number)/1 var(--font-latin);
  letter-spacing: 0.06em;
  color: var(--ink-2);
}
.history li.mine-hit b {
  color: var(--c-700);
}
.history .won {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
  text-align: right;
  white-space: nowrap;
}
.history .won.none {
  opacity: 0.55;
}
.history .won.on {
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: var(--c-700);
}

/* ---- the first showing of a draw: each digit of my stubs lights as the key above it comes to rest; once all three
 * rest, the digits drop onto the board right to left and the stamps go down. */
.reveal .drawn .digit.on {
  animation: digit-lit 360ms var(--ease-out) both;
}
@keyframes digit-lit {
  from { color: var(--ink-3); }
  45% { transform: translateY(-4px) scale(1.18); }
  to { color: var(--c-700); }
}
.reveal .stamp,
.reveal .result.in {
  animation: stamp-in 360ms var(--ease-pop) both;
}
@keyframes stamp-in {
  from { transform: scale(1.7); opacity: 0; }
}
.calm .air-plume {
  display: none;
}
.calm .mult-tag {
  animation: none;
}
.calm .cell,
.calm .slot,
.calm .step,
.calm .key-col,
.calm .base::after {
  transition: none;
}

/* Narrow panel: smaller keys and globe; the side keeps the pool and the latest draw (the rest is in 往期); the tray
 * runs under both columns. */
@container panel (max-width: 760px) {
  .stage {
    grid-template-columns: auto minmax(0, 1fr);
    grid-template-rows: auto auto;
    grid-template-areas:
      "machine side"
      "tray tray";
    align-content: start;
    gap: 12px 14px;
    padding: 14px 16px;
  }
  .globe {
    --globe: 104px;
    --ball: 21px;
  }
  .base {
    height: 14px;
    margin-top: -7px;
  }
  .base::after {
    bottom: 2px;
    width: 16px;
    height: 3px;
    margin-left: -8px;
  }
  .cabinet {
    padding: 32px 8px 8px;
    border-radius: 16px;
  }
  .keys {
    --key-w: 54px;
    --key-h: 72px;
    --slot-ball: 48px;
    gap: 6px;
  }
  .key-col {
    padding: 8px 5px;
    border-radius: 11px;
  }
  .numkey {
    border-radius: var(--radius-m);
  }
  .face,
  .rc {
    font-size: 46px;
  }
  .blank,
  .rc.void::after {
    width: 26px;
    height: 26px;
    border-width: 2.5px;
  }
  .caret {
    top: 18px;
    height: 36px;
  }
  .step {
    width: 30px;
    height: 16px;
    margin-left: -15px;
  }
  .step.up {
    top: 1px;
  }
  .side {
    contain: none;
    gap: 8px;
  }
  .tray {
    padding: 10px 10px 10px 12px;
  }
  /* The bar stays one row: 往期 keeps its mark, the keys their price, the win its number. */
  .park-actions {
    gap: 8px;
    padding-left: 12px;
    padding-right: 12px;
  }
  .park-actions > .park-actions-main {
    gap: 8px;
  }
  .past-key {
    width: 32px;
    padding: 0;
  }
  .past-key > span,
  .when {
    display: none;
  }
  .buy-key {
    gap: 3px;
    padding: 0 9px;
  }
  .result.won {
    font-size: var(--fs-section);
  }
  .result.won svg {
    display: none;
  }
}

/* Medium-short panel (561px..680px, e.g. 920×620 where panel is 900×600): tighten the vertical globe, cabinet and two-row
 * stub tray so all 10 ticket slots stay wholly above .park-actions without clipping. */
@container panel (max-height: 680px) {
  .stage {
    --tray-h: 82px;
    gap: 8px 16px;
    padding: 8px 16px;
  }
  .globe {
    --globe: 96px;
    --ball: 20px;
  }
  .base {
    height: 12px;
    margin-top: -6px;
  }
  .base::after {
    bottom: 1.5px;
    width: 16px;
    height: 3px;
    margin-left: -8px;
  }
  .cabinet {
    margin-top: 4px;
    padding: 26px 10px 8px;
    border-radius: 16px;
  }
  .keys {
    --key-w: 62px;
    --key-h: 58px;
    --slot-ball: 48px;
    gap: 7px;
  }
  .key-col {
    padding: 6px;
    border-radius: 11px;
  }
  .numkey {
    border-radius: var(--radius-m);
  }
  .face,
  .rc {
    font-size: 46px;
  }
  .blank,
  .rc.void::after {
    width: 24px;
    height: 24px;
    border-width: 2.5px;
  }
  .caret {
    top: 14px;
    height: 30px;
  }
  .step {
    width: 30px;
    height: 15px;
    margin-left: -15px;
  }
  .step.up {
    top: 1px;
  }
  .tray {
    padding: 7px 10px 7px 12px;
  }
  .stubs {
    grid-auto-rows: 31px;
    row-gap: 6px;
  }
  .stubs :deep(.ticket-stub) {
    --h: 31px;
    --font-size: 17px;
    --tab: 9px;
    --bite: 3.8px;
  }
  .count {
    line-height: 31px;
  }
  .count b {
    font-size: 20px;
  }
  .side {
    gap: 8px;
  }
}

@container panel (max-width: 760px) and (max-height: 680px) {
  .keys {
    --key-w: 52px;
    --slot-ball: 46px;
    gap: 6px;
  }
}

/* Short panel: the globe beside smaller keys, the pool's amount beside its tiers; the body scrolls, the bar stays. */
@container panel (max-height: 560px) {
  .stage {
    --tray-h: 84px;
    align-content: start;
    gap: 8px 20px;
    padding: 8px 16px 10px;
  }
  /* The globe stands beside the cabinet; the tube runs across onto the track. */
  .machine {
    flex-direction: row;
    align-items: flex-end;
    gap: 34px;
  }
  .globe {
    --globe: 120px;
    --ball: 24px;
  }
  .base {
    height: 14px;
    margin-top: -7px;
  }
  .base::after {
    bottom: 2px;
    width: 16px;
    height: 3px;
    margin-left: -8px;
  }
  .stubs {
    row-gap: 6px;
  }
  .cabinet {
    margin-top: 0;
    padding: 33px 8px 8px;
    border-radius: 16px;
  }
  .keys {
    --key-w: 56px;
    --key-h: 66px;
    --slot-ball: 50px;
    gap: 6px;
  }
  .key-col {
    padding: 8px 5px;
    border-radius: 11px;
  }
  .numkey {
    border-radius: var(--radius-m);
  }
  .face,
  .rc {
    font-size: 48px;
  }
  .blank,
  .rc.void::after {
    width: 26px;
    height: 26px;
    border-width: 2.5px;
  }
  .caret {
    top: 18px;
    height: 38px;
  }
  .step {
    width: 30px;
    height: 16px;
    margin-left: -15px;
  }
  .step.up {
    top: 1px;
  }
  .tray {
    padding: 8px 8px 8px 10px;
  }
  .side {
    gap: 8px;
  }
  .result.won {
    font-size: var(--fs-heading);
  }
}

/* Narrow and short: no globe; the pool stacks as on a narrow panel; the tray keeps a second row of places only once it has a stub
 * there. */
@container panel (max-width: 760px) and (max-height: 560px) {
  /* No room for a globe whose balls can be read: the cabinet alone, its windows still taking the drawn balls. */
  .stand {
    display: none;
  }
  .cabinet {
    margin-top: 0;
    padding: 8px;
  }
  .stubs:not(:has(.cell:nth-child(6))) .slot:nth-child(n + 6) {
    display: none;
  }
  .stage {
    gap: 10px 14px;
    padding: 10px 16px 12px;
  }
}
</style>
