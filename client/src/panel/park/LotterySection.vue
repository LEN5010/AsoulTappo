<script setup lang="ts">
// 每日夺宝 (docs/design/amusement-park.md §7, §11; docs/design/park-ui-rebuild.md §5.4): the prize board (the top
// prize on gold foil: the server-wide pool, which rolls over until a draw has a top winner; then the second and the third), three number keys to pick a number, my stubs of the day, and in the bottom bar the last draw with its hash
// check and the buy keys. There is no push: while the page is open the state loads every POLL_MS, and every few
// seconds once the close or the draw is due. The countdown and 阿草 go up in the park's coral band (band.ts).
// The number keys double as reels: 机选 spins them onto the number bought, and a draw's first showing spins them onto
// the drawn number, one digit at a time from the right.
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch, type Ref } from "vue";
import { online, status } from "../../stores/player";
import { park, parkTry } from "../../stores/park";
import { reducedMotion } from "../../stores/theme";
import { ACHAO } from "../../ui/achao";
import Icon from "../../ui/Icon.vue";
import { EASE_IN_OUT, EASE_OUT } from "../../ui/motion";
import { useBand } from "./band";
import { COIN_SMALL } from "./coin";
import {
  cleanNumber, countdown, dayBefore, dropDigit, markDrawSeen, nextDraw, NO_PICKS, pickedNumber, pickLabel, pickTarget,
  putDigit, reelDigit, revealDigits, salesOpen, seenDraw, shortDay, stepDigit, verifyDraw, winnersLine, type LotteryBuy,
  type LotteryState, type LotteryTier, type Picks,
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
/** The number's flight from the keys into its stub; the other stubs bought with it follow this far apart. */
const FLY_MS = 560;
const DROP_MS = 480;
const DROP_STAGGER_MS = 70;
/** A draw's first showing: the last digit starts slowing DRAW_FIRST_MS in, each digit to its left DRAW_GAP_MS later.
 * The stamps go down DRAW_STAMP_MS after the first digit rests; the keys go back no sooner than DRAW_HOLD_MS after that. */
const DRAW_FIRST_MS = 520;
const DRAW_GAP_MS = 700;
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
  const label = waiting.value ? "开奖中" : s?.drawn ? "明日 22:00 开奖" : "22:00 开奖";
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
/** Today is drawn: the keys show the drawn number and cannot be pressed. */
const showDraw = computed(() => !!state.value?.drawn && drawnHere.value);
const faces = computed<readonly string[]>(() => (showDraw.value ? winning.value : picks.value));
/** Keys stay pressable while coins are short: picking is free, only the pick key waits. */
const keysOff = computed(() => !online.value || closed.value || state.value?.left === 0);
/** Something is playing on the keys or a number is being bought: the keys take no input. */
const locked = computed(() => !!busy.value || !!reeling.value || !!reveal.value);
/** The keys as the draw's window: sunk into the tray, the digits coral once at rest. */
const drum = computed(() => reeling.value === "draw" || (showDraw.value && !reeling.value));
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
const reeling = ref<"" | "buy" | "draw">("");
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
/** Starts the three keys spinning from [from]; [plan] gives each its stop (ms after the start) and digit. */
function startReels(from: readonly string[], mode: "buy" | "draw", plan?: { at: number[]; land: readonly string[] }) {
  const g = gen;
  reeling.value = mode;
  reels = [0, 1, 2].map((i) => ({
    pos: 0, from: from[i] ?? "", stopAt: null, land: "", end: 0, p0: 0, t0: 0, ms: 0, done: false, shown: [-1, -1],
  }));
  onLand = () => {};
  onRest = () => {};
  reelStart = performance.now();
  // The reel windows are in the DOM after this render.
  void nextTick(() => {
    if (g !== gen) return;
    reelCells = Array.from(keysEl.value?.querySelectorAll(".reel") ?? [], (el) => Array.from(el.children) as HTMLElement[]);
    reelStart = lastFrame = performance.now();
    if (plan) reels.forEach((r, i) => {
      r.stopAt = reelStart + plan.at[i]!;
      r.land = plan.land[i] ?? "";
    });
    reels.forEach((_, i) => paint(i));
    reelFrame = requestAnimationFrame(spin);
  });
}
/** 机选: the spinning keys stop on [digits] left to right, no sooner than BUY_SPIN_MS after they started. */
function stopReels(digits: readonly string[], rest: () => void) {
  const t = Math.max(performance.now(), reelStart + BUY_SPIN_MS);
  reels.forEach((r, i) => {
    r.stopAt = t + i * BUY_STOP_GAP_MS;
    r.land = digits[i] ?? "";
  });
  onLand = press;
  onRest = rest;
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

// ---- a number bought leaves the keys: its digits fly into the new stub, which grows out of the keys around them.
// A spot is the centre of a digit and its font size; the spots on the keys are kept from the keys' top left corner,
// since the keys can move between the purchase and the flight (the table under them may change its rows).
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
  const keys = keysEl.value?.getBoundingClientRect();
  const stubs = Array.from(stubsEl.value?.querySelectorAll<HTMLElement>(".cell.fresh .ticket-stub") ?? []);
  const main = stubs[stubs.length - 1];
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
  root.querySelectorAll<HTMLElement>(".ghost").forEach((el, j) => {
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
  if (spinning) startReels(base, "buy");
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

// ---- the prize board: top, second and third, each with the trailing digits it takes. The top prize is the
// server-wide pool of the next draw (after today's draw, the pool it rolled over into or started again from). The
// park's state carries the same pool and loads again on every coin spent anywhere in the park, so the board takes it
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
/** Free places, while there is still a draw to buy for and today's stubs are on the table. */
const slots = computed(() => (state.value && !lastOnTable.value ? Math.max(0, state.value.daily - table.value.length) : 0));

/** The server's drawn days with their top prize winners, each with what I won that day (null: I had no tickets). */
const past = computed(() => {
  const s = state.value;
  if (!s) return [];
  const mine = new Map(s.history.map((h) => [h.day, h.won]));
  return s.draws.map((d) => ({ ...d, winners: winnersLine(d.top), won: mine.get(d.day) ?? null }));
});
/** The last draw's stubs when they are not on the table (today's stubs are): they go on top of 往期. */
const lastAside = computed(() => (!lastOnTable.value && last.value?.mine.length ? last.value : null));
const hasPast = computed(() => !!lastAside.value || past.value.length > 0);

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
  startReels(picks.value, "draw", {
    at: [0, 1, 2].map((i) => DRAW_FIRST_MS + (2 - i) * DRAW_GAP_MS),
    land: d.number.split(""),
  });
  onLand = () => stopped.value++;
  onRest = () => later(DRAW_STAMP_MS, () => {
    stamped.value = true;
    const best = d.mine.some((t) => t.tier === "top") ? 3 : d.mine.some((t) => t.tier === "second") ? 2 : 1;
    const ms = d.won > 0 ? ROLL_MS[best] : 0;
    if (ms) stopWon = countTo(wonShown, d.won, ms);
    later(Math.max(ms, DRAW_HOLD_MS), () => {
      endReels(showDraw.value ? "still" : "fade");
      reveal.value = "";
      stopped.value = 3;
    });
  });
}
watch(() => [active.value, last.value?.day ?? ""] as const, ([on, day]) => {
  if (!on || !day || seenDraw() === day) return;
  markDrawSeen(day);
  if (!calm.value) startReveal(day);
}, { immediate: true });
// The drawn number gives the keys back to a new day softly.
watch(showDraw, (on) => { if (!on && !reeling.value) faceIn.value = "fade"; });

// ---- the bar's two pop-ups (pop, above): the proof of the draw, and the earlier days
const barEl = ref<HTMLElement>();
function toggle(p: "proof" | "past") {
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
function onBarKey(e: KeyboardEvent) {
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
        <!-- The prize board: the top prize on gold foil, the second and the third beside it. The balls are the
             number's three digits: a coral ball where the digit must match, an empty slot where it need not. -->
        <ol class="prizes">
          <li class="tier top" :aria-label="`头奖 全服奖池 ${fmt(pool ?? 0)}`">
            <span class="tier-head" aria-hidden="true">
              <span class="tier-name">头奖</span>
              <small class="pool">全服奖池</small>
            </span>
            <b class="amount" aria-hidden="true"><Icon name="shard" :size="26" />{{ fmt(poolShown) }}</b>
            <span class="match" aria-hidden="true"><i v-for="(on, j) in needs(3)" :key="j" :class="{ on }"></i></span>
          </li>
          <li class="tier second" :aria-label="`二等 ${fmt(state.prize.second)}`">
            <span class="tier-name" aria-hidden="true">二等</span>
            <span class="match" aria-hidden="true"><i v-for="(on, j) in needs(2)" :key="j" :class="{ on }"></i></span>
            <b class="amount" aria-hidden="true"><Icon name="shard" :size="16" />{{ fmt(state.prize.second) }}</b>
          </li>
          <li class="tier third" :aria-label="`三等 ${fmt(state.prize.third)} /注`">
            <span class="tier-name" aria-hidden="true">三等</span>
            <span class="match" aria-hidden="true"><i v-for="(on, j) in needs(1)" :key="j" :class="{ on }"></i></span>
            <b class="amount" aria-hidden="true"><Icon name="shard" :size="16" />{{ fmt(state.prize.third) }}<small>/注</small></b>
          </li>
        </ol>

        <!-- The keys take clicks, the wheel and their ▲/▼ keys; the keyboard goes to the hidden field under them. -->
        <div ref="keysEl" class="keys" :class="[faceIn, { drum }]">
          <div v-for="(d, i) in faces" :key="i" class="key-col">
            <button
              type="button" class="ui-btn numkey" tabindex="-1" aria-hidden="true"
              :class="{ on: at === i, down: pressed[i], target: target === i, drum }"
              :disabled="keysOff || drum" :style="{ '--from': stepped[i]! > 0 ? '12px' : '-10px' }"
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
          </div>
          <input
            ref="field" class="field" type="text" inputmode="numeric" autocomplete="off" aria-label="号码"
            :disabled="keysOff" @input="onType" @keydown="onKey" @focus="typing = true" @blur="typing = false; at = null"
          />
        </div>

        <ol ref="stubsEl" class="stubs" :class="{ drawn: lastOnTable }" aria-label="我的号码">
          <li
            v-for="(t, i) in table" :key="`${tableDay}-${i}`" class="cell"
            :class="{
              fresh: fresh.includes(i), held: held && fresh.includes(i),
              out: lastOnTable && revealDigits(t.tier, stopped).out,
            }"
          >
            <TicketStub>
              <span
                v-for="(c, j) in digits(t.number, t.tier, lastOnTable ? stopped : 3)" :key="j" class="digit"
                :class="{ on: c.hit }"
              >{{ c.d }}</span>
            </TicketStub>
            <b v-if="t.prize && stamped" class="stamp" :class="{ top: t.tier === 'top' }">+{{ fmt(t.prize) }}</b>
          </li>
          <li v-for="i in slots" :key="`slot-${i}`" class="cell slot" aria-hidden="true"></li>
        </ol>
      </template>
    </div>

    <!-- The digits of a number bought, on their way from the keys into its stub. -->
    <span
      v-for="g in ghosts" :key="g.id" class="ghost" aria-hidden="true"
      :style="{ left: `${g.x}px`, top: `${g.y}px`, fontSize: `${g.size}px` }"
    >{{ g.d }}</span>

    <div v-if="state" ref="barEl" class="park-actions" @keydown="onBarKey">
      <div v-if="last" class="last">
        <span class="when">{{ lastName }}</span>
        <span
          class="balls" :class="{ hide: !!reveal && stopped < 3, in: !!reveal && stopped === 3 }"
          :aria-label="`开奖号码 ${last.number}`"
        >
          <i v-for="(d, i) in winning" :key="i" :style="{ '--i': i }">{{ d }}</i>
        </span>
        <button
          v-if="verified !== null" type="button" class="ui-btn ghost small proof-key" :class="{ bad: !verified }"
          :title="verified ? '已校验' : '校验不符'" :aria-expanded="pop === 'proof'" @click="toggle('proof')"
        >
          <Icon :name="verified ? 'check' : 'info'" :size="14" /><span>{{ verified ? "已校验" : "校验不符" }}</span>
        </button>
        <span class="result" :class="{ won: last.won > 0, hide: !stamped, in: !!reveal && stamped }">
          <template v-if="last.won > 0"><Icon name="shard" :size="16" />+{{ fmt(reveal ? wonShown : last.won) }}</template>
          <template v-else-if="last.mine.length">未中奖</template>
        </span>
      </div>
      <button
        v-if="hasPast" type="button" class="ui-btn ghost small" :aria-expanded="pop === 'past'" @click="toggle('past')"
      >往期</button>

      <dl v-if="pop === 'proof' && last" class="pop proof">
        <div><dt>哈希</dt><dd>{{ last.hash }}</dd></div>
        <div><dt>随机串</dt><dd>{{ last.salt }}</dd></div>
      </dl>
      <div v-if="pop === 'past'" class="pop past ui-scroll">
        <ul v-if="lastAside" class="past-stubs">
          <li v-for="(t, i) in lastAside.mine" :key="i">
            <TicketStub size="s">
              <span v-for="(c, j) in digits(t.number, t.tier)" :key="j" class="digit" :class="{ on: c.hit }">{{ c.d }}</span>
            </TicketStub>
          </li>
        </ul>
        <!-- Each draw: its day, its number, who won the top prize, and what I won. -->
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
.stage {
  flex: 1 0 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 24px;
  padding: 22px 22px 26px;
}
/* Nothing loaded: the error is the sheet's first line. */
.stage.empty {
  justify-content: flex-start;
}
.stage > .ui-error {
  align-self: stretch;
  margin: 0;
}

/*
 * ---- the prize board: one plaque. The top prize on gold foil fills the left, the second and the third take a row
 * each on the right, one step of the ramp apart. Plaques are read, not pressed: no edge under them.
 */
.prizes {
  display: grid;
  grid-template-columns: auto auto;
  grid-template-rows: 1fr 1fr;
  margin: 0;
  padding: 0;
  list-style: none;
  border-radius: var(--radius-m);
  overflow: hidden;
  color: var(--ink);
}
.tier {
  display: flex;
  align-items: center;
  gap: 10px;
  box-sizing: border-box;
}
.tier.top {
  grid-row: span 2;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  gap: 6px;
  padding: 12px 24px 14px 20px;
  background: var(--grad-gold);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.6), inset 0 -2px 0 rgba(var(--c-900-rgb), 0.14);
}
.tier.second,
.tier.third {
  padding: 0 18px 0 16px;
}
.tier.second {
  background: var(--c-300);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.5);
}
.tier.third {
  background: var(--c-100);
}
.tier-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.tier-name {
  font: 800 var(--fs-label)/1 var(--font);
  white-space: nowrap;
}
.tier.top .tier-name {
  font-size: var(--fs-body);
}
.pool {
  font: 700 var(--fs-caption)/1 var(--font);
  color: var(--ink-2);
  white-space: nowrap;
}
/* The number's three digits: a coral ball where the digit must match, an empty slot where it need not. */
.match {
  display: inline-flex;
  gap: 3px;
}
.match i {
  width: 13px;
  height: 13px;
  border-radius: 50%;
  background: rgba(var(--c-900-rgb), 0.1);
  box-shadow: inset 0 1px 2px rgba(var(--c-900-rgb), 0.2);
}
.match i.on {
  background: radial-gradient(circle at 34% 28%, var(--c-300), var(--c-500) 52%, var(--c-600));
  box-shadow: inset 0 -1px 2px rgba(var(--c-900-rgb), 0.18);
}
.amount {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin-left: auto;
  font: 800 20px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.tier.top .amount {
  gap: 4px;
  margin-left: 0;
  font-size: 46px;
}
.tier.second .amount {
  font-size: 26px;
}
.tier:not(.top) .amount svg {
  color: var(--c-700);
}
.amount small {
  margin-left: 3px;
  font: 600 var(--fs-caption) var(--font);
  color: var(--ink-2);
}
.tier:not(.top) .tier-name {
  width: 2.2em;
}
.tier:not(.top) .amount {
  min-width: 64px;
  justify-content: flex-end;
  padding-left: 12px;
}

/* ---- the number keys: three tall keycaps; typing presses them */
/* On a tonal tray: white keys need a step of the ramp under them to read as keys. */
.keys {
  position: relative;
  display: flex;
  gap: 14px;
  padding: 14px 16px 18px;
  border-radius: var(--radius-l);
  background: var(--c-100);
}
.key-col {
  position: relative;
  display: flex;
}
.numkey {
  --key-lip-h: 4px;
  width: 88px;
  height: 112px;
  padding: 0;
  border-radius: var(--radius-l);
}
.numkey.down:not(:disabled) {
  --key-y: 4px;
  --key-lip-h: 0px;
  transition-duration: var(--dur-press);
  transition-timing-function: ease-out;
}
/* Latched (the key being changed): a step deeper than the tray it sits on. */
.numkey.on:not(:disabled) {
  --key-top: var(--c-200);
  --key-bottom: var(--c-200);
  --key-lip: var(--c-300);
}
/* Disabled keys stay a shade off the tray. */
.numkey:disabled {
  --key-top: var(--c-50);
  --key-bottom: var(--c-50);
}
.numkey:disabled .face {
  color: var(--ink-3);
}
/* The draw's window: the keys sink into the tray, white, and the digits at rest are coral. */
.numkey.drum:disabled {
  --key-top: var(--surface);
  --key-bottom: var(--surface);
}
.numkey.drum:disabled .face {
  color: var(--c-700);
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
  top: -10px;
}
.step.up svg {
  rotate: 180deg;
}
.step.down {
  bottom: -12px;
}
/* Off with the sales they would sit flat on the tray; the draw's window has none. */
.step:disabled {
  opacity: 0;
  pointer-events: none;
}
.keys.drum .step {
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
  font: 800 72px/1 var(--font-latin);
  color: var(--ink);
  animation: face-in 200ms var(--ease-pop) both;
}
/* A stepped digit comes in from the side it was stepped from; a typed one from above. */
@keyframes face-in {
  from { transform: translateY(var(--from, -10px)) scale(0.8); opacity: 0; }
}
/* A blank key: a short line where its digit goes. */
.blank,
.rc.void::after {
  width: 28px;
  height: 4px;
  margin-top: 46px;
  border-radius: 2px;
  background: var(--c-200);
}
.caret {
  position: absolute;
  left: 50%;
  top: 28px;
  width: 3px;
  height: 52px;
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
  font: 800 72px/1 var(--font-latin);
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
.drum .rc.landed {
  color: var(--c-700);
}
/* A digit of a number bought, between the keys and its stub. */
.ghost {
  position: absolute;
  z-index: 3;
  font-family: var(--font-latin);
  font-weight: 800;
  line-height: 1;
  color: var(--ink);
  transform: translate(-50%, -50%);
  pointer-events: none;
}

/* ---- my stubs: 2 rows of 5; a place still free is a dashed outline */
.stubs {
  display: grid;
  grid-template-columns: repeat(5, 96px);
  gap: 14px 16px;
  justify-content: center;
  margin: 0;
  padding: 0;
  list-style: none;
}
.cell {
  position: relative;
  display: flex;
  height: 56px;
  transition: opacity var(--dur-slow) var(--ease-out);
}
.cell :deep(.ticket-stub),
.cell :deep(.paper) {
  width: 100%;
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
  box-sizing: border-box;
  border: 2px dashed var(--c-200);
  border-radius: var(--radius-s);
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
.stamp {
  position: absolute;
  top: -11px;
  right: -9px;
  padding: 3px 6px 2px;
  border: 2px solid var(--c-600);
  border-radius: var(--radius-s);
  background: var(--surface);
  font: 800 17px/1 var(--font-latin);
  color: var(--c-700);
  rotate: -9deg;
  white-space: nowrap;
}
.stamp.top {
  border-color: color-mix(in oklab, var(--gold) 78%, var(--c-700));
  background: var(--grad-gold);
  color: var(--ink);
}

/* ---- the bottom bar: the last draw on the left, the buy keys on the right */
.last {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.when {
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.balls {
  display: inline-flex;
  gap: 5px;
}
/* Lottery balls: coral spheres with a soft light at the upper left. */
.balls i {
  display: inline-grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: radial-gradient(circle at 34% 28%, var(--c-300), var(--c-500) 52%, var(--c-600));
  box-shadow: inset 0 -2px 3px rgba(var(--c-900-rgb), 0.18);
  font: 800 26px/1 var(--font-latin);
  font-style: normal;
  color: #fff;
}
/* Held back while the draw plays on the keys. */
.balls.hide,
.result.hide {
  visibility: hidden;
}
.proof-key {
  gap: 3px;
  padding: 0 8px;
  color: var(--ink-3);
}
.proof-key.bad,
.proof-key.bad:hover:not(:disabled),
.proof-key.bad[aria-expanded="true"]:not(:disabled) {
  color: var(--bad);
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
  font: 800 var(--fs-title)/1 var(--font-latin);
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

/* Pop-ups rise from the bar over the page. */
.pop {
  position: absolute;
  left: 16px;
  bottom: calc(100% + 8px);
  z-index: 3;
  max-width: min(460px, calc(100% - 32px));
  max-height: 240px;
  margin: 0;
  padding: 14px 16px;
  box-sizing: border-box;
  overflow-y: auto;
  border-radius: var(--radius-m);
  background: var(--surface);
  box-shadow: var(--shadow-paper), 0 10px 28px -12px rgba(var(--c-900-rgb), 0.3);
}
.proof {
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
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 420px;
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
.winners {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--ink);
}
.winners.none {
  color: var(--ink-3);
}
.history .won.on {
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: var(--c-700);
}

/* ---- the first showing of a draw: each digit of my stubs lights as the key above it comes to rest; once all three
 * rest, the balls drop into the bar right to left and the stamps go down. */
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
  from { transform: translate(14px, -46px); opacity: 0; }
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
.calm .step {
  transition: none;
}

/* The buy keys carry their price: near the narrowest panel the proof key keeps only its mark, so the bar stays one row. */
@container panel (max-width: 1100px) {
  .proof-key > span {
    display: none;
  }
}

@container panel (max-width: 760px) {
  .stage {
    gap: 20px;
  }
  .tier.top {
    padding: 10px 18px 12px 16px;
  }
  .tier.top .amount {
    font-size: 38px;
  }
  .tier.second,
  .tier.third {
    padding: 0 14px 0 12px;
  }
  .tier.second .amount {
    font-size: 22px;
  }
  .numkey {
    width: 64px;
    height: 84px;
    border-radius: var(--radius-m);
  }
  .face,
  .rc {
    font-size: 54px;
  }
  .blank,
  .rc.void::after {
    width: 22px;
    margin-top: 34px;
  }
  .caret {
    top: 20px;
    height: 40px;
  }
  .step {
    width: 34px;
    height: 18px;
    margin-left: -17px;
  }
  .step.up {
    top: -9px;
  }
  .step.down {
    bottom: -11px;
  }
  .stubs {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    max-width: 560px;
  }
  .stubs {
    gap: 12px;
  }
  .cell {
    width: 88px;
  }
  .keys {
    gap: 10px;
    padding: 12px 12px 16px;
  }
  .when {
    display: none;
  }
}

/* Short panel: the board and the keys side by side, the stubs under them; the body scrolls, the bar stays. */
@container panel (max-height: 560px) {
  .stage {
    flex-direction: row;
    flex-wrap: wrap;
    align-content: flex-start;
    gap: 16px 24px;
    padding: 16px 16px 18px;
  }
  .tier.top {
    gap: 4px;
    padding: 10px 18px 12px 14px;
  }
  .tier.top .amount {
    font-size: 32px;
  }
  .tier.top .amount svg {
    width: 20px;
    height: 20px;
  }
  .tier.second,
  .tier.third {
    min-height: 40px;
    padding: 0 12px;
  }
  .tier.second .amount {
    font-size: 20px;
  }
  .tier.third .amount {
    font-size: 17px;
  }
  .match i {
    width: 11px;
    height: 11px;
  }
  .stubs,
  .stage > .ui-error {
    flex: 1 0 100%;
  }
  .balls i {
    width: 32px;
    height: 32px;
    font-size: 21px;
  }
  .proof-key > span {
    display: none;
  }
  .result.won {
    font-size: var(--fs-heading);
  }
}
</style>
