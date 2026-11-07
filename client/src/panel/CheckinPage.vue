<script setup lang="ts">
// Daily check-in: this month's calendar under a coral head where 阿草 keeps watch. Today's square is a sealed
// card; pressing it checks in and turns it over to 阿草's face for the prize and the shards it paid, 阿草 in the
// head pulls the same face, and the sidebar alpaca says something. Every day checked in keeps that face.
// Days come from the server in China time (see checkin.ts).
import { computed, onActivated, onDeactivated, onMounted, ref, watch } from "vue";
import * as sfx from "../audio/sfx";
import { checkin, checkins, error, loadCheckins, online, status } from "../stores/player";
import { alpacaSay } from "../stores/alpaca";
import { reducedMotion } from "../stores/theme";
import { ACHAO } from "../ui/achao";
import Icon from "../ui/Icon.vue";
import { monthCells, pickLine, prizeTone, reactionOf, type DayCell } from "./checkin";

const WEEKDAYS = ["一", "二", "三", "四", "五", "六", "日"];
/** Day tags in the tone of the prize: gold, wine, coral. */
const TAGS: Record<string, string> = { "tone-legendary": "gold", "tone-epic": "dark", "tone-rare": "" };
const tagOf = (prize: number) => TAGS[prizeTone(prize)];
/** The two biggest prizes wear the resonance card frames: gold, then rose. */
const FRAMES: Record<string, string> = { "tone-legendary": "frame-gold", "tone-epic": "frame-rose", "tone-rare": "" };
const frameOf = (prize: number) => FRAMES[prizeTone(prize)];
/** Stickers on the calendar lean a little, each day its own way. */
const leanOf = (day: number) => `${((day * 7) % 5) * 2 - 4}deg`;
const SPARKS = Array.from({ length: 10 }, (_, n) => ({
  angle: `${n * 36 + (n % 2) * 12}deg`,
  reach: `${64 + (n % 3) * 20}px`,
  icon: n % 3 === 1 ? "spark" : "shard",
  size: n % 3 === 0 ? 18 : n % 3 === 1 ? 13 : 15,
}));
/** 阿草 in the head before today is paid: it will not hand anything over. */
const HOST_IDLE = "拒绝";
/** The card lifts at least this long while the request is out, so the turn never comes as a jump. */
const ASK_MS = 360;
/** When the face comes round in the turn: the flash, the burst and the alpaca's line start here. */
const FACE_MS = 300;
const TURN_MS = 1100;
/** Long enough for the last square of the deal to land. */
const DEAL_MS = 1100;

const calm = computed(() => reducedMotion.value);
const month = computed(() => checkins.value);
const cells = computed(() => (month.value ? monthCells(month.value) : []));
const signedDays = computed(() => month.value?.days.length ?? 0);
const monthShards = computed(() => month.value?.days.reduce((n, d) => n + d.shards, 0) ?? 0);
const monthNo = computed(() => Number(month.value?.today.slice(5, 7)) || 0);
const year = computed(() => month.value?.today.slice(0, 4) ?? "");
/** The heartbeat's flag is the freshest; the month's covers the moment before the first status. */
const available = computed(() => status.value?.checkin?.available ?? month.value?.available ?? false);
const todayWon = computed(() => cells.value.find((c) => c?.when === "today")?.won);

/** Today's card is up and waiting for its result. */
const asking = ref(false);
/** The day whose card is turning over. */
const turning = ref("");
/** The top prize shakes the whole calendar. */
const jolt = ref(false);
/** 阿草 keeps the banker's face until today's card shows its own. */
const holding = ref(false);
const hostFace = computed(() => (holding.value || !todayWon.value ? HOST_IDLE : reactionOf(todayWon.value.prize)));
const canSign = computed(() => available.value && online.value && !!month.value && !asking.value && !turning.value);
/** Today is still a card: face down, lifted, or turning. */
const isCard = (c: DayCell) => c.when === "today" && (!c.won || asking.value || turning.value === c.date);
let lastLine = "";
let timers: ReturnType<typeof setTimeout>[] = [];
const later = (ms: number, fn: () => void) => timers.push(setTimeout(fn, ms));
const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

async function sign() {
  if (!canSign.value) return;
  error.value = "";
  asking.value = true;
  holding.value = true;
  const [r] = await Promise.all([checkin(), wait(calm.value ? 0 : ASK_MS)]);
  asking.value = false;
  if (!r) {
    holding.value = false;
    return;
  }
  const top = prizeTone(r.prize.index) === "tone-legendary";
  turning.value = r.prize.day;
  sfx.flip();
  if (top) sfx.pageTurn();
  later(calm.value ? 0 : FACE_MS, () => {
    holding.value = false;
    lastLine = pickLine(lastLine);
    alpacaSay(lastLine);
    jolt.value = top && !calm.value;
  });
  later(calm.value ? 0 : TURN_MS, () => {
    turning.value = "";
    jolt.value = false;
  });
}

// Each visit deals the month in: a wave of squares from the top-left corner to the bottom-right.
const dealing = ref(false);
onMounted(sfx.prime);
let active = false;
onActivated(() => {
  active = true;
  void loadCheckins();
  if (calm.value) return;
  dealing.value = true;
  later(DEAL_MS, () => (dealing.value = false));
});
onDeactivated(() => {
  active = false;
  timers.forEach(clearTimeout);
  timers = [];
  turning.value = "";
  jolt.value = false;
  holding.value = false;
  dealing.value = false;
});
// A new day (midnight, or a check-in on another device) or another save: fetch the month again.
watch(() => [status.value?.player, status.value?.checkin?.available] as const, ([player, open], [was, wasOpen]) => {
  if (active && player && (player !== was || (open && wasOpen === false))) void loadCheckins();
});
</script>

<template>
  <div class="checkin-page ui-scroll" :class="{ calm }">
    <p v-if="error" class="ui-error" role="alert">{{ error }}</p>

    <section class="calendar" :class="{ jolt }" aria-label="本月签到">
      <header class="head" data-rise>
        <div class="title">
          <span class="eyebrow" aria-hidden="true">CHECK-IN</span>
          <h2 class="month"><b>{{ monthNo || "–" }}</b>月<small>{{ year }}</small></h2>
        </div>
        <p class="tally">
          <span>已签<b>{{ signedDays }}</b>天</span>
          <span><Icon name="shard" :size="16" /><b>{{ monthShards.toLocaleString("en-US") }}</b></span>
        </p>
        <Transition name="host" mode="out-in" :css="!calm">
          <img :key="hostFace" class="host" :src="ACHAO[hostFace]" alt="" draggable="false" />
        </Transition>
      </header>

      <div class="sheet">
        <ol class="weekdays" aria-hidden="true">
          <li v-for="(w, i) in WEEKDAYS" :key="w" :class="{ weekend: i >= 5 }">{{ w }}</li>
        </ol>
        <ol class="days" :class="{ deal: dealing }">
          <li
            v-for="(c, i) in cells" :key="c?.date ?? `pad-${i}`"
            :class="c ? [c.when, { turning: turning === c.date }] : 'pad'"
            :style="{ '--wave': (i % 7) + Math.floor(i / 7) }"
          >
            <template v-if="c">
              <!-- Today, until it has turned over: a sealed card, the page's one key. -->
              <button
                v-if="isCard(c)" type="button" class="card"
                :class="[c.won ? prizeTone(c.won.prize) : '', { open: canSign, asking, turn: turning === c.date && !calm }]"
                :disabled="!canSign" :aria-label="c.won ? `${c.won.shards} 碎片` : '签到'" @click="sign"
              >
                <span class="flipper">
                  <span class="face back">
                    <i class="rule"></i>
                    <span class="num">{{ c.day }}</span>
                    <i class="mark"></i>
                    <b>签到</b>
                    <i v-if="canSign && !calm" class="sheen"></i>
                  </span>
                  <span class="face front tile" :class="c.won ? frameOf(c.won.prize) : ''">
                    <span class="num">{{ c.day }}</span>
                    <span v-if="c.won" class="won">
                      <img :src="ACHAO[reactionOf(c.won.prize)]" alt="" draggable="false" :style="{ rotate: leanOf(c.day) }" />
                      <b class="ui-tag amount" :class="tagOf(c.won.prize)">{{ c.won.shards }}</b>
                    </span>
                  </span>
                </span>
                <template v-if="turning === c.date && !calm">
                  <i class="ring" aria-hidden="true"></i>
                  <span class="burst" aria-hidden="true">
                    <i v-for="(s, n) in SPARKS" :key="n" :style="{ '--a': s.angle, '--d': s.reach }">
                      <Icon :name="s.icon" :size="s.size" />
                    </i>
                  </span>
                </template>
              </button>
              <span v-else-if="c.won" class="tile" :class="frameOf(c.won.prize)">
                <span class="num">{{ c.day }}</span>
                <span class="won">
                  <img :src="ACHAO[reactionOf(c.won.prize)]" alt="" draggable="false" :style="{ rotate: leanOf(c.day) }" />
                  <b class="ui-tag amount" :class="tagOf(c.won.prize)">{{ c.won.shards }}</b>
                </span>
                <Icon v-if="prizeTone(c.won.prize) === 'tone-legendary'" name="spark" :size="14" class="twinkle" />
              </span>
              <span v-else class="num">{{ c.day }}</span>
            </template>
          </li>
        </ol>
      </div>
    </section>
  </div>
</template>

<style scoped>
.checkin-page {
  height: 100%;
  box-sizing: border-box;
  overflow-y: auto;
  padding: 24px 20px 20px 16px;
  display: flex;
  flex-direction: column;
}

/* A desk calendar: a coral head over one sheet of paper. The squares are steps of the ramp, not sheets. */
.calendar {
  flex: 1 0 auto;
  display: flex;
  flex-direction: column;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: var(--shadow-paper);
}
.calendar.jolt {
  animation: jolt 520ms var(--ease-out);
}

/* ---- the head: the month, what it has paid, and 阿草 standing behind the sheet with its face over the top */
.head {
  --host-h: 144px;
  --host-room: 176px;
  position: relative;
  display: flex;
  align-items: flex-end;
  gap: 20px;
  min-height: 92px;
  padding: 14px 22px 14px;
  box-sizing: border-box;
  border-radius: var(--radius-l) var(--radius-l) 0 0;
  background: var(--grad-sky);
}
.title {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.eyebrow {
  font: 800 12px/1 var(--font-latin);
  letter-spacing: 0.26em;
  color: var(--ink);
  opacity: 0.72;
}
.month {
  display: flex;
  align-items: baseline;
  gap: 4px;
  margin: 0;
  font: 800 var(--fs-heading)/1 var(--font);
  color: #fff;
  white-space: nowrap;
}
.month b {
  font: 800 60px/0.8 var(--font-latin);
}
.month small {
  margin-left: 10px;
  font: 800 var(--fs-number)/1 var(--font-latin);
  letter-spacing: 0.08em;
  color: var(--ink);
}
.tally {
  display: flex;
  align-items: baseline;
  gap: 20px;
  margin: 0 var(--host-room) 0 auto;
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--ink);
  white-space: nowrap;
}
.tally span {
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
}
.tally svg {
  align-self: center;
  color: #fff;
}
.tally b {
  font: 800 28px/1 var(--font-latin);
}
/* 阿草 stands behind the sheet: the sheet cuts it off at the waist, its head clears the top of the calendar. */
.host {
  position: absolute;
  right: 14px;
  bottom: -38px;
  height: var(--host-h);
  max-width: var(--host-h);
  object-fit: contain;
  object-position: 50% 100%;
  rotate: 6deg;
  filter: var(--sticker-lg);
  pointer-events: none;
  user-select: none;
}
/* Swapping faces: it ducks behind the sheet and comes back up with the new one. */
.host-enter-active {
  transition: translate 460ms var(--ease-pop), rotate 460ms var(--ease-pop);
}
.host-leave-active {
  transition: translate 170ms var(--ease-in);
}
.host-enter-from,
.host-leave-to {
  translate: 0 72%;
}
.host-enter-from {
  rotate: -6deg;
}

.sheet {
  position: relative;
  z-index: 1;
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 12px 16px 16px;
  border-radius: 0 0 var(--radius-l) var(--radius-l);
  background: var(--surface);
}
.weekdays,
.days {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.weekdays {
  margin-bottom: 6px;
}
.weekdays li {
  text-align: center;
  font-size: var(--fs-label);
  font-weight: 800;
  color: var(--ink-3);
}
.weekdays .weekend {
  color: var(--c-700);
}
.days {
  flex: 1;
  grid-auto-rows: minmax(64px, 1fr);
}
.days li {
  position: relative;
  min-width: 0;
  border-radius: var(--radius-m);
}
/* A day still to come is an empty slot, a step of the ramp. */
.days .future {
  background: var(--c-50);
}
/* The turning card throws its burst over the squares around it. */
.days .turning {
  z-index: 3;
}
/* Starts as the page-turn bands begin to clear, and runs the same way they do, left to right. */
.deal > li:not(.pad) {
  animation: deal-in 440ms var(--ease-out) calc(140ms + var(--wave) * 26ms) both;
}
@keyframes deal-in {
  from { opacity: 0; transform: translateY(14px) scale(0.9); }
}
.num {
  position: absolute;
  z-index: 1;
  left: 9px;
  top: 8px;
  font: 800 var(--fs-strong)/1 var(--font-latin);
  color: var(--ink-2);
}
/* Days to come carry their numeral large and faint in the middle of the slot, like a printed calendar. */
.future .num {
  inset: 0;
  display: grid;
  place-items: center;
  font-size: 30px;
  color: var(--c-300);
}
/* A missed day is gone: no square, only its number. */
.past > .num {
  color: var(--ink-3);
  opacity: 0.6;
}
.today .num {
  color: var(--c-700);
}

/* ---- a day checked in: 阿草's face from that day on a tile, what it paid on a tag in the prize's tone */
.tile {
  position: absolute;
  inset: 0;
  box-sizing: border-box;
  border-radius: var(--radius-m);
  background: var(--c-100);
}
.tile.frame-gold,
.tile.frame-rose {
  border: 3px solid transparent;
  background: var(--tile-face) padding-box, var(--frame-fill) var(--frame-at) / var(--frame-size) border-box;
}
.tile.frame-gold {
  --tile-face: linear-gradient(180deg, #FFFBF1, var(--gold-soft));
}
.tile.frame-rose {
  --tile-face: linear-gradient(180deg, var(--c-50), var(--c-200));
}
.tile.frame-gold .num,
.tile.frame-rose .num {
  left: 6px;
  top: 5px;
}
/* Today, checked in: a coral ring around its tile. */
.today .tile {
  outline: 2px solid var(--c-500);
  outline-offset: 2px;
}
.won {
  position: absolute;
  inset: 10px 6px 5px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
}
.won img {
  flex: 1;
  min-height: 0;
  max-width: 100%;
  object-fit: contain;
  filter: var(--sticker);
}
.amount {
  position: relative;
  margin-top: -7px;
  padding: 0 6px;
  font: 800 var(--fs-label)/17px var(--font-latin);
}
.twinkle {
  position: absolute;
  z-index: 2;
  right: -6px;
  top: -7px;
  color: var(--gold);
  fill: var(--gold-soft);
  stroke-width: 1.4;
  pointer-events: none;
  animation: twinkle 2.4s var(--ease-in-out) infinite;
}

/* ---- today: a sealed card, its back a coral key that breathes while it can be pressed */
.card {
  --burst: var(--tone-glow, rgba(var(--c-500-rgb), 0.7));
  position: absolute;
  inset: 0;
  padding: 0;
  border: 0;
  border-radius: var(--radius-m);
  background: none;
  font: inherit;
  color: var(--ink);
  cursor: pointer;
  perspective: 520px;
}
.card:disabled {
  cursor: default;
}
.card.open::before {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  box-shadow: var(--glow-l);
  opacity: 0;
  pointer-events: none;
  animation: breathe 2.8s var(--ease-in-out) infinite;
}
.flipper {
  position: absolute;
  inset: 0;
  transform-style: preserve-3d;
  transform: rotateY(180deg);
  transition: translate var(--dur-release) var(--ease-spring);
}
.face {
  position: absolute;
  inset: 0;
  border-radius: var(--radius-m);
  backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
}
.back {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding-top: 4px;
  box-sizing: border-box;
  overflow: hidden;
  transform: rotateY(180deg);
  background: linear-gradient(180deg, var(--c-400), var(--c-500));
  box-shadow: 0 3px 0 var(--c-600), var(--shadow-backlight);
  transition: box-shadow var(--dur-release) var(--ease-spring);
}
/* The seal: an inner rule and the A-SOUL mark, as on the backs the resonance deals. */
.back .rule {
  position: absolute;
  inset: 5px;
  border-radius: var(--radius-s);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.6);
}
.back .num {
  color: #fff;
}
.back .mark {
  width: 46%;
  aspect-ratio: 3.172;
  background: #fff;
  filter: drop-shadow(0 1px 1px rgba(var(--c-900-rgb), 0.2));
  mask: url("../assets/brand/asoul-logo.svg") center / contain no-repeat;
  -webkit-mask: url("../assets/brand/asoul-logo.svg") center / contain no-repeat;
}
.back b {
  font: 800 var(--fs-strong)/1 var(--font);
  letter-spacing: 0.12em;
}
/* A band of light keeps crossing it while it waits to be pressed. */
.back .sheen {
  position: absolute;
  inset: 0;
  background: linear-gradient(105deg, transparent 38%, rgba(255, 255, 255, 0.55) 50%, transparent 62%) 160% 0 / 260% 100% no-repeat;
  animation: back-sheen 3.2s var(--ease-in-out) infinite;
  pointer-events: none;
}
.card.open:hover .back {
  background: linear-gradient(180deg, color-mix(in oklab, var(--c-400) 70%, #fff), var(--c-400));
}
.card.open:active .flipper {
  translate: 0 3px;
  transition-duration: var(--dur-press);
}
.card.open:active .back {
  box-shadow: 0 0 0 var(--c-600), var(--shadow-backlight);
  transition-duration: var(--dur-press);
}
/* Offline, or the month is still on its way: a flat card that cannot be pressed. */
.card:disabled:not(.asking):not(.turn) .back {
  background: var(--c-100);
  box-shadow: none;
}
.card:disabled:not(.asking):not(.turn) .back :is(b, .num) {
  color: var(--ink-3);
}
.card:disabled:not(.asking):not(.turn) .back .mark {
  background: var(--c-300);
  filter: none;
}
.card:disabled:not(.asking):not(.turn) .back .rule {
  box-shadow: inset 0 0 0 1px var(--c-200);
}
/* Pressed: the card rises off the page while the server answers. */
.asking .flipper {
  animation: card-lift 420ms var(--ease-in-out) infinite alternate;
}
/* The turn: a flash as the face comes round, a ring, and shards thrown out of the card. */
.turn .flipper {
  transform: rotateY(0deg);
  animation: card-turn 760ms both;
}
.turn .front::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: #fff;
  pointer-events: none;
  animation: turn-flash 760ms var(--ease-out) both;
}
.turn .won img {
  animation: sticker-pop 560ms var(--ease-spring) 300ms both;
}
.ring {
  position: absolute;
  z-index: 2;
  left: 50%;
  top: 50%;
  width: 150%;
  aspect-ratio: 1;
  translate: -50% -50%;
  border-radius: 50%;
  box-shadow: 0 0 0 3px var(--burst), inset 0 0 18px var(--burst);
  opacity: 0;
  pointer-events: none;
  animation: turn-ring 620ms var(--ease-out) 260ms both;
}
.burst {
  --far: 1;
  position: absolute;
  z-index: 3;
  left: 50%;
  top: 50%;
  pointer-events: none;
}
.tone-legendary .burst {
  --far: 1.6;
}
.burst i {
  position: absolute;
  left: 0;
  top: 0;
  rotate: var(--a);
  transform-origin: 0 0;
}
.burst svg {
  position: absolute;
  left: 0;
  top: 0;
  stroke-width: 0;
  fill: var(--burst);
  filter: drop-shadow(0 0 1px #fff) drop-shadow(0 0 2px #fff);
  animation: burst-fly 720ms var(--ease-out) 260ms both;
}

/*
 * Every step names the same functions in the same order, so the angle itself is interpolated.
 * Speeds up into edge-on, overshoots past face-up and settles: a damped spring written out by hand.
 */
@keyframes card-turn {
  0% { transform: rotateY(180deg) scale(1.06); animation-timing-function: cubic-bezier(0.45, 0, 0.9, 0.55); }
  40% { transform: rotateY(90deg) scale(1.2); animation-timing-function: cubic-bezier(0.15, 0.6, 0.35, 1); }
  72% { transform: rotateY(-14deg) scale(1.08); animation-timing-function: cubic-bezier(0.45, 0, 0.55, 1); }
  88% { transform: rotateY(5deg) scale(1); animation-timing-function: cubic-bezier(0.45, 0, 0.55, 1); }
  100% { transform: rotateY(0deg) scale(1); }
}
@keyframes card-lift {
  from { transform: rotateY(180deg) translateY(0) scale(1); }
  to { transform: rotateY(180deg) translateY(-5px) scale(1.06); }
}
@keyframes back-sheen {
  0%, 55% { background-position: 160% 0; }
  100% { background-position: -60% 0; }
}
@keyframes turn-flash {
  0%, 30% { opacity: 0; }
  42% { opacity: 0.95; }
  100% { opacity: 0; }
}
@keyframes turn-ring {
  0% { opacity: 1; scale: 0.3; }
  100% { opacity: 0; scale: 1.6; }
}
@keyframes burst-fly {
  0% { opacity: 0; translate: -50% -50%; scale: 0.2; }
  20% { opacity: 1; }
  100% { opacity: 0; translate: calc(var(--d) * var(--far) - 50%) -50%; scale: 1; }
}
@keyframes sticker-pop {
  0% { transform: scale(0.7); }
  55% { transform: scale(1.16); }
  100% { transform: none; }
}
@keyframes twinkle {
  0%, 100% { scale: 0.7; opacity: 0.6; }
  50% { scale: 1.1; opacity: 1; }
}
.calm .twinkle {
  animation: none;
}
.calm .card.open::before {
  opacity: 0.6;
  animation: none;
}
@keyframes jolt {
  0%, 100% { transform: none; }
  15% { transform: translate(-6px, 1px); }
  30% { transform: translate(5px, -2px); }
  45% { transform: translate(-4px, 2px); }
  60% { transform: translate(3px, -1px); }
  80% { transform: translate(-1px, 1px); }
}

@container panel (max-width: 760px) {
  .head {
    --host-h: 118px;
    --host-room: 132px;
    gap: 14px;
    padding-inline: 18px;
  }
  .month b {
    font-size: 50px;
  }
  .month small {
    display: none;
  }
  /* The two counts stack, so 阿草 keeps its corner. */
  .tally {
    flex-direction: column;
    align-items: flex-end;
    gap: 4px;
  }
  .tally b {
    font-size: 22px;
  }
}
@container panel (max-height: 600px) {
  .checkin-page {
    padding-top: 18px;
  }
  .head {
    --host-h: 120px;
    min-height: 78px;
  }
  .month b {
    font-size: 48px;
  }
  .days {
    grid-auto-rows: minmax(54px, 1fr);
    gap: 6px;
  }
}
</style>
