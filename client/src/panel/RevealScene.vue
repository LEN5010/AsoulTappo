<script setup lang="ts">
// The reveal of a draw, played over the whole panel, sidebar and title bar included.
// Page-turn bands cover the page before the request goes out, because the stores update as soon
// as a response lands and the page underneath would give the result away. They give nothing away
// either: they uncover a board of identical backs, and only turning a tile shows what it is.
// A repeat has already turned into shards on the server; once its face is up the board stamps it
// and throws the shards into the counter at the foot, so nothing about repeats shows before a turn.
import { computed, nextTick, onBeforeUnmount, onDeactivated, onMounted, reactive, ref, shallowRef } from "vue";
import { assetUrl } from "../asset";
import * as sfx from "../audio/sfx";
import { characterColor } from "../manifest";
import type { Drop } from "../net/api";
import { DEAL_LIMIT } from "../reveal";
import { reducedMotion } from "../stores/theme";
import { ui } from "../stores/ui";
import { takeFocus, trapTab } from "../ui/focus";
import Icon from "../ui/Icon.vue";
import { createImagePreloader } from "../ui/imagePreloader";
import RevealBands from "./RevealBands.vue";
import RevealSpotlight from "./RevealSpotlight.vue";
import RevealTile from "./RevealTile.vue";
import { entriesOf, type BoardEntry } from "./reveal-board";

const props = defineProps<{
  /** Runs once the page is covered. null closes the scene, leaving the error to the page. */
  load: () => Promise<Drop[] | null>;
  /** Draws still queued after the batch in hand. */
  remaining?: number;
  /** Size of a repeat draw the player can afford from the board; 0 hides the button. */
  again?: number;
}>();
const emit = defineEmits<{ close: []; again: [] }>();

const DWELL_MS = 220;
/** Bands start leaving when the board mounts; the first tile lands a beat later. */
const DEAL_AT_MS = 90;
/** Time into a tile's turn when its face shows, so the spotlight lifts the face, not the back. */
const SPOT_AFTER_MS = 300;
const TURN_STEP_MS = 70;
/** Time from a turn to the stamp: the face has settled. */
const STAMP_AFTER_TURN_MS = 560;
/** Time from a tile dealt face up landing to its stamp. */
const STAMP_AFTER_DEAL_MS = 520;
/** Spacing between stamps, tighter once many are waiting. */
const STAMP_STEP_MS = 120;
const STAMP_STEP_BUSY_MS = 45;
/** Time from the stamp to the first shard leaving it. */
const SHARDS_AFTER_STAMP_MS = 200;
const SHARD_MS = 640;
const SHARD_STEP_MS = 45;
/** Past this many shards in the air, each tile throws one. */
const SHARDS_AIRBORNE_MAX = 24;
const SHARD_EASE = "cubic-bezier(0.12, 0.6, 0.88, 0.4)";
const SHARD_SVG = '<svg viewBox="-2 0 28 24"><path d="M12 3l6 7-6 11-6-11z"/><path class="cut" d="M6 10h12M12 3l-2 7 2 11 2-11z"/></svg>';

const calm = computed(() => reducedMotion.value);
const phase = ref<"cover" | "board">("cover");
const asking = ref(1);
const drops = shallowRef<Drop[]>([]);
const entries = shallowRef<BoardEntry[]>([]);
const opened = reactive(new Set<number>());
const turned = reactive(new Set<number>());
const spot = shallowRef<{ index: number; tile: HTMLElement | null } | null>(null);
const auto = ref(false);
/** Draws left as the board shows them. A repeat bumps the page's queue before its bands have covered the old board. */
const frozen = ref<number | null>(null);
const left = computed(() => frozen.value ?? props.remaining ?? 0);
let alive = true;
let round = 0;
let spotDone: (() => void) | undefined;

const wait = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

const bands = ref<InstanceType<typeof RevealBands>>();
const spotlight = ref<InstanceType<typeof RevealSpotlight>>();

const grouped = computed(() => drops.value.length > DEAL_LIMIT);
const single = computed(() => entries.value.length === 1);
const shape = computed(() => {
  const n = entries.value.length;
  const cols = Math.min(n, n > 6 ? 5 : n === 6 ? 3 : n);
  return { "--cols": cols, "--rows": Math.ceil(n / cols), "--deal-at": `${DEAL_AT_MS}ms` };
});
const sealedLeft = computed(() => entries.value.some((_, i) => !opened.has(i)));
const newCount = computed(() => drops.value.filter((d) => d.new).length);

/** Tiles whose repeats have been stamped, and the shards that have reached the counter so far. */
const exchanged = reactive(new Set<number>());
const paid = ref(0);
/** Bumped as each shard lands, to replay the counter's pop. */
const bump = ref(0);
const flightLayer = ref<HTMLElement>();
const scheduled = new Set<number>();
const timers = new Set<ReturnType<typeof setTimeout>>();
let stampAt = 0;
let waiting = 0;
let airborne: Animation[] = [];

/** Stops what is still on its way: queued stamps and shards in the air. */
function stopExchange() {
  for (const t of timers) clearTimeout(t);
  timers.clear();
  stampAt = 0;
  waiting = 0;
  for (const a of airborne) a.cancel();
  airborne = [];
}
/** Clears the stamps and the counter, once the board they belong to is covered. */
function clearExchange() {
  exchanged.clear();
  scheduled.clear();
  paid.value = 0;
}
function later(fn: () => void, ms: number) {
  const t = setTimeout(() => {
    timers.delete(t);
    fn();
  }, ms);
  timers.add(t);
}

function credit(shards: number) {
  paid.value += shards;
  bump.value += 1;
}

/** Stamps a tile whose face is up `delay` ms from now, after any stamps already waiting. */
function exchange(index: number, delay: number) {
  const shards = entries.value[index]?.drop.shards ?? 0;
  if (!shards || scheduled.has(index)) return;
  scheduled.add(index);
  if (calm.value) {
    exchanged.add(index);
    credit(shards);
    return;
  }
  const mine = round;
  const now = performance.now();
  const at = Math.max(now + delay, stampAt);
  stampAt = at + (waiting > 6 ? STAMP_STEP_BUSY_MS : STAMP_STEP_MS);
  waiting += 1;
  later(() => {
    waiting -= 1;
    if (!alive || mine !== round) return;
    exchanged.add(index);
    later(() => alive && mine === round && throwShards(index, shards), SHARDS_AFTER_STAMP_MS);
  }, at - now);
}

/** The shards leave the stamp in a fan, hang for a moment, then drop into the counter. */
function throwShards(index: number, shards: number) {
  const layer = flightLayer.value;
  const tile = root.value?.querySelectorAll<HTMLElement>(".tile")[index];
  const from = (tile?.querySelector(".stamp") ?? tile?.querySelector(".body"))?.getBoundingClientRect();
  const view = root.value?.querySelector(".deal")?.getBoundingClientRect();
  const mark = root.value?.querySelector<HTMLElement>(".tally .paid svg");
  const to = (mark?.getBoundingClientRect().width ? mark : root.value?.querySelector<HTMLElement>(".tally"))?.getBoundingClientRect();
  if (!layer || !from || !view || !to || closing.value) return credit(shards);
  const sx = from.left + from.width / 2;
  const sy = from.top + from.height / 2;
  // A tile scrolled out of the board's view pays without a flight.
  if (sy < view.top || sy > view.bottom) return credit(shards);

  const base = layer.getBoundingClientRect();
  const gold = entries.value[index]?.card?.tier === "small";
  const p0 = { x: sx - base.left, y: sy - base.top };
  const p3 = { x: to.left + to.width / 2 - base.left, y: to.top + to.height / 2 - base.top };
  const count = airborne.length > SHARDS_AIRBORNE_MAX ? 1 : shards >= 300 ? 7 : shards >= 40 ? 4 : shards >= 15 ? 3 : 2;
  const each = Math.floor(shards / count);
  const mine = round;
  for (let k = 0; k < count; k++) {
    const share = k === count - 1 ? shards - each * (count - 1) : each;
    // Fanned upward, a little uneven, the hidden card's further.
    const spread = count > 1 ? (k / (count - 1) - 0.5) * 120 : 0;
    const angle = ((-90 + spread + (Math.random() - 0.5) * 18) * Math.PI) / 180;
    const reach = (gold ? 70 : 48) + Math.random() * 26;
    const p1 = { x: p0.x + Math.cos(angle) * reach, y: p0.y + Math.sin(angle) * reach };
    const p2 = { x: p3.x + (p1.x - p3.x) * 0.2, y: p3.y - 90 };
    const spin = (k % 2 ? 1 : -1) * (220 + Math.random() * 160);
    const frames: Keyframe[] = [];
    for (let i = 0; i <= 24; i++) {
      const t = i / 24;
      const u = 1 - t;
      const x = u * u * u * p0.x + 3 * u * u * t * p1.x + 3 * u * t * t * p2.x + t * t * t * p3.x;
      const y = u * u * u * p0.y + 3 * u * u * t * p1.y + 3 * u * t * t * p2.y + t * t * t * p3.y;
      const scale = t < 0.12 ? 0.3 + (t / 0.12) * 0.9 : t < 0.3 ? 1.2 - ((t - 0.12) / 0.18) * 0.2 : t < 0.86 ? 1 : 1 - ((t - 0.86) / 0.14) * 0.5;
      const opacity = t < 0.06 ? t / 0.06 : t > 0.95 ? (1 - t) / 0.05 : 1;
      frames.push({ transform: `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) rotate(${(spin * t).toFixed(1)}deg) scale(${scale.toFixed(3)})`, opacity });
    }
    const piece = document.createElement("i");
    piece.className = gold ? "shard gold" : "shard";
    piece.innerHTML = SHARD_SVG;
    layer.append(piece);
    const distance = Math.hypot(p3.x - p0.x, p3.y - p0.y);
    const flight = piece.animate(frames, {
      duration: SHARD_MS + Math.min(320, distance * 0.3),
      delay: k * SHARD_STEP_MS,
      easing: SHARD_EASE,
      fill: "both",
    });
    airborne.push(flight);
    flight.finished.then(() => {
      if (alive && mine === round) credit(share);
    }, () => {}).finally(() => {
      piece.remove();
      airborne = airborne.filter((a) => a !== flight);
    });
  }
}

const artPreloader = createImagePreloader();
function preload(list: BoardEntry[], from = 0) {
  artPreloader.setWindow(list.slice(from).filter((e) => e.spot && e.card && !e.card.video)
    .map((e) => assetUrl(e.card!.full)));
}

/** `count` names the batch on the bands; a repeat passes it because its props have not caught up yet. */
async function run(count = props.remaining ?? 1) {
  const mine = ++round;
  frozen.value = phase.value === "board" ? left.value : null;
  spot.value = null;
  artPreloader.clear();
  spotDone = undefined;
  auto.value = false;
  stopExchange();
  asking.value = Math.max(1, Math.min(count, 100));

  // A repeat's bands sweep over the board it leaves; only then does the board go.
  sfx.stopTheme();
  if (!calm.value) {
    sfx.pageTurn();
    await bands.value?.cover();
  }
  if (!alive || mine !== round) return;
  phase.value = "cover";
  opened.clear();
  turned.clear();
  clearExchange();
  const [result] = await Promise.all([props.load(), wait(calm.value ? 0 : DWELL_MS)]);
  if (!alive || mine !== round) return;
  if (!result?.length) {
    emit("close");
    return;
  }
  drops.value = result;
  const list = entriesOf(result);
  preload(list);
  entries.value = list;
  list.forEach((e, i) => (!e.sealed || calm.value) && opened.add(i));
  phase.value = "board";
  frozen.value = null;
  await nextTick();
  // Tiles dealt face up (common ones in a grouped board) are stamped once they have landed.
  list.forEach((_, i) => opened.has(i) && exchange(i, DEAL_AT_MS + Math.min(i, 14) * 42 + STAMP_AFTER_DEAL_MS));
  if (!calm.value) await bands.value?.leave();
  if (alive && mine === round) root.value?.querySelector<HTMLElement>(".foot .primary")?.focus({ preventScroll: true });
}

function showSpot(index: number): Promise<void> {
  preload(entries.value, index);
  sfx.stopTheme();
  sfx.lift();
  // Cards bring their own sound to the spotlight; a skin has none, so it gets a theme.
  if (entries.value[index]?.item.kind === "character") sfx.startTheme();
  spot.value = { index, tile: root.value?.querySelectorAll<HTMLElement>(".tile")[index] ?? null };
  return new Promise((resolve) => (spotDone = resolve));
}
function spotClosed() {
  sfx.stopTheme();
  spot.value = null;
  void nextTick(() => root.value?.querySelector<HTMLElement>(".foot .primary")?.focus({ preventScroll: true }));
  const done = spotDone;
  spotDone = undefined;
  done?.();
}

async function turn(index: number) {
  const entry = entries.value[index];
  if (!entry) return;
  if (opened.has(index)) {
    if (entry.spot) await showSpot(index);
    return;
  }
  opened.add(index);
  if (!calm.value) turned.add(index);
  sfx.flip();
  if (!entry.spot) return exchange(index, STAMP_AFTER_TURN_MS);
  const mine = round;
  await wait(calm.value ? 0 : SPOT_AFTER_MS);
  if (alive && mine === round) await showSpot(index);
  // The stamp lands as the card does, back on its tile.
  if (alive && mine === round) exchange(index, 0);
}

function press(index: number) {
  if (auto.value || spot.value) return;
  void turn(index);
}

/** Quiet tiles turn in a quick ripple first, then each spotlight in board order. */
async function turnAll() {
  if (auto.value || spot.value) return;
  auto.value = true;
  const mine = round;
  const waiting = entries.value.map((_, i) => i).filter((i) => !opened.has(i));
  const quiet = waiting.filter((i) => !entries.value[i]!.spot);
  for (const i of quiet) {
    opened.add(i);
    if (!calm.value) turned.add(i);
    exchange(i, STAMP_AFTER_TURN_MS);
    sfx.flip(true);
    if (!calm.value) await wait(TURN_STEP_MS);
    if (!alive || mine !== round) return;
  }
  for (const i of waiting.filter((i) => entries.value[i]!.spot)) {
    if (!alive || mine !== round) return;
    await turn(i);
  }
  auto.value = false;
}

function finish() {
  if (left.value) void run();
  else void fadeOut();
}

/** 收下: the tiles drop away in board order, then the scene fades off the page it covered. */
const closing = ref(false);
const OUT_MS = 460;
async function fadeOut() {
  if (closing.value) return;
  sfx.stopTheme();
  if (calm.value) {
    emit("close");
    return;
  }
  closing.value = true;
  await wait(OUT_MS + Math.min(entries.value.length, 14) * 18);
  if (alive) emit("close");
}

/** A single draw gets a band of its tone and the facts beside it, instead of one card on a bare page. */
const solo = computed(() => (single.value ? entries.value[0] : undefined));
/** Only a first copy gets the stamp; how many are owned is already in the line under the name. */
const soloWord = computed(() => (solo.value?.drop.new ? "NEW" : ""));
function repeat() {
  const count = props.again ?? 1;
  emit("again");
  void run(count);
}

const root = ref<HTMLElement>();
let release: (() => void) | undefined;
function onKey(e: KeyboardEvent) {
  if (e.key === "Tab" && root.value) trapTab(root.value, e);
  if (e.key !== "Escape" || phase.value !== "board" || closing.value) return;
  if (spot.value) void spotlight.value?.close();
  else if (sealedLeft.value) void turnAll();
  else finish();
}
onMounted(async () => {
  sfx.prime();
  window.addEventListener("keydown", onKey);
  void run();
  await nextTick();
  release = takeFocus(root.value);
});
onBeforeUnmount(() => {
  alive = false;
  stopExchange();
  artPreloader.clear();
  sfx.stopTheme(0.2);
  window.removeEventListener("keydown", onKey);
  release?.();
});
// Teleported content stays behind when its page turns away (a desk shortcut can do that).
// Hiding or minimizing the window deactivates the whole panel; keep this reveal so it can resume.
onDeactivated(() => {
  if (!ui.panelOpen || ui.panelMinimized) return;
  emit("close");
});
</script>

<template>
  <Teleport defer to=".panel-overlay">
    <div
      ref="root" class="reveal" :class="[`phase-${phase}`, { calm, closing }]" data-overlay
      role="dialog" aria-modal="true" aria-label="共鸣结果" tabindex="-1"
    >
      <section v-if="phase === 'board'" class="board" :class="{ grouped, single }">
        <div class="deal ui-scroll" :class="{ solo: !!solo }" :style="shape">
          <i v-if="solo" class="solo-band" :class="[opened.has(0) ? solo.tone : 'tone-sealed', { calm }]" :style="opened.has(0) ? solo.toneStyle : undefined" aria-hidden="true"></i>
          <RevealTile
            v-for="(e, i) in entries" :key="e.key"
            :entry="e" :index="i" :open="opened.has(i)" :turned="turned.has(i)" :lifted="spot?.index === i" :calm="calm" :dense="grouped"
            :exchanged="exchanged.has(i)"
            @press="press(i)"
          />
          <div v-if="solo && opened.has(0)" class="solo-facts" :class="[solo.tone, { calm }]" :style="solo.toneStyle">
            <b v-if="soloWord" class="solo-word" aria-hidden="true">{{ soloWord }}</b>
            <span class="ui-tag dark solo-kind">{{ solo.kind }}</span>
            <h3>{{ solo.title }}</h3>
            <p class="who"><i :style="{ background: characterColor(solo.item.characters[0] ?? '') }"></i>{{ solo.who }}</p>
            <p class="own">
              <template v-if="solo.drop.new"><Icon name="spark" :size="17" />首次获得</template>
              <template v-else>已拥有</template>
              <small v-if="solo.drop.shards"><Icon name="shard" :size="14" />自动兑换 <b>+{{ solo.drop.shards }}</b> 碎片</small>
            </p>
          </div>
        </div>

        <footer class="foot">
          <p class="tally">
            <span class="total"><b>{{ drops.length }}</b>件</span>
            <span v-if="newCount"><Icon name="spark" :size="13" />新收藏 <b>{{ newCount }}</b></span>
            <span v-if="exchanged.size" class="paid" :class="{ empty: !paid }"><Icon name="shard" :size="15" />兑换 <b :key="bump" class="count">+{{ paid }}</b> 碎片</span>
          </p>
          <button v-if="sealedLeft" type="button" class="ui-btn primary large pulse" :disabled="auto" @click="turnAll">
            <Icon name="spark" :size="16" />全部翻开
          </button>
          <template v-else>
            <button v-if="again && !left" type="button" class="ui-btn large" :disabled="!!spot || frozen !== null || closing" @click="repeat">
              共鸣{{ again === 1 ? "一次" : "十次" }}
            </button>
            <button type="button" class="ui-btn primary large" :disabled="!!spot || frozen !== null || closing" @click="finish">
              {{ left ? `收下并继续（剩余 ${left} 次）` : "收下" }}
            </button>
          </template>
        </footer>

        <div ref="flightLayer" class="flights" aria-hidden="true"></div>

        <RevealSpotlight
          v-if="spot" ref="spotlight" :key="spot.index"
          :entry="entries[spot.index]!" :tile="spot.tile" :calm="calm" @done="spotClosed"
        />
      </section>

      <RevealBands v-if="!calm" ref="bands" :count="asking" />
    </div>
  </Teleport>
</template>

<style scoped>
.reveal {
  position: absolute;
  inset: 0;
  z-index: 40;
  container: reveal / size;
  overflow: hidden;
  outline: none;
  font-family: var(--font);
  color: var(--ink);
}
/* Clear while the bands sweep over the page, opaque once they cover it. */
.reveal.phase-board,
.reveal.calm {
  background: var(--c-50);
}

.board {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
}
.deal {
  --gap-x: 20px;
  --gap-y: 18px;
  --caption: 44px;
  --tile-max: 188px;
  flex: 1;
  min-height: 0;
  container: deal / size;
  display: flex;
  flex-wrap: wrap;
  align-content: center;
  justify-content: center;
  gap: var(--gap-y) var(--gap-x);
  padding: 22px 28px 10px;
  box-sizing: border-box;
  /* cq units measure the content box, inside the padding. */
  --tile-w: min(
    var(--tile-max),
    (100cqw - (var(--cols) - 1) * var(--gap-x)) / var(--cols),
    ((100cqh - (var(--rows) - 1) * var(--gap-y)) / var(--rows) - var(--caption)) * 0.7
  );
}
/* Leaves room for the facts column beside it. */
.single .deal {
  --tile-max: min(270px, 42cqw);
}
.grouped .deal {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(96px, 1fr));
  align-content: start;
  gap: 18px 16px;
  overflow-y: auto;
  --tile-w: 100%;
}

/* A sheet of paper along the bottom edge, as on the resonance page. */
.foot {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 20px 15px 24px;
  border-radius: 20px 20px 0 0;
  background: var(--surface);
  box-shadow: 0 -10px 28px -18px rgba(var(--shadow-rgb), 0.38), 0 -1px 2px rgba(var(--shadow-rgb), 0.05);
}
.tally {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 18px;
  margin: 0;
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--ink-2);
}
.tally span {
  display: inline-flex;
  align-items: baseline;
  gap: 4px;
  white-space: nowrap;
}
.tally b {
  font: 800 var(--fs-heading)/1 var(--font-latin);
  color: var(--ink);
}
.tally svg {
  align-self: center;
  stroke-width: 0;
  fill: var(--c-500);
}
.foot .ui-btn {
  min-width: 132px;
}
/* Shards land here; its icon is drawn like a shard in flight. */
.tally .paid svg {
  stroke: #fff;
  stroke-width: 1.6;
  fill: var(--c-500);
  filter: drop-shadow(0 1px 1px rgba(var(--shadow-rgb), 0.3));
}
/* Laid out from the first stamp so the shards have somewhere to fly, shown once the first one lands. */
.tally .paid {
  transition: opacity 180ms var(--ease-out);
}
.tally .paid.empty {
  opacity: 0;
}
.tally .count {
  display: inline-block;
  color: var(--c-700);
  animation: count-pop 320ms var(--ease-pop) both;
}
.calm /* Laid out from the first stamp so the shards have somewhere to fly, shown once the first one lands. */
.tally .paid {
  transition: opacity 180ms var(--ease-out);
}
.tally .paid.empty {
  opacity: 0;
}
.tally .count {
  animation: none;
}
.flights {
  position: absolute;
  inset: 0;
  z-index: 5;
  overflow: hidden;
  pointer-events: none;
}
.flights :deep(.shard) {
  position: absolute;
  left: 0;
  top: 0;
  width: 22px;
  height: 22px;
  margin: -11px 0 0 -11px;
  will-change: transform, opacity;
}
.flights :deep(svg) {
  display: block;
  width: 100%;
  height: 100%;
  overflow: visible;
  filter: drop-shadow(0 2px 2px rgba(var(--shadow-rgb), 0.3));
}
.flights :deep(path) {
  fill: var(--c-500);
  stroke: #fff;
  stroke-width: 2.2;
  stroke-linejoin: round;
}
.flights :deep(.cut) {
  fill: none;
  stroke: rgba(255, 255, 255, 0.7);
  stroke-width: 1.1;
}
.flights :deep(.gold) {
  width: 26px;
  height: 26px;
  margin: -13px 0 0 -13px;
}
.flights :deep(.gold svg) {
  filter: drop-shadow(0 0 5px rgba(var(--gold-rgb), 0.85));
}
.flights :deep(.gold path:first-child) {
  fill: var(--gold);
}
.closing .flights {
  animation: fade-out 160ms var(--ease-in) both;
}
@container reveal (max-width: 560px) {
  .tally .total {
    display: none;
  }
  .foot .ui-btn {
    min-width: 0;
    padding: 0 18px;
  }
}

/* A warm floor under the board, so the page is not bare white. */
.board {
  background: linear-gradient(180deg, transparent 45%, color-mix(in srgb, var(--c-200) 75%, transparent));
}

/* Single draw: the card on a band of its tone, the facts beside it. */
.deal.solo {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  align-items: center;
  column-gap: 40px;
}
.solo > :deep(.tile) {
  justify-self: end;
}
.solo :deep(.caption) {
  visibility: hidden;
}
/* NEW and 首次获得 beside the card already say it is new. */
.solo :deep(.fresh) {
  display: none;
}
.solo-band {
  position: absolute;
  z-index: -1;
  left: 0;
  right: 0;
  top: 24%;
  height: 46%;
  background: var(--tone-fill, var(--c-500));
  box-shadow: 0 0 0 6px rgba(255, 255, 255, 0.55);
  animation: solo-band-in 420ms var(--ease-in-out) both;
}
.solo-facts {
  justify-self: start;
  min-width: 0;
  max-width: 100%;
  /* Sits a little above the band's middle, so the name reads first. */
  translate: 0 -24px;
  color: var(--tone-ink, var(--ink));
  animation: solo-facts-in 380ms var(--ease-out) 160ms both;
}
.solo-band.calm,
.solo-facts.calm {
  animation: none;
}
.solo-word {
  display: block;
  margin-left: -3px;
  margin-bottom: 12px;
  font: 800 clamp(48px, 10cqw, 88px)/0.86 var(--font-latin);
  color: #fff;
  text-shadow: 0 2px 0 rgba(var(--shadow-rgb), 0.08);
}
.solo-kind {
  padding: 0 12px;
  font-size: 17px;
  line-height: 30px;
  border-radius: var(--radius-key-s);
}
.solo-facts h3 {
  margin: 12px 0 10px;
  font: 800 clamp(28px, 4.8cqw, 40px)/1.2 var(--font);
  text-wrap: balance;
}
/* White paper, so the member's tick reads on any band. */
.solo-facts .who {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  margin: 0;
  padding: 4px 12px 4px 9px;
  border-radius: var(--radius-key-s);
  background: var(--surface);
  box-shadow: var(--shadow-paper);
  color: var(--ink);
  font-size: 18px;
  font-weight: 800;
}
.solo-facts .who i {
  flex: none;
  width: 4px;
  height: 17px;
}
.solo-facts .own {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 6px;
  margin: 14px 0 0;
  font-size: 17px;
  font-weight: 800;
}
.solo-facts .own b {
  font: 800 var(--fs-number)/1 var(--font-latin);
}
.solo-facts .own small {
  display: flex;
  flex-basis: 100%;
  align-items: center;
  gap: 4px;
  font-size: 14px;
  font-weight: 700;
}
.solo-facts .own small b {
  font-size: 17px;
}
.solo-facts .own svg {
  stroke-width: 0;
  fill: currentColor;
}

/* 收下: tiles drop away in board order, then the whole scene fades off the page. */
.closing .tile {
  animation: tile-out 300ms var(--ease-in) calc(var(--i) * 18ms) both;
}
.closing .solo-band,
.closing .solo-facts,
.closing .foot {
  animation: fade-out 220ms var(--ease-in) both;
}
.reveal.closing {
  animation: fade-out 260ms var(--ease-in) 200ms both;
  pointer-events: none;
}

@keyframes solo-band-in {
  from { transform: translateX(-102%); }
  to { transform: none; }
}
@keyframes solo-facts-in {
  from { opacity: 0; transform: translateX(-16px); }
  to { opacity: 1; transform: none; }
}
@keyframes tile-out {
  from { opacity: 1; transform: none; }
  to { opacity: 0; transform: translateY(24px) scale(0.94); }
}
@keyframes fade-out {
  to { opacity: 0; }
}
@keyframes count-pop {
  0% { transform: scale(1.45); }
  100% { transform: none; }
}
</style>
