<script setup lang="ts">
// The reveal of a draw, played over the whole panel, sidebar and title bar included.
// Page-turn bands cover the page before the request goes out, because the stores update as soon
// as a response lands and the page underneath would give the result away. They announce the best
// result, then uncover a board where every result lands like a card stuck onto the page.
import { computed, nextTick, onBeforeUnmount, onDeactivated, onMounted, reactive, ref, shallowRef } from "vue";
import { assetUrl } from "../asset";
import { characterColor } from "../manifest";
import type { Drop } from "../net/api";
import { DEAL_LIMIT, tellOf, type Tell } from "../reveal";
import { reducedMotion } from "../stores/theme";
import { ui } from "../stores/ui";
import { takeFocus, trapTab } from "../ui/focus";
import Icon from "../ui/Icon.vue";
import RevealBands from "./RevealBands.vue";
import RevealSpotlight from "./RevealSpotlight.vue";
import RevealTile from "./RevealTile.vue";
import { entriesOf, memberTone, type BoardEntry } from "./reveal-board";

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
const TELL_LABEL: Record<"legendary" | "skin", string> = { legendary: "大隐藏", skin: "皮肤" };

const calm = computed(() => reducedMotion.value);
const phase = ref<"cover" | "board">("cover");
const asking = ref(1);
const drops = shallowRef<Drop[]>([]);
const entries = shallowRef<BoardEntry[]>([]);
const tell = ref<Tell>("plain");
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
const refund = computed(() => drops.value.reduce((n, d) => n + d.shards, 0));

const tellLabel = computed(() => {
  if (tell.value === "epic") {
    const n = drops.value.filter((d) => d.rarity === "epic").length;
    return n > 1 ? `史诗 ×${n}` : "史诗";
  }
  if (tell.value !== "legendary" && tell.value !== "skin") return "";
  const counts = (["legendary", "skin"] as const)
    .map((r) => [r, drops.value.filter((d) => d.rarity === r).length] as const)
    .filter(([, n]) => n > 0);
  return counts.map(([r, n]) => (n > 1 ? `${TELL_LABEL[r]} ×${n}` : TELL_LABEL[r])).join(" · ");
});
const tellStyle = computed(() => {
  if (tell.value !== "skin") return undefined;
  const skin = drops.value.find((d) => d.rarity === "skin");
  return skin ? memberTone(skin.item.slice(5)) : undefined;
});

function preload(list: BoardEntry[]) {
  for (const e of list) {
    if (!e.spot || !e.card || e.card.video) continue;
    const img = new Image();
    img.src = assetUrl(e.card.full);
    // Decode now, while the bands hold the screen, so the spotlight does not stall on it later.
    void img.decode().catch(() => {});
  }
}

/** `count` names the batch on the bands; a repeat passes it because its props have not caught up yet. */
async function run(count = props.remaining ?? 1) {
  const mine = ++round;
  frozen.value = phase.value === "board" ? left.value : null;
  spot.value = null;
  spotDone = undefined;
  auto.value = false;
  tell.value = "plain";
  asking.value = Math.max(1, Math.min(count, 100));

  // A repeat's bands sweep over the board it leaves; only then does the board go.
  if (!calm.value) await bands.value?.cover();
  if (!alive || mine !== round) return;
  phase.value = "cover";
  opened.clear();
  turned.clear();
  const [result] = await Promise.all([props.load(), wait(calm.value ? 0 : DWELL_MS)]);
  if (!alive || mine !== round) return;
  if (!result?.length) {
    emit("close");
    return;
  }
  drops.value = result;
  const list = entriesOf(result);
  preload(list);
  tell.value = tellOf(result);
  if (!calm.value) {
    await nextTick();
    await bands.value?.announce();
    if (!alive || mine !== round) return;
  }
  entries.value = list;
  list.forEach((e, i) => (!e.sealed || calm.value) && opened.add(i));
  phase.value = "board";
  frozen.value = null;
  await nextTick();
  if (!calm.value) await bands.value?.leave();
  if (alive && mine === round) root.value?.querySelector<HTMLElement>(".foot .primary")?.focus({ preventScroll: true });
}

function showSpot(index: number): Promise<void> {
  spot.value = { index, tile: root.value?.querySelectorAll<HTMLElement>(".tile")[index] ?? null };
  return new Promise((resolve) => (spotDone = resolve));
}
function spotClosed() {
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
  if (!entry.spot) return;
  const mine = round;
  await wait(calm.value ? 0 : SPOT_AFTER_MS);
  if (alive && mine === round) await showSpot(index);
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
  window.addEventListener("keydown", onKey);
  void run();
  await nextTick();
  release = takeFocus(root.value);
});
onBeforeUnmount(() => {
  alive = false;
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
          <i v-if="solo" class="solo-band" :class="[solo.tone, { calm }]" :style="solo.toneStyle" aria-hidden="true"></i>
          <RevealTile
            v-for="(e, i) in entries" :key="e.key"
            :entry="e" :index="i" :open="opened.has(i)" :turned="turned.has(i)" :lifted="spot?.index === i" :calm="calm" :dense="grouped"
            @press="press(i)"
          />
          <div v-if="solo && opened.has(0)" class="solo-facts" :class="[solo.tone, { calm }]" :style="solo.toneStyle">
            <b v-if="soloWord" class="solo-word" aria-hidden="true">{{ soloWord }}</b>
            <span class="ui-tag dark solo-kind">{{ solo.kind }}</span>
            <h3>{{ solo.title }}</h3>
            <p class="who"><i :style="{ background: characterColor(solo.item.characters[0] ?? '') }"></i>{{ solo.who }}</p>
            <p class="own">
              <template v-if="solo.drop.new"><Icon name="spark" :size="14" />首次获得</template>
              <template v-else>已拥有 <b>×{{ solo.drop.count }}</b></template>
              <small v-if="solo.drop.shards">重复返还 {{ solo.drop.shards }} 碎片</small>
            </p>
          </div>
        </div>

        <footer class="foot">
          <p class="tally">
            <span><b>{{ drops.length }}</b>件</span>
            <span v-if="newCount"><Icon name="spark" :size="13" />新收藏 <b>{{ newCount }}</b></span>
            <span v-if="refund">重复返还 <b>+{{ refund }}</b> 碎片</span>
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

        <RevealSpotlight
          v-if="spot" ref="spotlight" :key="spot.index"
          :entry="entries[spot.index]!" :tile="spot.tile" :calm="calm" @done="spotClosed"
        />
      </section>

      <RevealBands v-if="!calm" ref="bands" :count="asking" :tell="tell" :tell-label="tellLabel" :tell-style="tellStyle" />
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
@container reveal (max-width: 560px) {
  .tally span:last-child {
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
  padding: 0 10px;
  font-size: var(--fs-body);
  line-height: 24px;
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
  font-size: var(--fs-strong);
  font-weight: 800;
}
.solo-facts .who i {
  flex: none;
  width: 4px;
  height: 14px;
}
.solo-facts .own {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 6px;
  margin: 14px 0 0;
  font-size: var(--fs-body);
  font-weight: 700;
}
.solo-facts .own b {
  font: 800 var(--fs-number)/1 var(--font-latin);
}
.solo-facts .own small {
  flex-basis: 100%;
  font-size: var(--fs-label);
  font-weight: 700;
  opacity: 0.8;
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
</style>
