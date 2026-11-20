<script setup lang="ts">
// The dou dizhu table, the face of its own window (DdzApp.vue; the browser preview floats it over the desk page,
// pet/DdzFrame.vue): a light wall, a coral table with a rim and the multiplier in its middle, the two other seats' live
// pets behind its far edge on either side of the bottom cards, and the own pet beside the hand with the emotes' key
// under it. Cards are picked by click, by dragging across them, or by their rank on the keyboard; the keys under the
// hand carry the key that presses them.
// The cards are sized as on a desktop card table (measured on the PC client of 欢乐斗地主): the hand's a fifth of the
// height, a play two thirds of that, the bottom cards half.
// Drawn on a stage of at least 960×600 that is scaled as one piece to the window, in a board of at most 1040×680 in
// its middle. The wall moves the window; the close key closes it and leaves the seat playing (离桌 leaves the table).
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { hints, playable } from "../../ddz/rules";
import { arrange, cardAt, cardsOut, fan, pickJokers, pickRank, rankOfKey, stampOf } from "../../ddz/table";
import { cardSlide, flip } from "../../audio/sfx";
import { characterColor } from "../../manifest";
import { pet } from "../../stores/pet";
import { localPet, members, shownNick } from "../../stores/room";
import { settings } from "../../stores/settings";
import { reducedMotion } from "../../stores/theme";
import { autoDdz, againDdz, bidDdz, ddz, ddzEmotes, ddzLast, leaveDdz, playDdz, type DdzEvent } from "../../stores/ddz";
import NamePlate from "../../pet/NamePlate.vue";
import { getPlate } from "../../pet/plates";
import PetView from "../../pet/PetView.vue";
import Icon from "../../ui/Icon.vue";
import Modal from "../../ui/Modal.vue";
import { countTo } from "../park/countTo";
import DdzCard from "./DdzCard.vue";
import DdzEmotes from "./DdzEmotes.vue";
import DdzReceipt from "./DdzReceipt.vue";

const emit = defineEmits<{ close: []; drag: [e: PointerEvent] }>();

const t = computed(() => ddz.value!);
const you = computed(() => t.value.you);
/** The seat that plays after the own one sits on the right, the one before it on the left. */
const rightSeat = computed(() => (you.value + 1) % 3);
const leftSeat = computed(() => (you.value + 2) % 3);
const sides = computed(() => [{ seat: leftSeat.value, side: "left" }, { seat: rightSeat.value, side: "right" }] as const);
const mine = computed(() => t.value.seats[you.value]!);
const playing = computed(() => t.value.phase === "bid" || t.value.phase === "play");
/**
 * The room member in a seat, for its live pet's taps; null once it left the room, and at a table of the dou dizhu
 * connection, whose ids are not the room's (the seat's own face stands in).
 */
const memberOf = (seat: number) => {
  const s = t.value.seats[seat]!;
  return s.away || t.value.via === "link" ? null : members.get(s.id) ?? null;
};
/** The emote over a seat's pet: sent to the table, or by a 1.2.5 tablemate to the room. */
const emoteOf = (seat: number) => ddzEmotes.value[seat] ?? memberOf(seat)?.emote ?? null;
const nickOf = (seat: number) => (seat === you.value ? settings.nick.trim() || mine.value.nick || "我" : shownNick(t.value.seats[seat]!));
/** The name plate a seat shows in place of its name tag: the own one when worn, a partner's unless plates are off. */
const PLATE = { w: 196, h: 28 };
/** The other seats' pets, and the own one beside the hand. */
const PET = 0.85;
const OWN_PET = 0.8;
const plateOf = (seat: number): string | undefined => {
  if (seat === you.value) return getPlate(settings.plate)?.id;
  return settings.showPlates ? getPlate(t.value.seats[seat]!.plate ?? memberOf(seat)?.plate)?.id : undefined;
};

// ---- the stage: at least BASE, scaled as one piece
const BASE = { w: 960, h: 600 };
const root = ref<HTMLElement>();
const box = ref({ w: BASE.w, h: BASE.h });
let observer: ResizeObserver | undefined;
const unit = computed(() => Math.max(0.5, Math.min(box.value.w / BASE.w, box.value.h / BASE.h)));
const stage = computed(() => ({ w: box.value.w / unit.value, h: box.value.h / unit.value }));
/** The board everything but the window's own keys is laid out in: the stage's middle, so a large window gains margins. */
const BOARD_MAX = { w: 1040, h: 680 };
const board = computed(() => ({ w: Math.min(stage.value.w, BOARD_MAX.w), h: Math.min(stage.value.h, BOARD_MAX.h) }));
/** The margin on either side of the table; the table's top, under the other seats' pets, and its foot above the board's. */
const SIDE = 60;
const TABLE_TOP = 124;
const TABLE_FOOT = 212;
const tableW = computed(() => board.value.w - SIDE * 2);

// ---- the hand
const CARD = 84;
/** The hand starts clear of the own pet. */
const HAND_LEFT = 212;
const HAND_RIGHT = 28;
const LIFT = 18;
/** A card of the hand shows at most this much of itself under the next: half of it. */
const HAND_STEP = 42;
/** The hand's row: its foot above the board's foot (the time bar and the keys stand under it), and its height (a card and its lift). */
const HAND_BOTTOM = 68;
const HAND_H = Math.ceil(CARD * 1.42) + LIFT;
/** The bottom cards over the table, and how far down the board their middle is. */
const BOTTOM_CARD = 48;
const BOTTOMS_TOP = 12;
const BOTTOMS_MID = BOTTOMS_TOP + (BOTTOM_CARD * 1.42) / 2;
/** A card played onto the table, one left in a hand at the end, and the back that carries a seat's count. */
const PLAYED_CARD = 56;
const LEFT_CARD = 40;
const BACK_CARD = 30;
const handRoom = computed(() => board.value.w - HAND_LEFT - HAND_RIGHT);
const handFan = computed(() => fan(t.value.hand.length, handRoom.value, CARD, HAND_STEP));
const handX = computed(() => (handRoom.value - handFan.value.width) / 2);
const selected = ref(new Set<number>());
/** The landlord's three new cards stand up for a moment before they settle into the hand. */
const fresh = ref(new Set<number>());
let freshTimer: ReturnType<typeof setTimeout> | undefined;
/** Changes with every deal, so the cards come in one by one again. */
const dealt = ref(0);

// ---- the deal: the cards fly in face down from the bottom cards one by one, then turn over left to right in a
// wave. The keys to bid wait for it (the server starts the first bid's time after `dealSec`). FLIP_MS and
// FLIP_STEP_MS are the `turn-over` animation's length and its delay per card in the stylesheet.
const DEAL_FLIGHT_MS = 260;
const FLIP_MS = 440;
const FLIP_STEP_MS = 36;
/** Cards dealt so far while a deal runs (the other seats' counts follow it); null when no deal runs. */
const dealtN = ref<number | null>(null);
const dealing = computed(() => dealtN.value !== null);
/** The hand still shows its backs. */
const shut = ref(false);
const dealStep = ref(0);
let dealTimers: ReturnType<typeof setTimeout>[] = [];
function startDeal() {
  dealTimers.forEach(clearTimeout);
  dealTimers = [];
  const total = t.value.dealUntil - Date.now();
  const n = t.value.hand.length;
  if (total <= 0 || !n) { dealtN.value = null; shut.value = false; return; }
  const turnOver = FLIP_MS + (n - 1) * FLIP_STEP_MS;
  const span = Math.max(0, total - turnOver - DEAL_FLIGHT_MS);
  dealStep.value = n > 1 ? span / (n - 1) : 0;
  dealtN.value = 0;
  shut.value = true;
  for (let i = 0; i < n; i++) {
    dealTimers.push(setTimeout(() => { dealtN.value = i + 1; if (i % 2 === 0) cardSlide(); }, i * dealStep.value));
  }
  dealTimers.push(setTimeout(() => { shut.value = false; flip(); }, span + DEAL_FLIGHT_MS));
  dealTimers.push(setTimeout(() => { dealtN.value = null; }, total));
}
/** Cards a seat shows: while the deal runs, as many as were dealt out so far. */
const leftOf = (seat: number) => {
  const left = t.value.seats[seat]!.left;
  return dealtN.value === null ? left : Math.min(left, dealtN.value);
};
/** Where card [i] of the hand flies in from: the bottom cards at the top of the board, as an offset from its place. */
function dealFrom(i: number): Record<string, string> {
  const x = HAND_LEFT + handX.value + i * handFan.value.step + CARD / 2;
  const y = board.value.h - HAND_BOTTOM - HAND_H + (CARD * 1.42) / 2;
  return { "--fx": `${board.value.w / 2 - x}px`, "--fy": `${BOTTOMS_MID - y}px` };
}

watch(() => t.value.hand, (hand) => {
  const held = new Set(hand);
  if ([...selected.value].some((c) => !held.has(c))) selected.value = new Set([...selected.value].filter((c) => held.has(c)));
});

const handEl = ref<HTMLElement>();
let drag: { on: boolean; at: number; id: number } | null = null;
function cardUnder(e: PointerEvent): number {
  const rect = handEl.value!.getBoundingClientRect();
  return cardAt((e.clientX - rect.left) / unit.value - handX.value, t.value.hand.length, handFan.value.step, CARD);
}
function setCards(from: number, to: number, on: boolean) {
  const next = new Set(selected.value);
  for (let i = Math.min(from, to); i <= Math.max(from, to); i++) {
    const c = t.value.hand[i];
    if (c === undefined) continue;
    if (on) next.add(c); else next.delete(c);
  }
  selected.value = next;
}
// A press picks or drops the card under it; dragging on gives every card it crosses the same.
function handDown(e: PointerEvent) {
  if (e.button !== 0 || !playing.value || dealing.value) return;
  const at = cardUnder(e);
  if (at < 0) { selected.value = new Set(); return; }
  drag = { on: !selected.value.has(t.value.hand[at]!), at, id: e.pointerId };
  handEl.value?.setPointerCapture(e.pointerId);
  setCards(at, at, drag.on);
}
function handMove(e: PointerEvent) {
  if (!drag || e.pointerId !== drag.id) return;
  const at = cardUnder(e);
  if (at < 0 || at === drag.at) return;
  setCards(drag.at, at, drag.on);
  drag.at = at;
}
function handUp(e: PointerEvent) {
  if (drag?.id === e.pointerId) drag = null;
}
const clearPicked = () => { selected.value = new Set(); };

// ---- whose move, and what the keys do
const myTurn = computed(() => playing.value && t.value.turn === you.value && !mine.value.auto);
const last = computed(() => ddzLast(t.value));
const offers = computed(() => (myTurn.value && t.value.phase === "play" ? hints(t.value.hand, last.value?.cards ?? null) : []));
/** Nothing in the hand beats what is on the table: one key passes. */
const cannot = computed(() => myTurn.value && t.value.phase === "play" && !!last.value && offers.value.length === 0);
const canPlay = computed(() => myTurn.value && t.value.phase === "play" && !t.value.acted &&
  playable([...selected.value], last.value?.cards ?? null));
let hintAt = 0;
watch(() => [t.value.turn, t.value.until], () => { hintAt = 0; });
function hint() {
  if (!offers.value.length) return;
  selected.value = new Set(offers.value[hintAt % offers.value.length]);
  hintAt += 1;
}
function play() {
  if (canPlay.value) playDdz([...selected.value]);
}
function pass() {
  if (myTurn.value && t.value.phase === "play" && last.value && !t.value.acted) {
    clearPicked();
    playDdz([]);
  }
}
function bid(n: number) {
  if (myTurn.value && !dealing.value && t.value.phase === "bid" && !t.value.acted && (n === 0 || n > t.value.bid)) bidDdz(n);
}

// Leaving a game under way asks first: the seat is played to the end and the result still counts.
const leaving = ref(false);
function askLeave() {
  if (playing.value) leaving.value = true;
  else leaveDdz(t.value.id);
}
function leave() {
  leaving.value = false;
  leaveDdz(t.value.id);
}

function onKey(e: KeyboardEvent) {
  if (e.ctrlKey || e.metaKey || e.altKey || e.isComposing) return;
  if (document.querySelector(".ddz-overlay [data-overlay]")) return;
  if ((e.target as HTMLElement | null)?.closest?.("input, textarea, select, [contenteditable]")) return;
  const key = e.key;
  let used = true;
  if (t.value.phase === "result") {
    if (key === " " && !t.value.closed) againDdz();
    else if (key === "Escape") leaveDdz(t.value.id);
    else used = false;
  } else if (t.value.phase === "bid") {
    if (key === "Escape") bid(0);
    else if (key >= "1" && key <= "3") bid(Number(key));
    else used = false;
  } else if (t.value.phase === "play") {
    const r = rankOfKey(key);
    if (r !== null) selected.value = pickRank(t.value.hand, selected.value, r);
    else if (key === "w" || key === "W") selected.value = pickJokers(t.value.hand, selected.value);
    else if (key === " ") { if (cannot.value) pass(); else play(); }
    else if (key === "Tab") hint();
    else if (key === "Escape") { if (selected.value.size) clearPicked(); else pass(); }
    else used = false;
  } else used = false;
  if (used) e.preventDefault();
}

// ---- the countdown: a bar that empties, under the name of the seat to move and under the own hand, drawn by the
// stylesheet from where the turn stands when it is drawn; and a round key with the whole seconds left, where that
// seat lays its cards
function drain() {
  const left = Math.max(0, t.value.until - Date.now());
  const all = Math.max(1, t.value.sec * 1000);
  return { "--from": Math.min(1, left / all), animationDuration: `${left}ms` };
}
/** The seat whose countdown shows: the seat to move once the cards are dealt out; the own seat not while played for. */
const clockSeat = computed(() => {
  const x = t.value;
  if (!playing.value || dealing.value || x.turn === null) return null;
  return x.turn === you.value && !myTurn.value ? null : x.turn;
});
/** Turns coral from here down. */
const HURRY_SEC = 5;
const now = ref(Date.now());
const secLeft = computed(() => Math.max(0, Math.ceil((t.value.until - now.value) / 1000)));
let tickTimer: ReturnType<typeof setTimeout> | undefined;
/** Moves `now` on at each whole second of the countdown, only while one shows and the window is seen. */
function tick() {
  clearTimeout(tickTimer);
  now.value = Date.now();
  if (clockSeat.value === null || document.hidden) return;
  const left = t.value.until - now.value;
  if (left <= 0) return;
  tickTimer = setTimeout(tick, (left % 1000 || 1000) + 10);
}
watch([clockSeat, () => t.value.until], tick, { immediate: true });

// ---- what is on the table
/**
 * The card counter: what the other two seats still hold by rank. Hidden when the server does not list the plays, and
 * until the own hand is turned over (it would give the hand away).
 */
const out = computed(() => (playing.value && !dealing.value && t.value.played ? cardsOut(t.value.hand, t.value.played) : null));
const shownMult = ref(1);
const multEl = ref<HTMLElement>();
const matEl = ref<HTMLElement>();
const factorsEl = ref<HTMLElement>();
const mult = computed(() => (t.value.phase === "bid" ? Math.max(1, t.value.bid) : t.value.mult));
/** A bomb's ×2 flies from its cards into the row of factors first; the big number goes up when it lands. */
const FLY_DELAY_MS = 180;
const FLY_MS = 480;
let stopCount: (() => void) | undefined;
let countTimer: ReturnType<typeof setTimeout> | undefined;
watch(mult, (to, from) => {
  stopCount?.();
  clearTimeout(countTimer);
  if (from === undefined || to <= from) { shownMult.value = to; return; }
  const e = t.value.log.at(-1);
  countTimer = setTimeout(() => {
    stopCount = countTo(shownMult, to, 380);
    multEl.value?.animate(
      [{ scale: "1" }, { scale: "1.28", offset: 0.3 }, { scale: "0.96", offset: 0.7 }, { scale: "1" }],
      { duration: 460, easing: "ease-out" },
    );
  }, e?.kind === "play" && e.bomb ? FLY_DELAY_MS + FLY_MS : 0);
}, { immediate: true });

/**
 * The multiplier as its factors: the bid, then ×2 for each bomb and rocket, and 封顶 in place of the first one that
 * would take it past the cap (the bombs after that add nothing).
 */
const factors = computed(() => {
  const x = t.value;
  if (!x.bid) return [];
  const out = [{ key: `bid-${x.deal}-${x.bid}`, label: "叫分", value: String(x.bid) }];
  let at = x.bid;
  for (const [i, kind] of x.boosts.entries()) {
    if (at * 2 > x.cap) {
      out.push({ key: `cap-${x.deal}`, label: "封顶", value: "" });
      break;
    }
    at *= 2;
    out.push({ key: `boost-${x.deal}-${i}`, label: kind === "rocket" ? "王炸" : "炸弹", value: "×2" });
  }
  return out;
});
/** Flies the newest factor in from the cards of [seat], once per factor. */
const flown = new Set<string>();
function flyIn(seat: number) {
  const chip = factorsEl.value?.lastElementChild as HTMLElement | null | undefined;
  const key = chip?.dataset.key;
  if (!chip || !key || key.startsWith("bid-") || flown.has(key)) return;
  flown.add(key);
  const from = matEl.value?.querySelector(`.zone[data-seat="${seat}"]`)?.getBoundingClientRect();
  if (!from) return;
  const to = chip.getBoundingClientRect();
  const dx = (from.left + from.width / 2 - (to.left + to.width / 2)) / unit.value;
  const dy = (from.top + from.height / 2 - (to.top + to.height / 2)) / unit.value;
  chip.animate([
    { translate: `${dx}px ${dy}px`, scale: "1.7", opacity: 0 },
    { translate: `${dx}px ${dy}px`, scale: "1.7", opacity: 1, offset: 0.18 },
    { translate: "0 0", scale: "1", opacity: 1 },
  ], { duration: FLY_MS, delay: FLY_DELAY_MS, easing: "cubic-bezier(0.55, 0, 0.3, 1)", fill: "backwards" });
}

/** What a seat has in front of it: its last play, its bid while the seats bid, its cards left at the end. */
function zone(seat: number): { key: string; cards: number[]; said: string; small: boolean } {
  const s = t.value.seats[seat]!;
  if (t.value.phase === "result") {
    const leftOver = seat === you.value ? [] : arrange(t.value.result?.hands[seat] ?? []);
    return { key: "end", cards: leftOver, said: "", small: true };
  }
  if (t.value.phase === "bid") {
    return { key: `bid-${t.value.deal}-${s.bid}`, cards: [], said: s.bid === null ? "" : s.bid ? `${s.bid} 分` : "不叫", small: false };
  }
  const cards = t.value.trick[seat];
  if (!cards) return { key: "none", cards: [], said: "", small: false };
  return { key: cards.join(",") || "pass", cards: arrange(cards), said: cards.length ? "" : "不出", small: false };
}
/**
 * The three zones as drawn. Cards on the table show their corner and close up further when a play is long. The other
 * seats' reach from the table's side to the multiplier, the own one lies under it between the counter and its match
 * on the right.
 */
const zones = computed(() => [
  { seat: leftSeat.value, side: "left" }, { seat: rightSeat.value, side: "right" }, { seat: you.value, side: "own" },
].map(({ seat, side }) => {
  const z = zone(seat);
  const w = z.small ? LEFT_CARD : PLAYED_CARD;
  const room = side === "own" ? tableW.value - 380 : tableW.value / 2 - 122;
  return { seat, side, ...z, w, gap: fan(z.cards.length, room, w, z.small ? 16 : 23).step - w, bid: t.value.phase === "bid" && !!t.value.seats[seat]!.bid };
}));

const boom = ref<{ seq: number; seat: number } | null>(null);
/** A long play or a bomb is stamped with its name by its cards for a moment; one stamp on the table at a time. */
const STAMP_MS = 1200;
const stamp = ref<{ seq: number; seat: number; word: string } | null>(null);
let stampTimer: ReturnType<typeof setTimeout> | undefined;
function pressStamp(e: { seq: number; seat: number; cards: number[] }) {
  const word = stampOf(e.cards);
  // Only while the cards still lie there: a play caught up late may already be swept off by the next lead.
  if (!word || t.value.trick[e.seat]?.join() !== e.cards.join()) return;
  clearTimeout(stampTimer);
  stamp.value = { seq: e.seq, seat: e.seat, word };
  stampTimer = setTimeout(() => (stamp.value = null), STAMP_MS);
}
function liftStamp() {
  clearTimeout(stampTimer);
  stamp.value = null;
}

/** Bumped each time a seat's count changes at two cards or fewer, so its number bounces then (and not on opening). */
const bumps = ref([0, 0, 0]);
watch(() => t.value.seats.map((s) => s.left), (now, before) => {
  now.forEach((n, i) => { if (n <= 2 && before && n !== before[i]) bumps.value[i]! += 1; });
});

let seen = t.value.log.at(-1)?.seq ?? 0;
function onEvent(e: DdzEvent) {
  switch (e.kind) {
    case "deal":
      clearPicked();
      liftStamp();
      dealt.value = e.seq;
      flown.clear();
      startDeal();
      break;
    case "bid":
      cardSlide();
      break;
    case "landlord":
      flip();
      if (e.seat === you.value) {
        fresh.value = new Set(t.value.bottom);
        clearTimeout(freshTimer);
        freshTimer = setTimeout(() => (fresh.value = new Set()), 1100);
      }
      break;
    case "play":
      if (!e.cards.length) break;
      flip(!e.bomb);
      pressStamp(e);
      if (e.bomb) {
        boom.value = { seq: e.seq, seat: e.seat };
        void nextTick(() => flyIn(e.seat));
        if (!reducedMotion.value) matEl.value?.animate(
          [{ translate: "0 0" }, { translate: "-7px 3px" }, { translate: "6px -3px" }, { translate: "-4px 2px" }, { translate: "2px -1px" }, { translate: "0 0" }],
          { duration: 420, easing: "ease-out" },
        );
      }
      break;
    case "result":
      clearPicked();
      liftStamp();
      flip();
      break;
  }
}
watch(() => t.value.log.at(-1)?.seq, () => {
  for (const e of t.value.log) if (e.seq > seen) { seen = e.seq; onEvent(e); }
});
// The table opens with its first deal, which is already in the log: deal it out before the hand is first drawn.
startDeal();

/** A press on the wall: drops the picked cards, and moves the window. */
function wallDown(e: PointerEvent) {
  clearPicked();
  if (e.button === 0) emit("drag", e);
}

onMounted(() => {
  window.addEventListener("keydown", onKey);
  document.addEventListener("visibilitychange", tick);
  observer = new ResizeObserver(([entry]) => {
    const r = entry?.contentRect;
    if (r && r.width > 0 && r.height > 0) box.value = { w: r.width, h: r.height };
  });
  if (root.value) observer.observe(root.value);
});
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey);
  document.removeEventListener("visibilitychange", tick);
  clearTimeout(tickTimer);
  observer?.disconnect();
  clearTimeout(freshTimer);
  clearTimeout(countTimer);
  clearTimeout(stampTimer);
  dealTimers.forEach(clearTimeout);
  stopCount?.();
});
</script>

<template>
  <div class="ddz" data-overlay>
    <div ref="root" class="fit">
      <div
        class="stage" :class="`phase-${t.phase}`"
        :style="{ width: `${stage.w}px`, height: `${stage.h}px`, transform: `scale(${unit})` }" @pointerdown.self="wallDown"
      >
        <div class="top">
          <button type="button" class="ui-btn small ghost" @click="askLeave"><Icon name="logout" :size="16" />离桌</button>
          <span class="corner">
            <button
              v-if="playing" type="button" class="ui-btn small ghost" :aria-pressed="mine.auto" @click="autoDdz(!mine.auto)"
            >
              托管
            </button>
            <button type="button" class="ui-btn small ghost shut-key" title="关闭" aria-label="关闭" @click="emit('close')">
              <Icon name="close" :size="18" />
            </button>
          </span>
        </div>

        <div class="board" :style="{ width: `${board.w}px`, height: `${board.h}px` }" @pointerdown.self="wallDown">
          <!-- The three cards for the landlord: face down while the seats bid, turned over once there is one. -->
          <div class="bottoms" :class="{ open: t.landlord !== null }" :style="{ top: `${BOTTOMS_TOP}px` }" aria-label="底牌">
            <span v-for="i in 3" :key="i" class="flipper">
              <DdzCard class="side-back" :card="null" :width="BOTTOM_CARD" />
              <DdzCard v-if="t.bottom[i - 1] !== undefined" class="side-face" :card="t.bottom[i - 1]!" :width="BOTTOM_CARD" />
            </span>
          </div>

          <div
            ref="matEl" class="mat" :style="{ left: `${SIDE}px`, right: `${SIDE}px`, top: `${TABLE_TOP}px`, bottom: `${TABLE_FOOT}px` }"
            @pointerdown.self="clearPicked"
          >
            <div class="mult">
              <small>底分<Icon name="shard" :size="15" /><b>{{ t.base.toLocaleString("en-US") }}</b></small>
              <span ref="multEl" class="x"><i>×</i>{{ shownMult }}</span>
              <span ref="factorsEl" class="factors">
                <span v-for="f in factors" :key="f.key" class="factor" :data-key="f.key">
                  {{ f.label }}<b v-if="f.value">{{ f.value }}</b>
                </span>
              </span>
            </div>

            <div v-for="z in zones" :key="z.side" class="zone" :class="z.side" :data-seat="z.seat">
              <span v-if="z.said" :key="z.key" class="said" :class="{ bid: z.bid }">{{ z.said }}</span>
              <span v-else-if="z.cards.length" :key="`c-${z.key}`" class="cards" :class="{ small: z.small }">
                <DdzCard
                  v-for="(c, i) in z.cards" :key="c" :card="c" :width="z.w" :plain="i < z.cards.length - 1"
                  :style="{ marginLeft: i ? `${z.gap}px` : undefined, animationDelay: `${i * 16}ms` }"
                />
              </span>
              <i v-if="boom?.seat === z.seat" :key="boom.seq" class="boom" aria-hidden="true"></i>
              <span v-if="stamp?.seat === z.seat" :key="`s-${stamp.seq}`" class="stamp" :class="{ calm: reducedMotion }">{{ stamp.word }}</span>
              <span
                v-if="clockSeat === z.seat" class="timer" :class="{ hurry: secLeft <= HURRY_SEC, alone: !z.said && !z.cards.length }"
                role="timer"
              >
                {{ secLeft }}
              </span>
            </div>
            <div v-if="out" class="tally">
              <span v-for="c in out" :key="c.label" :class="{ none: !c.n }"><i>{{ c.label }}</i><b>{{ c.n }}</b></span>
            </div>
          </div>

          <div v-for="p in sides" :key="p.side" class="seat" :class="[p.side, { gone: t.seats[p.seat]!.away }]">
            <!-- The emotes open on the side away from the bottom cards, beside the head: over it is the stage's edge. -->
            <PetView
              v-if="memberOf(p.seat)" :character="t.seats[p.seat]!.character" :scale="PET" :min-emote="52"
              :pulse="memberOf(p.seat)!.pulse" :emote="emoteOf(p.seat)" :combo="memberOf(p.seat)!.combo"
              :win="memberOf(p.seat)!.win" :motion-id="memberOf(p.seat)!.id" :flip-bubble="p.side === 'left'"
              :bubble-shift="{ x: 0, y: 50 }"
            />
            <PetView
              v-else :character="t.seats[p.seat]!.character" :scale="PET" :min-emote="52" :emote="emoteOf(p.seat)"
              :flip-bubble="p.side === 'left'" :bubble-shift="{ x: 0, y: 50 }"
            />
            <div class="under">
              <span v-if="plateOf(p.seat)" class="worn" :class="{ turn: t.turn === p.seat && !dealing }">
                <NamePlate
                  :card="plateOf(p.seat)!" :nick="nickOf(p.seat)" :color="characterColor(t.seats[p.seat]!.character)"
                  :width="PLATE.w" :height="PLATE.h" :font="14"
                />
                <span class="badges">
                  <em v-if="t.landlord === p.seat" class="ui-tag lord">地主</em>
                  <em v-if="t.seats[p.seat]!.auto" class="ui-tag soft">托管</em>
                </span>
              </span>
              <div v-else class="pill" :class="{ turn: t.turn === p.seat && !dealing, lord: t.landlord === p.seat }">
                <i :style="{ background: characterColor(t.seats[p.seat]!.character) }" aria-hidden="true"></i>
                <span class="nick">{{ nickOf(p.seat) }}</span>
                <em v-if="t.landlord === p.seat" class="ui-tag light">地主</em>
                <em v-if="t.seats[p.seat]!.away" class="ui-tag soft">离开</em>
                <em v-else-if="t.seats[p.seat]!.auto" class="ui-tag soft">托管</em>
              </div>
              <!-- The cards the seat still holds: one back beside its name, the count on it. -->
              <div v-if="playing" v-show="leftOf(p.seat) > 0" class="count" :class="{ few: t.phase === 'play' && t.seats[p.seat]!.left <= 2 }">
                <DdzCard :card="null" :width="BACK_CARD" />
                <b :key="bumps[p.seat]" :class="{ bump: bumps[p.seat] && !reducedMotion }">{{ leftOf(p.seat) }}</b>
              </div>
            </div>
            <span v-if="playing && t.turn === p.seat && !dealing" :key="t.until" class="clock"><i :style="drain()"></i></span>
          </div>

          <div class="hand-wrap" :style="{ left: `${HAND_LEFT}px`, right: `${HAND_RIGHT}px`, bottom: `${HAND_BOTTOM}px`, height: `${HAND_H}px` }">
            <div
              ref="handEl" class="hand" :class="{ idle: !playing || dealing }"
              @pointerdown="handDown" @pointermove="handMove" @pointerup="handUp" @pointercancel="handUp"
            >
              <span
                v-for="(c, i) in t.hand" :key="`${dealt}-${c}`" class="held"
                :class="{ up: selected.has(c), fresh: fresh.has(c), shut, turning: dealing && !shut }"
                :style="{
                  translate: `${handX + i * handFan.step}px ${selected.has(c) || fresh.has(c) ? 0 : LIFT}px`,
                  zIndex: i, '--i': i, animationDelay: `${shut ? i * dealStep : i * 28}ms`, ...(shut ? dealFrom(i) : {}),
                }"
              >
                <span class="sides">
                  <DdzCard class="face" :card="c" :width="CARD" :plain="i < t.hand.length - 1" />
                  <DdzCard v-if="dealing" class="back" :card="null" :width="CARD" />
                </span>
              </span>
            </div>
          </div>

          <span
            v-if="myTurn && !dealing" :key="t.until" class="clock wide"
            :style="{ left: `${HAND_LEFT + handRoom / 2}px`, bottom: `${HAND_BOTTOM - 10}px` }"
          >
            <i :style="drain()"></i>
          </span>

          <div class="me">
            <PetView
              :character="settings.character" :scale="OWN_PET" :min-emote="52"
              :key-down="pet.keyDown" :form-press="pet.formPress" :mouse-dx="pet.dx" :mouse-dy="pet.dy" :left-down="pet.left" :right-down="pet.right"
              :emote="localPet.emote" :win="localPet.win" :pulse="localPet.pulse"
            />
            <div class="mine">
              <span v-if="plateOf(you)" class="worn" :class="{ turn: t.turn === you && !dealing }">
                <NamePlate
                  :card="plateOf(you)!" :nick="nickOf(you)" :color="characterColor(settings.character)"
                  :width="PLATE.w - 44" :height="PLATE.h" :font="14"
                />
                <span class="badges"><em v-if="t.landlord === you" class="ui-tag lord">地主</em></span>
              </span>
              <div v-else class="pill" :class="{ turn: t.turn === you && !dealing, lord: t.landlord === you }">
                <i :style="{ background: characterColor(settings.character) }" aria-hidden="true"></i>
                <span class="nick">{{ nickOf(you) }}</span>
                <em v-if="t.landlord === you" class="ui-tag light">地主</em>
              </div>
              <DdzEmotes up />
            </div>
          </div>

          <div class="keys" :style="t.phase === 'result' ? undefined : { left: `${HAND_LEFT}px`, right: `${HAND_RIGHT}px` }">
            <template v-if="t.phase === 'result'">
              <button type="button" class="ui-btn" @click="leaveDdz(t.id)">离桌<kbd>ESC</kbd></button>
              <button v-if="!t.closed" type="button" class="ui-btn primary" :disabled="mine.again" @click="againDdz">
                再来一局<kbd>SPACE</kbd>
              </button>
            </template>
            <button v-else-if="mine.auto" type="button" class="ui-btn primary" @click="autoDdz(false)">取消托管</button>
            <template v-else-if="myTurn && t.phase === 'bid' && !dealing">
              <button type="button" class="ui-btn" :disabled="t.acted" @click="bid(0)">不叫<kbd>ESC</kbd></button>
              <button
                v-for="n in 3" :key="n" type="button" class="ui-btn bid" :class="{ primary: n === 3 }"
                :disabled="t.acted || n <= t.bid" @click="bid(n)"
              >
                {{ n }} 分<kbd>{{ n }}</kbd>
              </button>
            </template>
            <template v-else-if="myTurn && t.phase === 'play'">
              <button v-if="cannot" type="button" class="ui-btn primary" :disabled="t.acted" @click="pass">要不起<kbd>SPACE</kbd></button>
              <template v-else>
                <button v-if="last" type="button" class="ui-btn" :disabled="t.acted" @click="pass">不出<kbd>ESC</kbd></button>
                <button type="button" class="ui-btn" :disabled="t.acted" @click="hint">提示<kbd>TAB</kbd></button>
                <button type="button" class="ui-btn primary" :disabled="!canPlay" @click="play">出牌<kbd>SPACE</kbd></button>
              </template>
            </template>
          </div>

          <DdzReceipt v-if="t.phase === 'result' && t.result" :key="t.log.at(-1)?.seq" :table="t" />
        </div>
      </div>
    </div>

    <div class="ddz-overlay"></div>
    <Modal v-if="leaving" to=".ddz-overlay" title="离开牌桌？" heading @close="leaving = false">
      <p class="leave-note">这一局会由托管打完，输赢照常结算。</p>
      <div class="confirm">
        <button type="button" class="ui-btn" @click="leaving = false">留下</button>
        <button type="button" class="ui-btn primary" @click="leave">离桌</button>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
/* The whole face of its window (or of the preview's frame), the corners rounded on a see-through window. */
.ddz { position: absolute; inset: 0; }
.fit { width: 100%; height: 100%; overflow: hidden; border-radius: var(--radius-l); }
/* The leave dialog is drawn here, over the table. */
.ddz-overlay { position: absolute; inset: 0; z-index: 10; overflow: hidden; border-radius: var(--radius-l); pointer-events: none; }
.ddz-overlay > :deep(*) { pointer-events: auto; }
/* The same light wall as the room's stage. */
.stage {
  position: relative;
  transform-origin: 0 0;
  background: var(--c-100);
  font-family: var(--font);
  color: var(--ink);
  user-select: none;
}
.board { position: absolute; left: 50%; top: 50%; translate: -50% -50%; }

.top { position: absolute; left: 14px; right: 14px; top: 12px; display: flex; justify-content: space-between; z-index: 5; pointer-events: none; }
.top .ui-btn { height: 36px; padding: 0 14px; gap: 6px; font-size: var(--fs-body); pointer-events: auto; }
.corner { display: flex; align-items: center; gap: 6px; }
.top .shut-key { width: 40px; padding: 0; }

/* The bottom cards turn over like the cards of a draw. */
.bottoms { position: absolute; left: 50%; translate: -50% 0; display: flex; gap: 6px; perspective: 780px; z-index: 1; pointer-events: none; }
.flipper { position: relative; display: block; width: 48px; height: calc(48px * 1.42); transform-style: preserve-3d; transition: transform 420ms var(--ease-out); }
.flipper:nth-child(2) { transition-delay: 70ms; }
.flipper:nth-child(3) { transition-delay: 140ms; }
.flipper > * { position: absolute; inset: 0; backface-visibility: hidden; }
.side-face { transform: rotateY(180deg); }
.bottoms.open .flipper { transform: rotateY(180deg); }
.bottoms.open .flipper:nth-child(1) { rotate: -5deg; translate: 0 3px; }
.bottoms.open .flipper:nth-child(3) { rotate: 5deg; translate: 0 3px; }

/* The table: a coral top with a deeper rim, lit along its outer edge, a white line where the rim meets the felt and
   the felt sunk a little under it; it throws its shadow on the wall. Sparse dots in the corner, as on the park's
   banners. The white cards land on it. */
.mat {
  position: absolute;
  border-radius: 28px;
  background: var(--grad-sky);
  box-shadow:
    0 2px 3px rgba(var(--c-900-rgb), 0.22),
    0 16px 24px -14px rgba(var(--c-900-rgb), 0.5),
    0 36px 52px -30px rgba(var(--c-900-rgb), 0.38);
}
.mat::before {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  box-shadow:
    inset 0 1.5px 0 rgba(255, 255, 255, 0.5),
    inset 0 -2px 0 rgba(var(--c-900-rgb), 0.16),
    inset 0 0 0 10px var(--c-600),
    inset 0 0 0 11.5px rgba(255, 255, 255, 0.55),
    inset 0 6px 10px 10px rgba(var(--c-900-rgb), 0.18);
  pointer-events: none;
}
.mat::after {
  content: "";
  position: absolute;
  inset: 10px;
  border-radius: 18px;
  background: #fff;
  opacity: 0.3;
  pointer-events: none;
  mask: radial-gradient(circle, #000 1.3px, transparent 1.8px) 0 0 / 18px 18px, radial-gradient(120% 100% at 100% 0, #000 10%, transparent 55%);
  mask-composite: intersect;
  -webkit-mask-composite: source-in;
}

/* The multiplier is the one big number of the table. At the table's lowest (264) the block (small 24, number 88,
   factors 28) ends 22 above the own cards on the table; a taller table gives the extra room above and below it. */
.mult {
  --at: max(12px, calc((100% - 264px) * 0.4 + 12px));
  position: absolute;
  left: 50%;
  top: var(--at);
  translate: -50% 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  color: #fff;
  z-index: 1;
  pointer-events: none;
}
.mult small {
  display: flex;
  align-items: center;
  gap: 5px;
  height: 24px;
  padding: 0 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.24);
  font-size: 13px;
  font-weight: 800;
}
.mult small b { font: 800 18px/1 var(--font-latin); letter-spacing: 0.3px; }
.mult .x {
  font: 800 106px/88px var(--font-latin);
  letter-spacing: -2px;
  text-shadow: 0 4px 0 var(--c-600), 0 12px 22px rgba(var(--c-900-rgb), 0.28);
}
/* The smaller × keeps out of the line's height, which stays the number's 88. */
.mult .x i { font-style: normal; font-size: 60px; line-height: 0; margin-right: 2px; opacity: 0.9; }
/* What the big number is made of, as on the receipt: the bid, then ×2 for each bomb. Always takes its room, so the
   number does not move when the first factor comes. */
.factors { display: flex; gap: 7px; height: 26px; margin-top: 2px; }
.factor {
  display: flex;
  align-items: center;
  gap: 5px;
  height: 26px;
  padding: 0 11px;
  border-radius: 13px;
  background: rgba(255, 255, 255, 0.24);
  font-size: 14px;
  font-weight: 800;
  white-space: nowrap;
  animation: pop 260ms var(--ease-pop) backwards;
}
.factor b { font: 800 18px/1 var(--font-latin); letter-spacing: 0.2px; }
.phase-result .mult { opacity: 0; }
/* The card counter: a paper slip in the table's near left corner, each rank over how many the other two still hold,
   in two rows; a rank all gone fades. */
.tally {
  position: absolute;
  left: 24px;
  bottom: 20px;
  width: 152px;
  box-sizing: border-box;
  display: grid;
  grid-template-columns: repeat(8, 1fr);
  row-gap: 6px;
  padding: 7px 4px 6px;
  border-radius: 10px;
  background: var(--surface);
  box-shadow: 0 4px 10px -5px rgba(var(--c-900-rgb), 0.45);
  z-index: 2;
  pointer-events: none;
}
.tally span { display: flex; flex-direction: column; align-items: center; gap: 2px; }
.tally i { font: 800 13px/1 var(--font-latin); font-style: normal; color: var(--ink-3); letter-spacing: -0.5px; }
/* The jokers' 小 and 大 are characters: smaller to sit on the numerals' line. */
.tally span:nth-last-child(-n + 2) i { font: 800 10px/13px var(--font); }
.tally b { font: 800 15px/1 var(--font-latin); color: var(--c-700); }
.tally .none { opacity: 0.3; }

/* What each seat has in front of it. Cards on the table lie a little askew, turned about the end their seat is at;
   the ones in the hand do not. The other seats' lie under their names, on either side of the multiplier; the own one
   along the table's near edge. */
.zone { position: absolute; display: flex; align-items: center; z-index: 2; pointer-events: none; }
.zone.left { left: 36px; top: 56px; rotate: -2deg; transform-origin: 0 50%; }
.zone.right { right: 36px; top: 56px; rotate: 2deg; transform-origin: 100% 50%; justify-content: flex-end; }
.zone.own { left: 50%; bottom: 12px; translate: -50% 0; }
.cards { display: flex; align-items: center; }
.cards > * { animation: land 300ms var(--ease-out) backwards; }
.zone.left .cards > * { --from: -70px -80px; }
.zone.right .cards > * { --from: 70px -80px; }
.zone.own .cards > * { --from: 0 120px; }
.cards.small > * { animation: none; }
@keyframes land {
  from { opacity: 0; translate: var(--from); scale: 0.72; }
}
/* A word in place of cards, standing where their middle would be. */
.said {
  height: 34px;
  padding: 0 16px;
  border-radius: 17px;
  background: color-mix(in srgb, #fff 26%, var(--c-500));
  display: grid;
  place-items: center;
  font-size: 15px;
  font-weight: 800;
  color: #fff;
  white-space: nowrap;
  animation: pop 260ms var(--ease-pop) backwards;
}
.zone.left .said { margin: 23px 0 23px 4px; }
.zone.right .said { margin: 23px 4px 23px 0; }
.zone.own .said { margin: 23px 0; }
.said.bid { background: #fff; color: var(--c-700); font: 800 21px/1 var(--font-latin); box-shadow: 0 3px 0 var(--c-600); }
@keyframes pop {
  from { opacity: 0; scale: 0.6; }
}
/* A bomb: a white ring opens from the cards and is gone. */
.boom {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 120px;
  height: 120px;
  margin: -60px 0 0 -60px;
  border-radius: 50%;
  box-shadow: 0 0 0 7px #fff, 0 0 30px 10px rgba(255, 255, 255, 0.7);
  opacity: 0;
  animation: boom 520ms var(--ease-out);
}
@keyframes boom {
  from { opacity: 0.95; scale: 0.3; }
  to { opacity: 0; scale: 2.6; }
}
/* A long play or a bomb: its name stamped askew on a white disc, as the receipt's spring seal, on the lower inner
   corner of the cards (beside them for the own seat), then gone. */
.stamp {
  position: absolute;
  width: 64px;
  height: 64px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: #fff;
  box-shadow: inset 0 0 0 2.5px var(--c-600), 0 5px 12px -5px rgba(var(--c-900-rgb), 0.5);
  color: var(--c-700);
  font: 800 18px/1 var(--font);
  letter-spacing: 1px;
  white-space: nowrap;
  rotate: -12deg;
  animation: press 1200ms var(--ease-out) forwards;
}
.stamp::before { content: ""; position: absolute; inset: 6px; border-radius: 50%; border: 1.5px solid var(--c-600); opacity: 0.6; }
.zone.left .stamp { right: -22px; top: 100%; margin-top: -22px; }
.zone.right .stamp { left: -22px; top: 100%; margin-top: -22px; rotate: 12deg; }
.zone.own .stamp { left: 100%; top: 50%; margin: -32px 0 0 14px; }
.stamp.calm { animation-name: press-calm; }
@keyframes press {
  0% { opacity: 0; scale: 2.4; }
  22% { opacity: 1; scale: 0.92; }
  32% { scale: 1; }
  84% { opacity: 1; }
  100% { opacity: 0; scale: 1; }
}
@keyframes press-calm {
  0%, 100% { opacity: 0; }
  10%, 84% { opacity: 1; }
}
/* The cards a seat still holds: one back beside its name, on the side away from the middle, the count on it. */
.count { position: absolute; top: 50%; translate: 0 -50%; width: 30px; height: calc(30px * 1.42); pointer-events: none; }
.seat.left .count { right: 100%; margin-right: 10px; rotate: -5deg; }
.seat.right .count { left: 100%; margin-left: 10px; rotate: 5deg; }
.count b {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  font: 800 19px/1 var(--font-latin);
  letter-spacing: -0.5px;
  color: #fff;
  text-shadow: 0 1px 0 var(--c-700), 0 0 6px rgba(var(--c-900-rgb), 0.5);
}
/* Nearly out: the number goes onto a white disc ringed in coral, and bounces each time it drops. */
.count.few b {
  inset: 50% auto auto 50%;
  width: 30px;
  height: 30px;
  margin: -15px 0 0 -15px;
  border-radius: 50%;
  background: #fff;
  color: var(--c-700);
  text-shadow: none;
  box-shadow: 0 0 0 2.5px var(--c-600), 0 5px 10px -4px rgba(var(--c-900-rgb), 0.55);
}
.count.few b.bump { animation: bump 520ms var(--ease-out); }
@keyframes bump {
  0% { scale: 0.6; }
  30% { scale: 1.32; }
  55% { scale: 0.92; }
  75% { scale: 1.08; }
  100% { scale: 1; }
}
/* The time a move has left: a round white key with the seconds, beside what the seat last laid down (on the inner
   side for the other seats, to the right for the own one, whose cards keep their place), alone where there is
   nothing. Coral for the last seconds. Stands upright on the askew zones. */
.timer {
  flex: none;
  width: 44px;
  height: 44px;
  margin-left: 12px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: linear-gradient(180deg, #fff, var(--key-white-shade));
  box-shadow: 0 3px 0 var(--c-200), 0 7px 10px -4px rgba(var(--c-900-rgb), 0.4);
  color: var(--ink);
  font: 800 23px/1 var(--font-latin);
  letter-spacing: -0.5px;
}
/* The coral key keeps a white edge, as the landlord's tag does, so it stands off the coral table. */
.timer.hurry {
  background: var(--c-600);
  box-shadow: inset 0 0 0 2px #fff, 0 3px 0 var(--c-700), 0 7px 10px -4px rgba(var(--c-900-rgb), 0.45);
  color: #fff;
}
.zone.left .timer { rotate: 2deg; }
.zone.right .timer { order: -1; margin: 0 12px 0 0; rotate: -2deg; }
.zone.own .timer { margin: 0 -56px 0 12px; }
/* Alone, it stands where the middle of the seat's cards would be. */
.zone .timer.alone { margin: 18px 0; }

/* The two other seats stand at the far edge of the table, one on either side of the bottom cards, their name tags on
   it; the cards left lie beside the tag on the side away from the middle, and the time to move runs out under it. */
.seat { position: absolute; top: 10px; width: 204px; translate: -50% 0; display: flex; flex-direction: column; align-items: center; z-index: 3; pointer-events: none; }
.seat.left { left: 28%; }
.seat.right { left: 72%; }
.seat :deep(.still), .me :deep(.still) { filter: var(--contour); }
.seat.gone :deep(.pet) { filter: grayscale(0.8); opacity: 0.6; }
.under { position: relative; display: flex; align-items: center; margin-top: 2px; }
/* A name plate in place of the tag: whose move it is rings it, and its tags sit on its top right corner like stickers. */
.worn { position: relative; flex: none; display: block; border-radius: 8px; transition: box-shadow var(--dur-base); }
.worn.turn { box-shadow: 0 0 0 3px var(--c-600); }
.me .worn.turn { box-shadow: 0 0 0 3px var(--c-500); }
.worn .badges { position: absolute; right: -7px; top: -11px; display: flex; gap: 4px; pointer-events: none; }
.worn .ui-tag.soft { --tag-bg: var(--c-100); --tag-fg: var(--c-700); }
.worn .ui-tag.lord { --tag-bg: var(--c-600); --tag-fg: #fff; box-shadow: 0 0 0 2px #fff; }
.pill {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  max-width: 190px;
  height: 28px;
  padding: 0 13px;
  box-sizing: border-box;
  border-radius: 14px;
  background: var(--surface);
  box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.12), 0 5px 12px -5px rgba(var(--c-900-rgb), 0.45);
  font-size: 14.5px;
  font-weight: 800;
  white-space: nowrap;
  transition: box-shadow var(--dur-base);
}
/* Whose move it is: a coral ring round the name. */
.pill.turn { box-shadow: 0 0 0 3px var(--c-600), 0 5px 12px -5px rgba(var(--c-900-rgb), 0.45); }
.pill > i { flex: none; width: 5px; height: 13px; border-radius: 1px; }
.pill .nick { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.pill .ui-tag { flex: none; margin: 0 -6px 0 2px; }
.pill .ui-tag.soft { --tag-bg: var(--c-100); --tag-fg: var(--c-700); }
/* The landlord's tag turns coral, a white edge keeping it off the table; its ring of the move stands outside that
   edge, in deep coral, as the table's coral would swallow the usual one. */
.pill.lord {
  background: var(--c-600);
  color: #fff;
  box-shadow: 0 0 0 2px #fff, 0 5px 12px -5px rgba(var(--c-900-rgb), 0.45);
}
.pill.lord.turn { box-shadow: 0 0 0 2px #fff, 0 0 0 5px var(--c-700), 0 5px 12px -5px rgba(var(--c-900-rgb), 0.45); }
.pill.lord > i { box-shadow: 0 0 0 1.5px #fff; }
/* The time a move has left: a bar that empties. */
.clock { display: block; width: 156px; height: 6px; margin-top: 8px; border-radius: 3px; background: rgba(255, 255, 255, 0.45); overflow: hidden; }
.clock i {
  display: block;
  height: 100%;
  border-radius: 3px;
  background: #fff;
  transform-origin: 0 50%;
  animation: drain linear forwards;
}
/* The own move's bar lies between the hand and the keys. */
.clock.wide { position: absolute; width: 452px; margin: 0 0 0 -226px; background: var(--c-200); z-index: 4; pointer-events: none; }
.clock.wide i { background: linear-gradient(90deg, var(--c-400), var(--c-600)); }
@keyframes drain {
  from { transform: scaleX(var(--from)); }
  to { transform: scaleX(0); }
}

.hand-wrap { position: absolute; z-index: 4; pointer-events: none; }
.hand { position: relative; height: 100%; pointer-events: auto; touch-action: none; }
.hand.idle { pointer-events: none; }
/* A card of the hand: the outer box flies it in and moves it, the inner one turns it over. */
.held {
  --fx: 0px;
  --fy: -120px;
  position: absolute;
  left: 0;
  top: 0;
  width: 84px;
  height: calc(84px * 1.42);
  perspective: 780px;
  transition: translate 150ms var(--ease-out);
  animation: deal 320ms var(--ease-out) backwards;
}
/* Dealt out: from the bottom cards, small and turning, one after another. */
.held.shut { animation-duration: 260ms; animation-timing-function: cubic-bezier(0.3, 0.6, 0.35, 1); }
@keyframes deal {
  from { opacity: 0; transform: translate(var(--fx), var(--fy)) scale(0.52) rotate(-12deg); }
  20% { opacity: 1; }
}
.sides {
  position: relative;
  display: block;
  width: 100%;
  height: 100%;
  transform-style: preserve-3d;
}
/* Over the card's own `position: relative`. */
.held .sides > * { position: absolute; inset: 0; backface-visibility: hidden; }
.held .sides > .back { transform: rotateY(180deg); }
.held.shut .sides { transform: rotateY(180deg); }
/* Turned over one after another, left to right: each lifts a little as it stands on edge, then lies down face up.
   Holds its back until its turn comes. */
.held.turning .sides { animation: turn-over 440ms linear calc(var(--i) * 36ms) both; }
@keyframes turn-over {
  from { transform: translateY(0) rotateY(180deg) scale(1); animation-timing-function: cubic-bezier(0.45, 0, 0.8, 0.6); }
  50% { transform: translateY(-13px) rotateY(90deg) scale(1.08); animation-timing-function: cubic-bezier(0.2, 0.4, 0.3, 1); }
  to { transform: translateY(0) rotateY(0deg) scale(1); }
}
.held .face { transition: box-shadow 150ms; }
/* A picked card stands up: a coral line along its top and coral light under it. */
.held.up .face, .held.fresh .face {
  box-shadow: 0 0 0 1px rgba(var(--c-900-rgb), 0.12), 0 -4px 0 var(--c-500), 0 13px 20px -5px rgba(var(--c-500-rgb), 0.95),
    -3px 3px 6px -2px rgba(var(--c-900-rgb), 0.3);
}
.phase-result .held { filter: saturate(0.6); opacity: 0.75; }

/* The own pet sits beside the hand, live like the two others; under it the own name and the emotes' key. */
.me { position: absolute; left: 8px; bottom: 10px; width: 196px; display: flex; flex-direction: column; align-items: center; gap: 3px; z-index: 6; pointer-events: none; }
.mine { display: flex; align-items: center; gap: 7px; max-width: 100%; }
.me .pill { max-width: 148px; box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.12), 0 5px 12px -5px rgba(var(--shadow-rgb), 0.3); }
.me .pill.turn { box-shadow: 0 0 0 3px var(--c-500), 0 5px 12px -5px rgba(var(--shadow-rgb), 0.3); }
.me .pill.lord { box-shadow: 0 0 0 2px #fff, 0 5px 12px -5px rgba(var(--shadow-rgb), 0.3); }
.me .pill.lord.turn { box-shadow: 0 0 0 2px #fff, 0 0 0 5px var(--c-500), 0 5px 12px -5px rgba(var(--shadow-rgb), 0.3); }

.keys { position: absolute; left: 0; right: 0; bottom: 10px; height: 42px; display: flex; justify-content: center; gap: 12px; z-index: 5; pointer-events: none; }
.keys .ui-btn { height: 42px; min-width: 118px; padding: 0 16px; font-size: 16px; pointer-events: auto; }
.keys .ui-btn.bid { min-width: 92px; }
/* The corner of a keycap says which key of the keyboard it is. */
.keys kbd {
  height: 19px;
  margin-left: 4px;
  padding: 0 6px;
  border-radius: 5px;
  background: var(--c-100);
  font: 800 11.5px/19px var(--font-latin);
  letter-spacing: 0.5px;
  color: var(--c-700);
}
.keys .primary kbd { background: rgba(255, 255, 255, 0.45); color: var(--c-900); }
/* A key that cannot be pressed stays a key: flat paper with an outline, since the wall is the disabled colour. */
.keys .ui-btn:disabled { --key-top: var(--c-50); --key-bottom: var(--c-50); box-shadow: inset 0 0 0 1.5px var(--c-200); }
.keys .ui-btn:disabled kbd { background: transparent; color: var(--ink-3); }

.leave-note { margin: 0 0 18px; font-size: var(--fs-body); line-height: 1.6; color: var(--ink-2); }
.confirm { display: flex; justify-content: flex-end; gap: 10px; }
</style>
