<script setup lang="ts">
// 每日夺宝 (docs/design/amusement-park.md §7, §11; docs/design/park-ui-rebuild.md §5.4), laid out like a lottery's
// draw broadcast: on the left the draw machine (a globe with a ring of the ten numbered balls over a coral cabinet with
// the three number keys in its windows) and the tray of my stubs of the day under it; on the right the pool (the top prize, server-wide,
// which rolls over until a draw has a top winner, with the second and the third under it) and the board of the latest
// draws (day, number, top prize winners, what I won). The bottom bar has my result of the draw on the table and the
// buy keys; 往期 there opens the full list on a narrow panel, and the last draw's stubs once today has its own. There
// is no push: while the page is open the state loads every POLL_MS, and every few seconds once the close or the draw
// is due. The countdown and 阿草 go up in the park's coral band (band.ts).
// The number keys double as reels: 机选 spins them onto the number bought, and a draw's first showing spins them onto
// the drawn number, one digit at a time from the right, while the ring of balls turns and each digit's ball drops onto
// its key.
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, useId, watch, type Ref } from "vue";
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
  cleanNumber, countdown, dayBefore, drawLabel, dropDigit, markDrawSeen, nextDraw, NO_PICKS, pickedNumber, pickLabel,
  pickTarget, putDigit, reelDigit, revealDigits, salesOpen, seenDraw, shortDay, stepDigit, verifyDraw, winnersLine,
  type LotteryBuy, type LotteryState, type LotteryTier, type Picks,
} from "./lottery";
import TicketStub from "./TicketStub.vue";

const POLL_MS = 20000;
/** After the close or the draw time, until the state shows it. */
const DUE_POLL_MS = 4000;
/** A key pressed by typing stays down this long. */
const PRESS_MS = 140;
/** Wheel travel (px) per digit step. */
const WHEEL_STEP = 40;
/** A reel at full spin, in cells per ms, and the time it takes to get there from rest. */
const SPIN_SPEED = 0.02;
const SPIN_UP_MS = 160;
/** A reel slowing to a stop eases out from full spin over at least this long (up to 3 / SPIN_SPEED ms more). */
const SETTLE_MS = 420;
/** 机选: the keys spin at least this long, then stop left to right this far apart; the number rests this long on them. */
const BUY_SPIN_MS = 260;
const BUY_STOP_GAP_MS = 110;
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
/** A draw's first showing: the balls blow DRAW_FIRST_MS before the last digit's ball goes, each digit to its left
 * DRAW_GAP_MS later. The stamps go down DRAW_STAMP_MS after the first digit's ball is in; the keys go back no sooner
 * than DRAW_HOLD_MS after that. */
const DRAW_FIRST_MS = 1000;
const DRAW_GAP_MS = 950;
const DRAW_STAMP_MS = 180;
const DRAW_HOLD_MS = 650;
/** How long the win in the bar counts up, by the best tier won. */
const ROLL_MS: Record<1 | 2 | 3, number> = { 1: 400, 2: 650, 3: 900 };
/** The top prize counts to a new amount over this long. */
const POOL_ROLL_MS = 700;
const fmt = (n: number) => n.toLocaleString("en-US");

const state = ref<LotteryState | null>(null);
const loadError = ref("");
const now = ref(Date.now() / 1000);
const calm = computed(() => reducedMotion.value);
/** The page is shown: the clock runs and a new draw may play its reveal. */
const active = ref(false);
/** The pop-up open over the bottom bar. */
const pop = ref<"" | "proof" | "past">("");
const rootEl = ref<HTMLElement>();

let loading = false;
let loadedAt = 0;
async function load() {
  if (loading) return;
  loading = true;
  loadedAt = Date.now();
  const player = status.value?.player;
  try {
    const r = await parkTry<LotteryState>("GET", "/api/park/lottery");
    if (player !== status.value?.player) return;
    if (r.ok) {
      state.value = r.data;
      loadError.value = "";
    } else if (!state.value && r.error.status > 0) {
      loadError.value = r.error.message;
    }
  } finally {
    loading = false;
  }
}

// ---- the clock: the countdown, the close on this machine's clock, and loading again on time
let timer: ReturnType<typeof setInterval> | null = null;
function tick() {
  now.value = Date.now() / 1000;
  const s = state.value;
  // Past the close the keys are off at once; the state loads right away, then often until the server agrees.
  const closing = !!s && s.open && now.value >= s.closeAt;
  const due = closing || (!!s && !s.drawn && now.value >= s.drawAt);
  if ((closing && loadedAt < s!.closeAt * 1000) || Date.now() - loadedAt >= (due ? DUE_POLL_MS : POLL_MS)) void load();
}
function start() {
  active.value = true;
  window.addEventListener("keydown", onPageKey, true);
  if (timer) return;
  now.value = Date.now() / 1000;
  void load();
  timer = setInterval(tick, 1000);
}
function stop() {
  active.value = false;
  window.removeEventListener("keydown", onPageKey, true);
  if (timer) clearInterval(timer);
  timer = null;
  pop.value = "";
  settle();
}
// The page is kept alive: mounting (the park may open while the page is shown) and coming back both start the clock.
onMounted(start);
onActivated(start);
onDeactivated(stop);
onBeforeUnmount(() => {
  stop();
  stopPool();
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
  if (timer) void load();
});

// ---- the next draw
const drawTime = computed(() => (state.value ? nextDraw(state.value) : 0));
const left = computed(() => countdown(drawTime.value, now.value));
const waiting = computed(() => !!state.value && !state.value.drawn && now.value >= state.value.drawAt);
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
/** Sales are over for today, by the server or by this machine's clock. */
const closed = computed(() => !!state.value && !salesOpen(state.value, now.value));

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
/** Where the caret shows: the key the next typed digit goes to. */
const target = computed(() => (typing.value && !keysOff.value && !locked.value ? pickTarget(picks.value, at.value) : null));
const pickReady = computed(() => typed.value.length === 3 && blocked(1) === null);
const note = computed(() => buyError.value || blocked(1) || "");

const pressTimers: ReturnType<typeof setTimeout>[] = [];
function press(i: number) {
  if (calm.value) return;
  pressed.value = pressed.value.map((p, j) => p || j === i);
  clearTimeout(pressTimers[i]);
  pressTimers[i] = setTimeout(() => (pressed.value = pressed.value.map((p, j) => p && j !== i)), PRESS_MS);
}
function put(d: string) {
  const r = putDigit(picks.value, at.value, d);
  if (r.key === null) return;
  faceIn.value = "";
  stepped.value = stepped.value.map((s, j) => (j === r.key ? 0 : s));
  picks.value = r.picks;
  at.value = null;
  press(r.key);
}
/** Typed or pasted digits go onto the keys; the field itself stays empty. */
function onType(e: Event) {
  const input = e.target as HTMLInputElement;
  if (!keysOff.value && !locked.value) for (const d of cleanNumber(input.value)) put(d);
  input.value = "";
}
function onKey(e: KeyboardEvent) {
  if (e.isComposing) return;
  if (e.key === "Enter") {
    buyPicked();
  } else if (e.key === "Escape") {
    // Lets go of a picked key before the panel's own Escape closes the panel.
    if (at.value !== null) {
      at.value = null;
      e.stopPropagation();
    }
  } else if (keysOff.value || locked.value) {
    return;
  } else if (e.key === "Backspace" || e.key === "Delete") {
    e.preventDefault();
    faceIn.value = "";
    picks.value = dropDigit(picks.value, at.value);
    at.value = null;
  } else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
    e.preventDefault();
    const from = at.value ?? pickTarget(picks.value, null) ?? 2;
    at.value = Math.min(2, Math.max(0, from + (e.key === "ArrowLeft" ? -1 : 1)));
  } else if (e.key === "ArrowUp" || e.key === "ArrowDown") {
    e.preventDefault();
    step(at.value ?? pickTarget(picks.value, null) ?? 2, e.key === "ArrowUp" ? 1 : -1);
  }
}
/**
 * Keys typed anywhere on the shown page while picking is open go to the number keys, ahead of the panel's digit page
 * shortcuts (a window listener in the bubble phase). Editable fields keep their keys (the hidden field has its own
 * handler), a focused tab keeps its arrows and a focused key its Enter; with picking closed everything passes through.
 */
function onPageKey(e: KeyboardEvent) {
  const s = state.value;
  if (!s || s.drawn || keysOff.value || e.isComposing || e.ctrlKey || e.metaKey || e.altKey) return;
  if (document.querySelector("[data-overlay]")) return;
  const el = document.activeElement;
  const focused = (sel: string) => !!el?.closest?.(sel);
  if (focused("input, textarea, select, [contenteditable]")) return;
  const digit = /^[0-9]$/.test(e.key);
  const arrow = e.key.startsWith("Arrow");
  if (!digit && !arrow && e.key !== "Backspace" && e.key !== "Enter") return;
  if (arrow && focused("[role=tab]")) return;
  if (e.key === "Enter" && focused("button, a, [role=button]")) return;
  e.stopImmediatePropagation();
  e.preventDefault();
  if (!digit) onKey(e);
  else if (!locked.value) put(e.key);
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

// ---- what plays on the keys. Everything below runs under one generation: settle() ends it all at once, on the state
// it was heading for, and any timer or callback of an older generation does nothing.
let gen = 0;
const timers = new Set<ReturnType<typeof setTimeout>>();
function later(ms: number, fn: () => void) {
  const g = gen;
  const t = setTimeout(() => {
    timers.delete(t);
    if (g === gen) fn();
  }, ms);
  timers.add(t);
}
function settle() {
  gen++;
  timers.forEach(clearTimeout);
  timers.clear();
  if (reeling.value) endReels("still");
  haltGlobe();
  ghosts.value = [];
  held.value = false;
  stopWon();
  reveal.value = "";
  stopped.value = 3;
  stamped.value = true;
}

// ---- the reels: while spinning, each number key shows a window onto an endless column of digits. Cell 0 is what
// the key showed, later cells run through every digit, and the cell a reel stops on is given the digit it lands on.
// Two cells are in the window at a time; they are written straight to the DOM each frame (transform only).
interface Reel {
  /** Cells travelled; cell k sits (pos - k) cells down from the window. */
  pos: number;
  from: string;
  /** When to start slowing (performance time), and the digit to land on. */
  stopAt: number | null;
  land: string;
  /** Slowing down: from p0 at t0 to the cell `end` over `ms`, easing out from full spin. */
  end: number;
  p0: number;
  t0: number;
  ms: number;
  done: boolean;
  /** The cell each of the two cell elements shows. */
  shown: [number, number];
}
const reeling = ref<"" | "buy">("");
let reels: Reel[] = [];
let reelCells: HTMLElement[][] = [];
let reelFrame = 0;
let reelStart = 0;
let lastFrame = 0;
let onLand: (i: number) => void = () => {};
let onRest: () => void = () => {};

function cellDigit(r: Reel, i: number, k: number): string {
  if (k === 0) return r.from;
  if (!r.ms) return reelDigit(k, i);
  if (k === r.end) return r.land;
  const d = reelDigit(k, i);
  // The cell before the stop never shows the digit it stops on.
  return k === r.end - 1 && d === r.land ? reelDigit(k + 5, i) : d;
}
function paint(i: number) {
  const r = reels[i];
  const els = reelCells[i];
  if (!r || !els || els.length < 2) return;
  const k0 = Math.floor(r.pos);
  for (const k of [k0, k0 + 1]) {
    const el = els[k % 2]!;
    if (r.shown[k % 2] !== k) {
      r.shown[k % 2] = k;
      const d = cellDigit(r, i, k);
      el.textContent = d;
      el.classList.toggle("void", !d);
      el.classList.remove("landed");
    }
    el.style.transform = `translateY(${(r.pos - k) * 100}%)`;
  }
}
function spin(t: number) {
  // A frame's time can be a little behind performance.now() taken at the start.
  const dt = Math.min(64, Math.max(0, t - lastFrame));
  lastFrame = Math.max(lastFrame, t);
  const v = SPIN_SPEED * Math.min(1, Math.max(0, t - reelStart) / SPIN_UP_MS);
  let running = false;
  reels.forEach((r, i) => {
    if (r.done) return;
    if (r.stopAt !== null && !r.ms && t >= r.stopAt) {
      r.p0 = r.pos;
      r.t0 = t;
      r.end = Math.ceil(r.pos + (SPIN_SPEED * SETTLE_MS) / 3);
      // An ease-out cubic starts at three times its average speed: start it at full spin.
      r.ms = (3 * (r.end - r.pos)) / SPIN_SPEED;
    }
    if (r.ms) {
      const u = Math.min(1, (t - r.t0) / r.ms);
      r.pos = r.p0 + (r.end - r.p0) * (1 - (1 - u) ** 3);
      if (u >= 1) {
        r.pos = r.end;
        r.done = true;
      }
    } else {
      r.pos += v * dt;
    }
    paint(i);
    if (r.done) {
      reelCells[i]?.[r.end % 2]?.classList.add("landed");
      onLand(i);
    } else {
      running = true;
    }
  });
  if (running) reelFrame = requestAnimationFrame(spin);
  else {
    reelFrame = 0;
    onRest();
  }
}
/** 机选: starts the three keys spinning from [from] while the balls blow in the globe. */
function startReels(from: readonly string[]) {
  const g = gen;
  reeling.value = "buy";
  reels = [0, 1, 2].map((i) => ({
    pos: 0, from: from[i] ?? "", stopAt: null, land: "", end: 0, p0: 0, t0: 0, ms: 0, done: false, shown: [-1, -1],
  }));
  onLand = () => {};
  onRest = () => {};
  reelStart = performance.now();
  airOn();
  // The reel windows are in the DOM after this render.
  void nextTick(() => {
    if (g !== gen) return;
    reelCells = Array.from(keysEl.value?.querySelectorAll(".reel") ?? [], (el) => Array.from(el.children) as HTMLElement[]);
    reelStart = lastFrame = performance.now();
    reels.forEach((_, i) => paint(i));
    reelFrame = requestAnimationFrame(spin);
  });
}
/** The spinning keys stop on [digits] left to right, no sooner than BUY_SPIN_MS after they started. */
function stopReels(digits: readonly string[], rest: () => void) {
  const t = Math.max(performance.now(), reelStart + BUY_SPIN_MS);
  reels.forEach((r, i) => {
    r.stopAt = t + i * BUY_STOP_GAP_MS;
    r.land = digits[i] ?? "";
  });
  onLand = press;
  onRest = () => {
    airOff();
    rest();
  };
}
/** The keys show their faces again: [face] says how they come in. */
function endReels(face: "fade" | "still") {
  cancelAnimationFrame(reelFrame);
  reelFrame = 0;
  reels = [];
  reelCells = [];
  faceIn.value = face;
  reeling.value = "";
}

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
const tubeMask = `tube-${useId()}`;
const globeEl = ref<HTMLElement>();
const cabinetEl = ref<HTMLElement>();
const tubePathEl = ref<SVGPathElement>();

/** The tube and the track, from the rendered machine: the path to draw and the points a ball runs through. */
interface Pt { x: number; y: number }
interface Tube {
  w: number; h: number; d: string; width: number; ball: number; exit: Pt; entry: Pt; end: number; y: number;
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
  const lastCol = cols[2]!.getBoundingClientRect();
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
    width: ball + 4, ball, exit, entry, end, y, cx, cy, R: r - 2, angle,
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
  wake();
}
function airOff() {
  if (!globeSim) return;
  globeSim.airTarget = 0;
  wake();
}
/** Everything stops where it should end up: the air off, the pile fallen still, no ball on its way. */
function haltGlobe() {
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
  const g = globeEl.value;
  if (g && globeSim) {
    for (const el of g.querySelectorAll<HTMLElement>(".gball")) {
      const b = globeSim.balls.find((x) => x.d === el.dataset.d);
      if (b) el.style.transform = `translate(${b.x.toFixed(2)}px, ${b.y.toFixed(2)}px) rotate(${b.a.toFixed(3)}rad)`;
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
  const path = tubePathEl.value;
  const m = machineEl.value;
  if (!t || !sim || !col || !path || !m || calm.value) {
    later(BALL_DROP_MS, done);
    return;
  }
  // Read now, while nothing moves: the window's centre and the size of its ball.
  const mb = m.getBoundingClientRect();
  const cb = col.getBoundingClientRect();
  const slot = { x: cb.left + cb.width / 2 - mb.left, y: cb.top + cb.height / 2 - mb.top };
  const size = parseFloat(getComputedStyle(col).getPropertyValue("--slot-ball")) || 64;
  const track = Math.abs(t.entry.x - t.end);
  const curve = path.getTotalLength() - track;
  if (!sim.has(d)) sim.add(d);
  const g = gen;
  sim.pull(d, (b) => {
    if (g !== gen) return;
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
  const path = tubePathEl.value;
  if (!runs.length) return;
  if (!t || !path) {
    runs.forEach((r) => r.done());
    runs = [];
    drops.value = [];
    return;
  }
  const finished: Run[] = [];
  for (const run of runs) {
    run.el ??= machineEl.value?.querySelector<HTMLElement>(`.drop[data-id="${run.id}"]`) ?? null;
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
        const q = path.getPointAtLength(Math.min(s - run.lead, path.getTotalLength()));
        p = { x: q.x, y: q.y };
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

// ---- a number bought leaves the keys: its digits fly into the new stub, which grows out of the keys around them.
// A spot is the centre of a digit and its font size; the spots on the keys are kept from the keys' top left corner,
// since the keys can move between the purchase and the flight.
interface Spot { d: string; x: number; y: number; size: number }
interface Ghost { id: number; d: string; x: number; y: number; size: number }
const ghosts = ref<Ghost[]>([]);
let ghostId = 0;
function spotOf(el: Element | null | undefined, d: string): Spot | null {
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return { d, x: r.left + r.width / 2, y: r.top + r.height / 2, size: parseFloat(getComputedStyle(el).fontSize) || 72 };
}
function onKeys(spots: (Spot | null)[]): Spot[] {
  const box = keysEl.value?.getBoundingClientRect();
  if (!box) return [];
  return spots.flatMap((p) => (p ? { ...p, x: p.x - box.left, y: p.y - box.top } : []));
}
/** Where the digits picked are on the keys. */
function faceSpots(): Spot[] {
  const keys = keysEl.value ? Array.from(keysEl.value.querySelectorAll(".numkey")) : [];
  return onKeys(keys.map((k, i) => spotOf(k.querySelector(".face"), picks.value[i] ?? "")));
}
/** Where the digits the reels stopped on are on the keys. */
function reelSpots(): Spot[] {
  return onKeys(reels.map((r, i) => spotOf(reelCells[i]?.[r.end % 2], r.land)));
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
  const g = gen;
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
  if (g !== gen) return;
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
  later(FLY_MS, () => (ghosts.value = []));
}

async function buy(body: { numbers?: string[]; random?: number }, kind: "pick" | "random") {
  settle();
  const g = gen;
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
    if (spinning && g === gen) stopReels(base, () => endReels("still"));
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
  if (calm.value || g !== gen) return;
  held.value = true;
  await nextTick();
  if (g !== gen) return;
  if (kind === "pick") {
    void fly(from);
    return;
  }
  // The keys show the last number bought.
  stopReels((bought[bought.length - 1] ?? "").split(""), () => later(BUY_HOLD_MS, () => {
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

/** Counts [out] to [to] over [ms], easing out; returns what cancels it. */
function countTo(out: Ref<number>, to: number, ms: number): () => void {
  const from = out.value;
  const begin = performance.now();
  let frame = 0;
  const stepFrame = (t: number) => {
    const u = Math.min(1, (t - begin) / ms);
    out.value = Math.round(from + (to - from) * (1 - (1 - u) ** 3));
    if (u < 1) frame = requestAnimationFrame(stepFrame);
  };
  frame = requestAnimationFrame(stepFrame);
  return () => cancelAnimationFrame(frame);
}

// ---- the pool card: top, second and third, each with the trailing digits it takes. The top prize is the
// server-wide pool of the next draw (after today's draw, the pool it rolled over into or started again from). The
// park's state carries the same pool and loads again on every coin spent anywhere in the park, so the card takes it
// from there when it can and always matches the pool in the top bar. A new amount counts up from the one shown.
const pool = computed(() => (state.value ? park.value?.jackpot ?? state.value.prize.top : null));
const poolShown = ref(0);
let stopPool = () => {};
watch(pool, (to, was) => {
  stopPool();
  if (to == null) return;
  if (was == null || calm.value) poolShown.value = to;
  else stopPool = countTo(poolShown, to, POOL_ROLL_MS);
}, { immediate: true });
/** The trailing digits a prize takes, left to right: true where the digit must match. */
const needs = (hit: number) => [0, 1, 2].map((j) => j >= 3 - hit);

// ---- the last draw
const last = computed(() => state.value?.last ?? null);
const winning = computed(() => (last.value ? last.value.number.split("") : []));
/** Today is drawn: the stubs on the table are the ones of the last draw, with their results. */
const drawnHere = computed(() => !!last.value && last.value.day === state.value?.day);
const lastName = computed(() => {
  const d = last.value?.day ?? "";
  const today = state.value?.day ?? "";
  return d === today ? "今日" : d === dayBefore(today) ? "昨日" : shortDay(d);
});
/**
 * The last draw's stubs, with their results, are on the table: today once it is drawn, and the day after it until the
 * first number of that day is bought, so a draw seen the next morning lights up the stubs it was played with.
 */
const lastOnTable = computed(() => {
  const s = state.value;
  const d = last.value;
  if (!s || !d) return false;
  return drawnHere.value || (!!d.mine.length && !s.tickets.length && d.day === dayBefore(s.day));
});
/** My stubs: today's, or the last draw's with what each matched. */
const table = computed(() => {
  const s = state.value;
  if (!s) return [];
  if (lastOnTable.value) return last.value!.mine;
  return s.tickets.map((number) => ({ number, tier: null, prize: 0 }));
});
/** The day of the stubs on the table, so a stub of one day is never reused for another. */
const tableDay = computed(() => (lastOnTable.value ? last.value!.day : state.value?.day ?? ""));
/** Today's tickets show with an empty place for each one still to buy, so a stub never moves when another is bought. */
const showCount = computed(() => !lastOnTable.value || drawnHere.value);
const slots = computed(() => (showCount.value ? Math.max(0, (state.value?.daily ?? 0) - table.value.length) : 0));

/** The server's drawn days with their top prize winners, each with what I won that day (null: I had no tickets). */
const past = computed(() => {
  const s = state.value;
  if (!s) return [];
  const mine = new Map(s.history.map((h) => [h.day, h.won]));
  return s.draws.map((d) => ({ ...d, winners: winnersLine(d.top), first: winnersLine(d.top, 1), won: mine.get(d.day) ?? null }));
});
/** The last draw's stubs when they are not on the table (today's stubs are): they go on top of 往期. */
const lastAside = computed(() => (!lastOnTable.value && last.value?.mine.length ? last.value : null));
const hasPast = computed(() => !!lastAside.value || past.value.length > 0);
/** A draw on the board stays blank while its first showing is still playing on the keys. */
const unseen = (day: string) => !!reveal.value && reveal.value === day && stopped.value < 3;

const verified = ref<boolean | null>(null);
// Checked again only when the draw itself changes, not on every reload of the same one.
watch(() => (last.value ? [last.value.day, last.value.number, last.value.salt, last.value.hash].join("|") : ""), async (key) => {
  verified.value = null;
  if (pop.value === "proof") pop.value = "";
  const d = last.value;
  if (!d) return;
  const ok = await verifyDraw(d.number, d.salt, d.hash);
  if (last.value?.day === d.day && key) verified.value = ok;
}, { immediate: true });

/** A ticket's digits, each marked when it is one of the trailing digits matched among the [stopped] at rest. */
function digits(number: string, tier: LotteryTier | null, stopped = 3) {
  const { lit } = revealDigits(tier, stopped);
  return number.split("").map((d, i) => ({ d, hit: lit[i]! }));
}

// ---- the first showing of a draw, on the keys: all three spin, then stop one by one from the right, each lighting the
// digits of my stubs it matches and fading the stubs it rules out; then the stamps go down and the win counts up.
const reveal = ref("");
/** Trailing digits of the draw at rest; 3 when nothing is playing. */
const stopped = ref(3);
/** The stamps and the result in the bar are out. */
const stamped = ref(true);
const wonShown = ref(0);
let stopWon = () => {};

function startReveal(day: string) {
  const d = last.value;
  if (!d) return;
  settle();
  reveal.value = day;
  stopped.value = 0;
  stamped.value = false;
  wonShown.value = 0;
  void nextTick(() => {
    layoutTube();
    airOn();
  });
  const number = d.number.split("");
  const land = () => {
    stopped.value++;
    if (stopped.value < 3) return;
    later(DRAW_STAMP_MS, () => {
      stamped.value = true;
      const best = d.mine.some((t) => t.tier === "top") ? 3 : d.mine.some((t) => t.tier === "second") ? 2 : 1;
      const ms = d.won > 0 ? ROLL_MS[best] : 0;
      if (ms) stopWon = countTo(wonShown, d.won, ms);
      later(Math.max(ms, DRAW_HOLD_MS), () => {
        faceIn.value = showDraw.value ? "still" : "fade";
        reveal.value = "";
        stopped.value = 3;
      });
    });
  };
  // From the right: the last digit's ball first; the air dies away once the third ball is on its way.
  [2, 1, 0].forEach((i, n) => later(DRAW_FIRST_MS + n * DRAW_GAP_MS, () => {
    sendBall(i, number[i]!, land);
    if (n === 2) later(350, airOff);
  }));
}
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

// ---- the two pop-ups (pop, above): the proof of the draw from the board, and the earlier days from the bar
const barEl = ref<HTMLElement>();
const sideEl = ref<HTMLElement>();
function toggle(p: "proof" | "past") {
  pop.value = pop.value === p ? "" : p;
}
function onOutside(e: PointerEvent) {
  const t = e.target as Node;
  if (!barEl.value?.contains(t) && !sideEl.value?.contains(t)) pop.value = "";
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
  <section ref="rootEl" class="lottery" :class="{ calm, reveal: !!reveal }" aria-label="每日夺宝">
    <div class="stage" :class="{ empty: !state }">
      <p v-if="loadError" class="ui-error" role="alert">{{ loadError }}</p>

      <template v-if="state">
        <!-- The draw machine: the glass globe of numbered balls on its base, the tube from its rim to the track along
             the cabinet's top, and the three windows: the number keys, or the draw's balls. -->
        <div ref="machineEl" class="machine" :class="{ drum }">
          <!-- The tube is clear glass: a tint over whatever is behind it, its two walls (a mask cuts the inside out of a
               wider stroke) and a line of light along its top. -->
          <svg v-if="tube" class="tube" :width="tube.w" :height="tube.h" aria-hidden="true">
            <defs>
              <mask :id="tubeMask" maskUnits="userSpaceOnUse" x="0" y="0" :width="tube.w" :height="tube.h">
                <path :d="tube.d" stroke="#fff" :stroke-width="tube.width + 3" />
                <path :d="tube.d" stroke="#000" :stroke-width="tube.width" />
              </mask>
            </defs>
            <path class="tube-tint" :d="tube.d" :stroke-width="tube.width" />
            <path ref="tubePathEl" class="tube-glass" :d="tube.d" :stroke-width="tube.width" />
            <path class="tube-edge" :d="tube.d" :stroke-width="tube.width + 3" :mask="`url(#${tubeMask})`" />
            <path class="tube-shine" :d="tube.d" :transform="`translate(0 ${-tube.width / 2 + 4})`" />
          </svg>
          <!-- The drawn balls on their way from the globe to their windows (placed by script). -->
          <i
            v-for="b in drops" :key="b.id" class="drop lball" :class="{ odd: odd(b.d) }" :data-id="b.id" aria-hidden="true"
            :style="{ '--s': `${b.size}px` }"
          ><b>{{ b.d }}</b></i>
          <div class="stand" aria-hidden="true">
            <div ref="globeEl" class="globe" :class="{ ready: globeReady }">
              <i
                v-for="d in DIGITS" :key="d" class="gball lball" :class="{ odd: odd(d), out: !present[d] }" :data-d="d"
              ><b>{{ d }}</b></i>
              <svg class="glass" viewBox="0 0 100 100">
                <path d="M15 46 A36 36 0 0 1 46 15" />
                <path class="far" d="M83 62 A36 36 0 0 1 68 82" />
              </svg>
            </div>
            <i class="base"></i>
          </div>
          <div ref="cabinetEl" class="cabinet">
            <!-- The keys take clicks, the wheel and their ▲/▼ keys; the keyboard goes to the hidden field under them. -->
            <div ref="keysEl" class="keys" :class="[faceIn, { drum }]">
              <div v-for="(d, i) in faces" :key="i" class="key-col">
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
                ref="field" class="field" type="text" inputmode="numeric" autocomplete="off" aria-label="号码"
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
              }"
            >
              <TicketStub size="s">
                <span
                  v-for="(c, j) in digits(t.number, t.tier, lastOnTable ? stopped : 3)" :key="j" class="digit"
                  :class="{ on: c.hit }"
                >{{ c.d }}</span>
              </TicketStub>
              <b v-if="t.prize && stamped" class="stamp" :class="{ top: t.tier === 'top' }">+{{ fmt(t.prize) }}</b>
            </li>
            <li v-for="n in slots" :key="`slot-${n}`" class="slot" aria-hidden="true"></li>
          </ol>
          <span class="count"><template v-if="showCount"><b>{{ state.tickets.length }}</b>/{{ state.daily }}</template></span>
        </div>

        <!-- The pool and the board of the latest draws. -->
        <aside ref="sideEl" class="side" :class="{ only: !past.length }" @keydown="onPopKey">
          <div class="pool-card" :aria-label="`头奖 累积奖池 ${fmt(pool ?? 0)}`">
            <div class="pool-head" aria-hidden="true">
              <span class="tier-name">头奖</span>
              <small>累积奖池</small>
              <span class="match"><i v-for="(on, j) in needs(3)" :key="j" :class="on ? 'lball' : 'hole'"></i></span>
            </div>
            <b class="pool-amount" aria-hidden="true"><Icon name="shard" :size="28" />{{ fmt(poolShown) }}</b>
            <ul class="tiers">
              <li :aria-label="`二等 ${fmt(state.prize.second)}`">
                <span class="tier-head" aria-hidden="true">
                  <span class="tier-name">二等</span>
                  <span class="match"><i v-for="(on, j) in needs(2)" :key="j" :class="on ? 'lball' : 'hole'"></i></span>
                </span>
                <b class="amount" aria-hidden="true"><Icon name="shard" :size="14" />{{ fmt(state.prize.second) }}</b>
              </li>
              <li :aria-label="`三等 ${fmt(state.prize.third)} /注`">
                <span class="tier-head" aria-hidden="true">
                  <span class="tier-name">三等</span>
                  <span class="match"><i v-for="(on, j) in needs(1)" :key="j" :class="on ? 'lball' : 'hole'"></i></span>
                </span>
                <b class="amount" aria-hidden="true"><Icon name="shard" :size="14" />{{ fmt(state.prize.third) }}<small>/注</small></b>
              </li>
            </ul>
          </div>

          <!-- One draw a row, newest first: its day, its number, who won the top prize, and what I won. -->
          <div v-if="past.length" class="board">
            <div class="board-head" aria-hidden="true"><span>日期</span><span>开奖号码</span><span>头奖</span></div>
            <ol class="rows ui-scroll">
              <li v-for="h in past" :key="h.day" :class="{ unseen: unseen(h.day) }">
                <span class="day">{{ shortDay(h.day) }}</span>
                <span
                  class="balls" :class="{ in: !!reveal && reveal === h.day && stopped === 3 }"
                  :aria-label="`开奖号码 ${h.number}`"
                ><i v-for="(d, i) in h.number.split('')" :key="i" class="lball" :class="{ odd: odd(d) }" :style="{ '--i': i }"><b>{{ d }}</b></i></span>
                <button
                  v-if="last && h.day === last.day && verified !== null" type="button" class="ui-btn ghost small proof-key"
                  :class="{ bad: !verified }" :title="verified ? '已校验' : '校验不符'" :aria-label="verified ? '已校验' : '校验不符'"
                  :aria-expanded="pop === 'proof'" @click="toggle('proof')"
                ><Icon :name="verified ? 'check' : 'info'" :size="14" /></button>
                <span v-else class="proof-gap"></span>
                <span class="winners" :class="{ none: !h.top.length }" :title="h.top.length > 1 ? h.winners : undefined">{{ h.first }}</span>
                <span v-if="h.won" class="won">+{{ fmt(h.won) }}</span>
              </li>
            </ol>
          </div>
          <dl v-if="pop === 'proof' && last" class="pop proof">
            <div><dt>哈希</dt><dd>{{ last.hash }}</dd></div>
            <div><dt>随机串</dt><dd>{{ last.salt }}</dd></div>
          </dl>
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
      ><Icon name="clock" :size="15" /><span>往期</span></button>
      <!-- My result of the draw whose stubs are in the tray. -->
      <div v-if="last && lastOnTable && last.mine.length" class="last">
        <span class="when">{{ lastName }}</span>
        <span class="result" :class="{ won: last.won > 0, hide: !stamped, in: !!reveal && stamped }">
          <template v-if="last.won > 0"><Icon name="shard" :size="16" />+{{ fmt(reveal ? wonShown : last.won) }}</template>
          <template v-else>未中奖</template>
        </span>
      </div>

      <div v-if="pop === 'past'" class="pop past ui-scroll">
        <ul v-if="lastAside" class="past-stubs">
          <li v-for="(t, i) in lastAside.mine" :key="i">
            <TicketStub size="s">
              <span v-for="(c, j) in digits(t.number, t.tier)" :key="j" class="digit" :class="{ on: c.hit }">{{ c.d }}</span>
            </TicketStub>
          </li>
        </ul>
        <ul v-if="past.length" class="history">
          <li v-for="h in past" :key="h.day">
            <span>{{ shortDay(h.day) }}</span>
            <b>{{ h.number }}</b>
            <span class="winners" :class="{ none: !h.top.length }">{{ h.winners }}</span>
            <span v-if="h.won !== null" class="won" :class="{ on: h.won > 0 }">{{ h.won > 0 ? `+${fmt(h.won)}` : "未中奖" }}</span>
            <span v-else></span>
          </li>
        </ul>
      </div>

      <!-- The buy keys, all alike: what they do, then the coins they take. -->
      <div v-if="!state.drawn" class="park-actions-main">
        <p class="note" :class="{ warn: !!buyError }" role="status">{{ note }}</p>
        <button
          type="button" class="ui-btn buy-key" :disabled="blocked(1) !== null" :aria-busy="busy === 'random'"
          @click="buyRandom(1)"
        >
          <span>机选</span><small class="buy-cost"><img :src="COIN_SMALL" alt="" draggable="false" />1</small>
        </button>
        <button
          v-if="state.left > 1" type="button" class="ui-btn buy-key"
          :disabled="blocked(state.left) !== null" @click="buyRandom(state.left)"
        >
          <span>机选 {{ state.left }} 注</span>
          <small class="buy-cost"><img :src="COIN_SMALL" alt="" draggable="false" />{{ state.left }}</small>
        </button>
        <button
          type="button" class="ui-btn primary buy-key" :class="{ pulse: pickReady }" :disabled="!pickReady"
          :aria-busy="busy === 'pick'" @click="buyPicked"
        >
          <span class="pick-num">买<b
            v-for="(d, i) in pickFaces" :key="i" :class="{ gap: d === '_' }" :aria-hidden="d === '_' || undefined"
          >{{ d }}</b></span>
          <small class="buy-cost"><img :src="COIN_SMALL" alt="" draggable="false" />1</small>
        </button>
      </div>
    </div>
  </section>
</template>

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

/*
 * ---- a lottery ball: a coral sphere (two steps of the ramp, by odd and even) with a white round label and the digit
 * in ink; one small sharp highlight and a soft dark edge along the bottom. --s is its size. Used in the globe, in the
 * windows, on the board and, without a label, as the pool card's match marks.
 */
.lball {
  --s: 24px;
  position: relative;
  display: inline-grid;
  place-items: center;
  flex: none;
  width: var(--s);
  height: var(--s);
  border-radius: 50%;
  background: var(--c-500);
  box-shadow:
    inset 0 calc(var(--s) * -0.08) calc(var(--s) * 0.09) rgba(var(--c-900-rgb), 0.32),
    inset 0 calc(var(--s) * 0.03) 0 rgba(255, 255, 255, 0.3);
  font-style: normal;
}
.lball.odd {
  background: var(--c-600);
}
.lball::after {
  content: "";
  position: absolute;
  left: 16%;
  top: 9%;
  width: 20%;
  height: 12%;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.92);
}
.lball > b {
  display: grid;
  place-items: center;
  width: 62%;
  height: 62%;
  border-radius: 50%;
  background: #fff;
  box-shadow: inset 0 calc(var(--s) * -0.025) 0 rgba(var(--c-900-rgb), 0.12);
  font: 800 calc(var(--s) * 0.44) / 1 var(--font-latin);
  color: var(--ink);
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
.tube-edge {
  stroke: var(--c-400);
}
/* A touch of coral over the white page, then a white veil, so the glass shows on the page and on the cabinet alike. */
.tube-tint {
  stroke: rgba(var(--c-500-rgb), 0.12);
}
.tube-glass {
  stroke: rgba(255, 255, 255, 0.5);
}
.tube-shine {
  stroke: #fff;
  stroke-width: 2;
  opacity: 0.9;
}
.stand {
  position: relative;
  z-index: 3;
  display: flex;
  flex-direction: column;
  align-items: center;
}
/* The glass: nearly clear, a crisp outline with a white rim inside it, a reflection arc over the balls. */
.globe {
  --globe: 140px;
  --ball: 27px;
  position: relative;
  z-index: 1;
  width: var(--globe);
  height: var(--globe);
  border-radius: 50%;
  background: rgba(255, 250, 247, 0.94);
  box-shadow:
    0 0 0 2px var(--c-300),
    inset 0 0 0 2px #fff,
    inset 0 -12px 16px -12px rgba(var(--c-500-rgb), 0.35);
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
  stroke-width: 3.2;
  stroke-linecap: round;
}
.glass .far {
  stroke-width: 2;
  opacity: 0.7;
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
/* The base the globe sits in: a coral block with its thickness showing below. */
.base {
  position: relative;
  width: 64%;
  height: 18px;
  margin-top: -9px;
  border-radius: 9px 9px 5px 5px;
  background: linear-gradient(180deg, var(--c-400), var(--c-500));
  box-shadow: inset 0 2px 0 rgba(255, 255, 255, 0.45), 0 5px 0 var(--c-600);
}
/* The cabinet: the track runs in its top band, the windows under it. */
.cabinet {
  margin-top: 5px;
  padding: 37px 14px 12px;
  border-radius: 20px;
  background: var(--grad-sky);
  box-shadow:
    inset 0 2px 0 rgba(255, 255, 255, 0.35),
    0 12px 24px -16px rgba(var(--shadow-rgb), 0.45);
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
  box-shadow: inset 0 3px 6px rgba(var(--c-900-rgb), 0.2), 0 1px 0 rgba(255, 255, 255, 0.35);
  transition: background var(--dur-slow), box-shadow var(--dur-slow);
}
/* The draw lights the windows up: white, ringed, each with a cup for its ball. */
.keys.drum .key-col {
  background: var(--surface);
  box-shadow: inset 0 0 0 3px var(--c-300), 0 0 16px 3px rgba(255, 255, 255, 0.7);
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
  box-shadow: inset 0 2px 4px rgba(var(--c-900-rgb), 0.12);
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
/* The small keys on a number key's top and bottom edge: one digit up, one down. */
.step {
  --key-lip-h: 2px;
  position: absolute;
  left: 50%;
  z-index: 1;
  width: 40px;
  height: 20px;
  margin-left: -20px;
  padding: 0;
  border-radius: var(--radius-s);
  color: var(--ink-3);
  transition:
    transform var(--dur-release) var(--ease-spring),
    box-shadow var(--dur-release) var(--ease-spring),
    color var(--dur-fast),
    opacity var(--dur-base);
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
  bottom: 0;
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

/* A spinning key: a window onto a column of digits, the two in view placed by script; the edges fall away like a drum. */
.reel {
  position: absolute;
  inset: 0;
  overflow: hidden;
  border-radius: inherit;
  mask: linear-gradient(180deg, transparent, #000 22%, #000 78%, transparent);
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

/* ---- the tray: my stubs in a grid of five, the empty places pale, the count bought at the end of the first row */
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
.cell :deep(.paper) {
  width: 62px;
  min-width: 0;
  padding: 0 7px 0 calc(var(--tab) + 6px);
}
/* Bought, waiting for the number to leave the keys. */
.cell.held :deep(.ticket-stub) {
  opacity: 0;
}
/* Drawn and matching nothing: the stub steps back. */
.cell.out {
  opacity: 0.45;
}
.slot {
  border-radius: var(--radius-s);
  background: var(--c-100);
}
.digit {
  display: inline-block;
}
/* Drawn: what matched is coral, the rest steps back. */
.drawn .digit {
  color: var(--ink-3);
}
.drawn .digit.on,
.past-stubs .digit.on {
  color: var(--c-700);
}
/* What a stub won, on its corner. */
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
  background: var(--c-400);
  box-shadow: 0 0 0 2px var(--surface), 0 0 12px 2px rgba(var(--c-500-rgb), 0.7);
  color: var(--ink);
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
 * ---- the side: the pool on coral, then the board of the latest draws. It takes the height the machine and the tray
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
.pool-card {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 14px 14px 16px;
  border-radius: var(--radius-l);
  background: var(--grad-sky);
  box-shadow: inset 0 2px 0 rgba(255, 255, 255, 0.35);
  color: var(--ink);
}
.pool-head {
  display: flex;
  align-items: baseline;
  gap: 6px;
}
.tier-name {
  font: 800 var(--fs-label)/1 var(--font);
  white-space: nowrap;
}
.pool-head .tier-name {
  font-size: var(--fs-section);
}
.pool-head small {
  font: 700 var(--fs-label)/1 var(--font);
  white-space: nowrap;
}
.pool-head .match {
  align-self: center;
  margin-left: auto;
}
.pool-amount {
  display: flex;
  align-items: center;
  gap: 4px;
  font: 800 50px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.tiers {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.tiers li {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  padding: 8px 10px 9px;
  border-radius: var(--radius-m);
  background: var(--surface);
}
.tier-head {
  display: flex;
  align-items: center;
  gap: 6px;
}
/* The number's three digits: a ball where the digit must match, an empty slot where it need not. */
.match {
  display: inline-flex;
  gap: 3px;
}
.match .lball {
  --s: 12px;
}
.match .hole {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: rgba(var(--c-900-rgb), 0.1);
}
/* On the coral card the balls are white. */
.pool-head .match .lball {
  --s: 15px;
  background: var(--surface);
}
.amount {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font: 800 22px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.amount svg {
  color: var(--c-700);
}
.amount small {
  margin-left: 2px;
  font: 600 var(--fs-caption) var(--font);
  color: var(--ink-2);
}

/* The board: a header strip, then one draw a row, the newest on white. */
.board {
  flex: 0 1 auto;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
  border-radius: var(--radius-l);
  background: var(--c-50);
}
.board-head,
.rows li {
  display: grid;
  grid-template-columns: 4.6em 98px 22px minmax(0, 1fr) auto;
  align-items: center;
  column-gap: 6px;
  padding: 0 12px;
}
.board-head {
  flex: none;
  height: 30px;
  background: var(--c-100);
  font: 700 var(--fs-caption)/1 var(--font);
  color: var(--ink-2);
}
.board-head span:nth-child(2) {
  grid-column: 2 / span 2;
}
.board-head span:nth-child(3) {
  grid-column: 4 / span 2;
}
/* The rows fade out at the bottom edge, where they scroll under it. */
.rows {
  min-height: 0;
  margin: 0;
  padding: 0 0 12px;
  overflow-y: auto;
  list-style: none;
  mask: linear-gradient(180deg, #000 calc(100% - 12px), transparent);
}
.rows li {
  min-height: 32px;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.rows li:first-child {
  min-height: 46px;
  background: var(--surface);
  color: var(--ink);
}
.balls {
  display: inline-flex;
  gap: 3px;
}
/* The draw's balls: the machine's balls, small. */
.balls .lball {
  --s: 25px;
}
.rows li:first-child .balls {
  gap: 4px;
}
.rows li:first-child .balls .lball {
  --s: 30px;
}
.day {
  white-space: nowrap;
}
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
.rows .won {
  font: 800 15px/1 var(--font-latin);
  color: var(--c-700);
  white-space: nowrap;
}
/* Held back while the draw plays on the keys. */
.rows li.unseen .balls,
.rows li.unseen .proof-key,
.rows li.unseen .winners,
.rows li.unseen .won,
.result.hide {
  visibility: hidden;
}
.proof-key {
  width: 22px;
  height: 22px;
  padding: 0;
  color: var(--ink-3);
}
.proof-key.bad,
.proof-key.bad:hover:not(:disabled),
.proof-key.bad[aria-expanded="true"]:not(:disabled) {
  color: var(--bad);
}

/* ---- the bottom bar: 往期 on a narrow panel or with the last draw's stubs aside, my result, the buy keys */
.past-key {
  gap: 4px;
  padding: 0 11px 0 9px;
}
.past-key:not(.aside) {
  display: none;
}
.past-key svg {
  color: var(--c-700);
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

/* Pop-ups: the full list rises from the bar, the proof from the bottom of the side. */
.pop {
  position: absolute;
  z-index: 3;
  margin: 0;
  padding: 14px 16px;
  box-sizing: border-box;
  overflow-y: auto;
  border-radius: var(--radius-m);
  background: var(--surface);
  box-shadow: var(--shadow-paper), 0 10px 28px -12px rgba(var(--c-900-rgb), 0.3);
}
.proof {
  right: 0;
  bottom: 0;
  width: max(100%, 280px);
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.proof > div {
  display: flex;
  gap: 8px;
  min-width: 0;
}
.proof dt {
  flex: none;
  width: 40px;
  font-size: var(--fs-caption);
  font-weight: 700;
  color: var(--ink-3);
}
.proof dd {
  min-width: 0;
  margin: 0;
  font: 500 var(--fs-caption)/1.4 ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  color: var(--ink-2);
  overflow-wrap: anywhere;
  user-select: text;
}
.past {
  left: 16px;
  bottom: calc(100% + 8px);
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 420px;
  max-width: calc(100% - 32px);
  max-height: 240px;
}
/* My stubs of the last draw, on a tinted strip above the list. */
.past-stubs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 0;
  padding: 10px 12px;
  border-radius: var(--radius-s);
  background: var(--c-100);
  list-style: none;
}
.past-stubs .digit {
  color: var(--ink-3);
}
/* One draw a row: the day, the number, the top prize winners, my result. */
.history {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0 2px;
  list-style: none;
}
.history li {
  display: grid;
  grid-template-columns: 4.6em 3em minmax(0, 1fr) auto;
  align-items: baseline;
  gap: 12px;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-3);
}
.history b {
  font: 800 var(--fs-number)/1 var(--font-latin);
  letter-spacing: 0.08em;
  color: var(--ink-2);
}
.history .won.on {
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: var(--c-700);
}

/* ---- the first showing of a draw: each digit of my stubs lights as the key above it comes to rest; once all three
 * rest, the balls drop onto the board right to left and the stamps go down. */
.reveal .drawn .digit.on {
  animation: digit-lit 360ms var(--ease-out) both;
}
@keyframes digit-lit {
  from { color: var(--ink-3); }
  45% { transform: translateY(-4px) scale(1.18); }
  to { color: var(--c-700); }
}
.reveal .balls.in i {
  animation: ball-in 420ms var(--ease-pop) both;
  animation-delay: calc((2 - var(--i)) * 90ms);
}
@keyframes ball-in {
  from { transform: translateY(-24px); opacity: 0; }
  40% { opacity: 1; }
}
.reveal .stamp,
.reveal .result.in {
  animation: stamp-in 360ms var(--ease-pop) both;
}
@keyframes stamp-in {
  from { transform: scale(1.7); opacity: 0; }
}
.calm .cell,
.calm .step,
.calm .key-col {
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
  .past-key:not(.aside) {
    display: inline-flex;
  }
  .globe {
    --globe: 104px;
    --ball: 21px;
  }
  .base {
    height: 14px;
    margin-top: -7px;
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
  .pool-card {
    gap: 6px;
    padding: 10px 12px;
  }
  .pool-head .tier-name {
    font-size: var(--fs-strong);
  }
  .pool-head .match i {
    width: 11px;
    height: 11px;
  }
  .pool-amount {
    font-size: 32px;
  }
  .pool-amount svg {
    width: 20px;
    height: 20px;
  }
  .tiers {
    grid-template-columns: 1fr;
    gap: 4px;
  }
  .tiers li {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    padding: 5px 8px;
  }
  .tiers .match {
    display: none;
  }
  .tiers .amount {
    font-size: 17px;
  }
  .board-head,
  .rows li:not(:first-child) {
    display: none;
  }
  .rows {
    overflow: visible;
    padding: 0;
  }
  /* The latest draw on one line: its day, the balls and the proof; who won is in 往期. */
  .rows {
    mask: none;
  }
  .rows li:first-child {
    grid-template-columns: minmax(0, 1fr) auto 22px;
    min-height: 0;
    padding: 8px 8px 8px 10px;
  }
  .rows li:first-child .winners,
  .rows li:first-child .won {
    display: none;
  }
  .rows li:first-child .balls i {
    width: 26px;
    height: 26px;
    font-size: 18px;
  }
  .tray {
    padding: 10px 10px 10px 12px;
  }
  /* The bar stays one row: 往期 keeps its mark, the keys their price, the win its number. */
  .park-actions {
    gap: 8px;
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
  .park-actions {
    padding-left: 12px;
    padding-right: 12px;
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

/* Short panel: the globe beside smaller keys, the pool's amount beside its tiers; the body scrolls, the bar stays. */
@container panel (max-height: 560px) {
  .stage {
    --tray-h: 106px;
    align-content: start;
    gap: 10px 20px;
    padding: 10px 16px 12px;
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
  .stubs {
    row-gap: 10px;
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
  .pool-card {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    grid-template-areas:
      "head head"
      "amount tiers";
    align-items: center;
    gap: 6px 12px;
    padding: 10px 12px;
  }
  .pool-head {
    grid-area: head;
  }
  .pool-head .tier-name {
    font-size: var(--fs-strong);
  }
  .pool-amount {
    grid-area: amount;
    font-size: 38px;
  }
  .pool-amount svg {
    width: 22px;
    height: 22px;
  }
  .tiers {
    grid-area: tiers;
    grid-template-columns: 1fr;
    gap: 4px;
  }
  .tiers li {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    padding: 5px 8px;
  }
  .tiers .match {
    display: none;
  }
  .tiers .amount {
    font-size: 17px;
  }
  .rows li {
    min-height: 30px;
  }
  .rows li:first-child {
    min-height: 40px;
  }
  .rows li:first-child .balls i {
    width: 26px;
    height: 26px;
    font-size: 18px;
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
  .pool-card {
    display: flex;
    align-items: stretch;
  }
  .stage {
    gap: 10px 14px;
    padding: 10px 16px 12px;
  }
  .pool-amount {
    font-size: 28px;
  }
  .pool-amount svg {
    width: 18px;
    height: 18px;
  }
  .rows li:first-child {
    row-gap: 4px;
    padding: 6px 10px 7px;
  }
}
</style>
