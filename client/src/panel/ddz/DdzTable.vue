<script setup lang="ts">
// The dou dizhu table, over the room page while a game is on: a light wall, a coral mat with the multiplier in its
// middle, the two other seats' live pets behind it and the own pet beside the hand. Cards are picked by click, by
// dragging across them, or by their rank on the keyboard; the keys under the hand carry the key that presses them.
// Drawn on a stage of at least 748×600 that is scaled as one piece to the room the panel has.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { hints, playable } from "../../ddz/rules";
import { arrange, cardAt, fan, pickJokers, pickRank, rankOfKey } from "../../ddz/table";
import { cardSlide, flip } from "../../audio/sfx";
import { characterColor } from "../../manifest";
import { pet } from "../../stores/pet";
import { localPet, members, shownNick } from "../../stores/room";
import { settings } from "../../stores/settings";
import { autoDdz, againDdz, bidDdz, ddz, ddzLast, leaveDdz, playDdz, type DdzEvent } from "../../stores/ddz";
import NamePlate from "../../pet/NamePlate.vue";
import { getPlate } from "../../pet/plates";
import PetView from "../../pet/PetView.vue";
import Icon from "../../ui/Icon.vue";
import Modal from "../../ui/Modal.vue";
import { countTo } from "../park/countTo";
import DdzCard from "./DdzCard.vue";
import DdzEmotes from "./DdzEmotes.vue";
import DdzReceipt from "./DdzReceipt.vue";

const t = computed(() => ddz.value!);
const you = computed(() => t.value.you);
/** The seat that plays after the own one sits on the right, the one before it on the left. */
const rightSeat = computed(() => (you.value + 1) % 3);
const leftSeat = computed(() => (you.value + 2) % 3);
const sides = computed(() => [{ seat: leftSeat.value, side: "left" }, { seat: rightSeat.value, side: "right" }] as const);
const mine = computed(() => t.value.seats[you.value]!);
const playing = computed(() => t.value.phase === "bid" || t.value.phase === "play");
/** The room member in a seat, for its live pet; null once it left the room. */
const memberOf = (seat: number) => {
  const s = t.value.seats[seat]!;
  return s.away ? null : members.get(s.id) ?? null;
};
const nickOf = (seat: number) => (seat === you.value ? settings.nick.trim() || mine.value.nick || "我" : shownNick(t.value.seats[seat]!));
/** The name plate a seat shows in place of its name tag: the own one when worn, a partner's unless plates are off. */
const PLATE = { w: 168, h: 24 };
const plateOf = (seat: number): string | undefined => {
  if (seat === you.value) return getPlate(settings.plate)?.id;
  const m = memberOf(seat);
  return settings.showPlates && m ? getPlate(m.plate)?.id : undefined;
};

// ---- the stage: at least BASE, scaled as one piece
const BASE = { w: 748, h: 600 };
const root = ref<HTMLElement>();
const box = ref({ w: BASE.w, h: BASE.h });
let observer: ResizeObserver | undefined;
const unit = computed(() => Math.max(0.5, Math.min(box.value.w / BASE.w, box.value.h / BASE.h)));
const stage = computed(() => ({ w: box.value.w / unit.value, h: box.value.h / unit.value }));

// ---- the hand
const CARD = 64;
const HAND_LEFT = 172;
const HAND_RIGHT = 16;
const LIFT = 18;
const handRoom = computed(() => stage.value.w - HAND_LEFT - HAND_RIGHT);
const handFan = computed(() => fan(t.value.hand.length, handRoom.value, CARD, 38));
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
/** Where card [i] of the hand flies in from: the bottom cards at the top of the stage, as an offset from its place. */
function dealFrom(i: number): Record<string, string> {
  const x = HAND_LEFT + handX.value + i * handFan.value.step + CARD / 2;
  const y = stage.value.h - 166 + (CARD * 1.42) / 2;
  return { "--fx": `${stage.value.w / 2 - x}px`, "--fy": `${46 - y}px` };
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
  else leaveDdz();
}
function leave() {
  leaving.value = false;
  leaveDdz();
}

function onKey(e: KeyboardEvent) {
  if (e.ctrlKey || e.metaKey || e.altKey || e.isComposing) return;
  if (document.querySelector(".panel-overlay [data-overlay]")) return;
  if ((e.target as HTMLElement | null)?.closest?.("input, textarea, select, [contenteditable]")) return;
  const key = e.key;
  let used = true;
  if (t.value.phase === "result") {
    if (key === " " && !t.value.closed) againDdz();
    else if (key === "Escape") leaveDdz();
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

// ---- countdown bars: drawn by the stylesheet from where the turn stands when it is drawn
function drain() {
  const left = Math.max(0, t.value.until - Date.now());
  const all = Math.max(1, t.value.sec * 1000);
  return { "--from": Math.min(1, left / all), animationDuration: `${left}ms` };
}

// ---- what is on the table
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
/** The three zones as drawn. Cards on the table are 54 wide (40 for what is left at the end) and close up when a play is long. */
const zones = computed(() => [
  { seat: leftSeat.value, side: "left" }, { seat: rightSeat.value, side: "right" }, { seat: you.value, side: "own" },
].map(({ seat, side }) => {
  const z = zone(seat);
  const w = z.small ? 40 : 54;
  const room = side === "own" ? stage.value.w - 300 : stage.value.w / 2 - 130;
  return { seat, side, ...z, w, gap: fan(z.cards.length, room, w, z.small ? 17 : 30).step - w, bid: t.value.phase === "bid" && !!t.value.seats[seat]!.bid };
}));

const boom = ref<{ seq: number; seat: number } | null>(null);
let seen = t.value.log.at(-1)?.seq ?? 0;
function onEvent(e: DdzEvent) {
  switch (e.kind) {
    case "deal":
      clearPicked();
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
      if (e.bomb) {
        boom.value = { seq: e.seq, seat: e.seat };
        void nextTick(() => flyIn(e.seat));
        matEl.value?.animate(
          [{ translate: "0 0" }, { translate: "-7px 3px" }, { translate: "6px -3px" }, { translate: "-4px 2px" }, { translate: "2px -1px" }, { translate: "0 0" }],
          { duration: 420, easing: "ease-out" },
        );
      }
      break;
    case "result":
      clearPicked();
      flip();
      break;
  }
}
watch(() => t.value.log.at(-1)?.seq, () => {
  for (const e of t.value.log) if (e.seq > seen) { seen = e.seq; onEvent(e); }
});
// The table opens with its first deal, which is already in the log: deal it out before the hand is first drawn.
startDeal();

onMounted(() => {
  window.addEventListener("keydown", onKey);
  observer = new ResizeObserver(([entry]) => {
    const r = entry?.contentRect;
    if (r && r.width > 0 && r.height > 0) box.value = { w: r.width, h: r.height };
  });
  if (root.value) observer.observe(root.value);
});
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey);
  observer?.disconnect();
  clearTimeout(freshTimer);
  clearTimeout(countTimer);
  dealTimers.forEach(clearTimeout);
  stopCount?.();
});
</script>

<template>
  <div class="ddz" data-overlay>
    <div ref="root" class="fit">
      <div
        class="stage" :class="`phase-${t.phase}`"
        :style="{ width: `${stage.w}px`, height: `${stage.h}px`, transform: `scale(${unit})` }" @pointerdown.self="clearPicked"
      >
        <div class="top">
          <button type="button" class="ui-btn small ghost" @click="askLeave"><Icon name="logout" :size="14" />离桌</button>
          <span class="corner">
            <button
              v-if="playing" type="button" class="ui-btn small ghost" :aria-pressed="mine.auto" @click="autoDdz(!mine.auto)"
            >
              托管
            </button>
            <DdzEmotes />
          </span>
        </div>

        <!-- The three cards for the landlord: face down while the seats bid, turned over once there is one. -->
        <div class="bottoms" :class="{ open: t.landlord !== null }" aria-label="底牌">
          <span v-for="i in 3" :key="i" class="flipper">
            <DdzCard class="side-back" :card="null" :width="40" />
            <DdzCard v-if="t.bottom[i - 1] !== undefined" class="side-face" :card="t.bottom[i - 1]!" :width="40" />
          </span>
        </div>

        <div ref="matEl" class="mat" @pointerdown.self="clearPicked">
          <div class="mult">
            <small>底分<Icon name="shard" :size="12" /><b>{{ t.base.toLocaleString("en-US") }}</b></small>
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
          </div>
        </div>

        <div v-for="p in sides" :key="p.side" class="seat" :class="[p.side, { gone: !memberOf(p.seat) }]">
          <PetView
            v-if="memberOf(p.seat)" :character="memberOf(p.seat)!.character" :scale="0.85" :min-emote="40"
            :pulse="memberOf(p.seat)!.pulse" :emote="memberOf(p.seat)!.emote" :combo="memberOf(p.seat)!.combo"
            :win="memberOf(p.seat)!.win" :motion-id="memberOf(p.seat)!.id" :flip-bubble="p.side === 'right'"
          />
          <PetView v-else :character="t.seats[p.seat]!.character" :scale="0.85" />
          <div class="under">
            <span v-if="plateOf(p.seat)" class="worn" :class="{ turn: t.turn === p.seat && !dealing }">
              <NamePlate
                :card="plateOf(p.seat)!" :nick="nickOf(p.seat)" :color="characterColor(t.seats[p.seat]!.character)"
                :width="PLATE.w" :height="PLATE.h" :font="12"
              />
              <span class="badges">
                <em v-if="t.landlord === p.seat" class="ui-tag dark">地主</em>
                <em v-if="t.seats[p.seat]!.auto" class="ui-tag soft">托管</em>
              </span>
            </span>
            <div v-else class="pill" :class="{ turn: t.turn === p.seat && !dealing }">
              <i :style="{ background: characterColor(t.seats[p.seat]!.character) }" aria-hidden="true"></i>
              <span class="nick">{{ nickOf(p.seat) }}</span>
              <em v-if="t.landlord === p.seat" class="ui-tag dark">地主</em>
              <em v-if="t.seats[p.seat]!.away" class="ui-tag soft">离开</em>
              <em v-else-if="t.seats[p.seat]!.auto" class="ui-tag soft">托管</em>
            </div>
            <div v-if="playing" class="count" :class="{ few: t.phase === 'play' && t.seats[p.seat]!.left <= 2 }">
              <span class="stack"><DdzCard v-for="n in Math.min(3, leftOf(p.seat))" :key="n" :card="null" :width="26" /></span>
              <b>{{ leftOf(p.seat) }}</b>
            </div>
          </div>
          <span v-if="playing && t.turn === p.seat && !dealing" :key="t.until" class="clock"><i :style="drain()"></i></span>
        </div>

        <div class="hand-wrap" :style="{ left: `${HAND_LEFT}px`, right: `${HAND_RIGHT}px` }">
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
        <span v-if="myTurn && !dealing" :key="t.until" class="clock wide"><i :style="drain()"></i></span>

        <div class="me">
          <PetView
            :character="settings.character" :scale="0.625" :min-emote="40"
            :key-down="pet.keyDown" :form-press="pet.formPress" :mouse-dx="pet.dx" :mouse-dy="pet.dy" :left-down="pet.left" :right-down="pet.right"
            :emote="localPet.emote" :win="localPet.win" :pulse="localPet.pulse"
          />
          <span v-if="plateOf(you)" class="worn" :class="{ turn: t.turn === you && !dealing }">
            <NamePlate
              :card="plateOf(you)!" :nick="nickOf(you)" :color="characterColor(settings.character)"
              :width="PLATE.w" :height="PLATE.h" :font="12"
            />
            <span class="badges"><em v-if="t.landlord === you" class="ui-tag dark">地主</em></span>
          </span>
          <div v-else class="pill" :class="{ turn: t.turn === you && !dealing }">
            <i :style="{ background: characterColor(settings.character) }" aria-hidden="true"></i>
            <span class="nick">{{ nickOf(you) }}</span>
            <em v-if="t.landlord === you" class="ui-tag dark">地主</em>
          </div>
        </div>

        <div class="keys" :style="t.phase === 'result' ? undefined : { left: `${HAND_LEFT}px`, right: `${HAND_RIGHT}px` }">
          <template v-if="t.phase === 'result'">
            <button type="button" class="ui-btn" @click="leaveDdz">离桌<kbd>ESC</kbd></button>
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

    <Modal v-if="leaving" title="离开牌桌？" heading @close="leaving = false">
      <p class="leave-note">这一局会由托管打完，输赢照常结算。</p>
      <div class="confirm">
        <button type="button" class="ui-btn" @click="leaving = false">留下</button>
        <button type="button" class="ui-btn primary" @click="leave">离桌</button>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
/* Over the page area of the panel: beside the sidebar, under the top bar. */
.ddz {
  position: absolute;
  inset: 46px 0 0 var(--side-w);
  /* Above everything of the page under it, its pets' bubbles included. */
  z-index: 30;
  padding: 4px 16px 16px 12px;
  box-sizing: border-box;
  background: var(--c-50);
}
.fit { width: 100%; height: 100%; overflow: hidden; border-radius: var(--radius-l); }
/* The same light wall as the room's stage. */
.stage {
  position: relative;
  transform-origin: 0 0;
  background: var(--c-100);
  font-family: var(--font);
  color: var(--ink);
  user-select: none;
}

.top { position: absolute; left: 14px; right: 14px; top: 12px; display: flex; justify-content: space-between; z-index: 5; pointer-events: none; }
.top > .ui-btn, .corner > .ui-btn { height: 30px; padding: 0 12px; gap: 5px; pointer-events: auto; }
.corner { display: flex; align-items: center; gap: 4px; }

/* The bottom cards turn over like the cards of a draw. */
.bottoms { position: absolute; left: 50%; top: 18px; translate: -50% 0; display: flex; gap: 6px; perspective: 600px; z-index: 1; }
.flipper { position: relative; display: block; width: 40px; height: 57px; transform-style: preserve-3d; transition: transform 420ms var(--ease-out); }
.flipper:nth-child(2) { transition-delay: 70ms; }
.flipper:nth-child(3) { transition-delay: 140ms; }
.flipper > * { position: absolute; inset: 0; backface-visibility: hidden; }
.side-face { transform: rotateY(180deg); }
.bottoms.open .flipper { transform: rotateY(180deg); }
.bottoms.open .flipper:nth-child(1) { rotate: -5deg; translate: 0 2px; }
.bottoms.open .flipper:nth-child(3) { rotate: 5deg; translate: 0 2px; }

/* The mat: one coral block with a white line inside its edge and sparse dots in the corner, as on the park's
   banners. The white cards land on it. */
.mat {
  position: absolute;
  left: 20px;
  right: 20px;
  top: 168px;
  bottom: 178px;
  border-radius: 22px;
  background: var(--grad-sky);
  box-shadow: 0 10px 24px -14px rgba(var(--c-900-rgb), 0.55), inset 0 1px 0 rgba(255, 255, 255, 0.45);
}
.mat::before {
  content: "";
  position: absolute;
  inset: 9px;
  border-radius: 14px;
  box-shadow: inset 0 0 0 1.5px rgba(255, 255, 255, 0.5);
  pointer-events: none;
}
.mat::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: #fff;
  opacity: 0.3;
  pointer-events: none;
  mask: radial-gradient(circle, #000 1.1px, transparent 1.5px) 0 0 / 14px 14px, radial-gradient(120% 100% at 100% 0, #000 10%, transparent 55%);
  mask-composite: intersect;
  -webkit-mask-composite: source-in;
}
/* The multiplier is the one big number of the table. */
.mult {
  /* At the mat's lowest (254) the block (small 20, number 82, factors 24) ends 17 above the own cards on the table. */
  --at: max(22px, calc((100% - 195px) * 0.35));
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
  gap: 4px;
  height: 20px;
  padding: 0 10px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.24);
  font-size: 11px;
  font-weight: 800;
}
.mult small b { font: 800 15px/1 var(--font-latin); letter-spacing: 0.3px; }
.mult .x {
  font: 800 92px/82px var(--font-latin);
  letter-spacing: -2px;
  text-shadow: 0 3px 0 var(--c-600), 0 10px 18px rgba(var(--c-900-rgb), 0.28);
}
/* The smaller × keeps out of the line's height, which stays the number's 82. */
.mult .x i { font-style: normal; font-size: 52px; line-height: 0; margin-right: 2px; opacity: 0.9; }
/* What the big number is made of, as on the receipt: the bid, then ×2 for each bomb. Always takes its room, so the
   number does not move when the first factor comes. */
.factors { display: flex; gap: 6px; height: 22px; margin-top: 2px; }
.factor {
  display: flex;
  align-items: center;
  gap: 4px;
  height: 22px;
  padding: 0 9px;
  border-radius: 11px;
  background: rgba(255, 255, 255, 0.24);
  font-size: 12px;
  font-weight: 800;
  white-space: nowrap;
  animation: pop 260ms var(--ease-pop) backwards;
}
.factor b { font: 800 15px/1 var(--font-latin); letter-spacing: 0.2px; }
.phase-result .mult { opacity: 0; }

/* What each seat has in front of it. Cards on the table lie a little askew; the ones in the hand do not. */
.zone { position: absolute; display: flex; align-items: center; z-index: 2; pointer-events: none; }
.zone.left { left: 44px; top: max(92px, calc((100% - 195px) * 0.35 + 62px)); rotate: -3deg; }
.zone.right { right: 44px; top: max(92px, calc((100% - 195px) * 0.35 + 62px)); rotate: 3deg; justify-content: flex-end; }
.zone.own { left: 50%; bottom: 12px; translate: -50% 0; }
.cards { display: flex; align-items: center; }
.cards > * { animation: land 300ms var(--ease-out) backwards; }
.zone.left .cards > * { --from: -90px -70px; }
.zone.right .cards > * { --from: 90px -70px; }
.zone.own .cards > * { --from: 0 120px; }
.cards.small > * { animation: none; }
@keyframes land {
  from { opacity: 0; translate: var(--from); scale: 0.72; }
}
.said {
  height: 32px;
  padding: 0 15px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.26);
  display: grid;
  place-items: center;
  font-size: 14px;
  font-weight: 800;
  color: #fff;
  white-space: nowrap;
  animation: pop 260ms var(--ease-pop) backwards;
}
.zone.left .said { margin: 22px 0 0 30px; }
.zone.right .said { margin: 22px 30px 0 0; }
.zone.own .said { margin-bottom: 22px; }
.said.bid { background: #fff; color: var(--c-700); font: 800 20px/1 var(--font-latin); box-shadow: 0 3px 0 var(--c-600); }
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
  box-shadow: 0 0 0 6px #fff, 0 0 30px 10px rgba(255, 255, 255, 0.7);
  opacity: 0;
  animation: boom 520ms var(--ease-out);
}
@keyframes boom {
  from { opacity: 0.95; scale: 0.3; }
  to { opacity: 0; scale: 2.6; }
}

/* The two other seats sit at the far edge of the mat, their name tags on it. */
.seat { position: absolute; top: 58px; width: 214px; display: flex; flex-direction: column; align-items: center; z-index: 3; pointer-events: none; }
.seat.left { left: 24px; }
.seat.right { right: 24px; }
.seat :deep(.still), .me :deep(.still) { filter: var(--contour); }
.seat.gone :deep(.pet) { filter: grayscale(0.8); opacity: 0.6; }
/* The name tag (or plate) right under the pet; the cards left hang beside it on the side of the table's middle, so
   nothing reaches the mat's edge. */
.under { position: relative; display: flex; align-items: center; margin-top: 2px; }
/* A name plate in place of the tag: whose move it is rings it, and its tags sit on its top right corner like stickers. */
.worn { position: relative; flex: none; display: block; border-radius: 7px; transition: box-shadow var(--dur-base); }
.worn.turn { box-shadow: 0 0 0 2.5px var(--c-600); }
.me .worn.turn { box-shadow: 0 0 0 2.5px var(--c-500); }
.worn .badges { position: absolute; right: -6px; top: -9px; display: flex; gap: 3px; pointer-events: none; }
.worn .ui-tag.soft { --tag-bg: var(--c-100); --tag-fg: var(--c-700); }
.pill {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  max-width: 150px;
  height: 24px;
  padding: 0 11px;
  box-sizing: border-box;
  border-radius: 12px;
  background: var(--surface);
  box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.12), 0 4px 10px -4px rgba(var(--c-900-rgb), 0.45);
  font-size: 12px;
  font-weight: 800;
  white-space: nowrap;
  transition: box-shadow var(--dur-base);
}
/* Whose move it is: a coral ring round the name. */
.pill.turn { box-shadow: 0 0 0 2.5px var(--c-600), 0 4px 10px -4px rgba(var(--c-900-rgb), 0.45); }
.pill > i { flex: none; width: 4px; height: 11px; border-radius: 1px; }
.pill .nick { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.pill .ui-tag { flex: none; margin: 0 -5px 0 2px; }
.pill .ui-tag.soft { --tag-bg: var(--c-100); --tag-fg: var(--c-700); }
.count { position: absolute; top: 50%; translate: 0 -50%; display: flex; align-items: center; gap: 5px; font: 800 26px/1 var(--font-latin); color: #fff; text-shadow: 0 2px 0 var(--c-600); white-space: nowrap; }
.seat.left .count { left: 100%; margin-left: 10px; }
.seat.right .count { right: 100%; margin-right: 10px; }
.count .stack { display: flex; }
.count .stack > * + * { margin-left: -19px; }
/* Nearly out: the number goes onto a white disc, in deep coral. */
.count.few b {
  display: grid;
  place-items: center;
  min-width: 30px;
  height: 30px;
  border-radius: 15px;
  background: #fff;
  color: var(--c-700);
  text-shadow: none;
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.35);
  animation: pop 260ms var(--ease-pop);
}
/* The time a move has left: a bar that empties. */
.clock { display: block; width: 120px; height: 5px; margin-top: 7px; border-radius: 3px; background: rgba(255, 255, 255, 0.45); overflow: hidden; }
.clock i {
  display: block;
  height: 100%;
  border-radius: 3px;
  background: #fff;
  transform-origin: 0 50%;
  animation: drain linear forwards;
}
/* The own move's bar lies between the hand and the keys. */
.clock.wide { position: absolute; left: calc(50% + 78px); bottom: 62px; width: 348px; margin: 0 0 0 -174px; background: var(--c-200); z-index: 4; }
.clock.wide i { background: linear-gradient(90deg, var(--c-400), var(--c-600)); }
@keyframes drain {
  from { transform: scaleX(var(--from)); }
  to { transform: scaleX(0); }
}

.hand-wrap { position: absolute; bottom: 74px; height: 110px; z-index: 4; pointer-events: none; }
.hand { position: relative; height: 110px; pointer-events: auto; touch-action: none; }
.hand.idle { pointer-events: none; }
/* A card of the hand: the outer box flies it in and moves it, the inner one turns it over. */
.held {
  --fx: 0px;
  --fy: -90px;
  position: absolute;
  left: 0;
  top: 0;
  width: 64px;
  height: calc(64px * 1.42);
  perspective: 600px;
  transition: translate 150ms var(--ease-out);
  animation: deal 320ms var(--ease-out) backwards;
}
/* Dealt out: from the bottom cards, small and turning, one after another. */
.held.shut { animation-duration: 260ms; animation-timing-function: cubic-bezier(0.3, 0.6, 0.35, 1); }
@keyframes deal {
  from { opacity: 0; transform: translate(var(--fx), var(--fy)) scale(0.62) rotate(-12deg); }
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
  50% { transform: translateY(-10px) rotateY(90deg) scale(1.08); animation-timing-function: cubic-bezier(0.2, 0.4, 0.3, 1); }
  to { transform: translateY(0) rotateY(0deg) scale(1); }
}
.held .face { transition: box-shadow 150ms; }
/* A picked card stands up: a coral line along its top and coral light under it. */
.held.up .face, .held.fresh .face {
  box-shadow: 0 0 0 1px rgba(var(--c-900-rgb), 0.12), 0 -3px 0 var(--c-500), 0 10px 16px -4px rgba(var(--c-500-rgb), 0.95),
    -3px 3px 6px -2px rgba(var(--c-900-rgb), 0.3);
}
.phase-result .held { filter: saturate(0.6); opacity: 0.75; }

/* The own pet sits beside the hand, live like the two others. */
.me { position: absolute; left: 8px; bottom: 16px; width: 160px; display: flex; flex-direction: column; align-items: center; gap: 2px; z-index: 4; pointer-events: none; }
.me .pill { box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.12), 0 4px 10px -4px rgba(var(--shadow-rgb), 0.3); }
.me .pill.turn { box-shadow: 0 0 0 2.5px var(--c-500), 0 4px 10px -4px rgba(var(--shadow-rgb), 0.3); }

.keys { position: absolute; left: 0; right: 0; bottom: 16px; height: 40px; display: flex; justify-content: center; gap: 12px; z-index: 5; }
.keys .ui-btn { height: 40px; min-width: 108px; font-size: 14px; }
.keys .ui-btn.bid { min-width: 84px; }
/* The corner of a keycap says which key of the keyboard it is. */
.keys kbd {
  height: 16px;
  margin-left: 3px;
  padding: 0 5px;
  border-radius: 4px;
  background: var(--c-100);
  font: 800 10px/16px var(--font-latin);
  letter-spacing: 0.4px;
  color: var(--c-700);
}
.keys .primary kbd { background: rgba(255, 255, 255, 0.45); color: var(--c-900); }
/* A key that cannot be pressed stays a key: flat paper with an outline, since the wall is the disabled colour. */
.keys .ui-btn:disabled { --key-top: var(--c-50); --key-bottom: var(--c-50); box-shadow: inset 0 0 0 1.5px var(--c-200); }
.keys .ui-btn:disabled kbd { background: transparent; color: var(--ink-3); }

.leave-note { margin: 0 0 18px; font-size: var(--fs-body); line-height: 1.6; color: var(--ink-2); }
.confirm { display: flex; justify-content: flex-end; gap: 10px; }
</style>
