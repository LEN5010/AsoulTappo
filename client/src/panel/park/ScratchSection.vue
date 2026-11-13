<script setup lang="ts">
// The park's scratch cards (docs/design/amusement-park.md §5, docs/design/park-ui-rebuild.md §5.2): 阿草 keeps the
// stall from the park's coral band (band.ts: its face, and the odds behind the band's info key). Both cards lie on
// the table: the one picked straight in front, the other tilted behind it with its stub showing; pressing the one
// behind swaps them. A card is nine cells under a foil coating. Dragging over it scratches the coating off, and three
// cells alike are the prize. The server decides the prize when the card is bought and pays it when the card is
// revealed (scratchCards.ts), so the balance gives nothing away while the coating is on. Wins are celebrated by size:
// the coins back plainly, then three steps.
// A card of the old shard scratch cards (/api/scratch, stores/player.ts) still unrevealed comes onto the table first,
// alone and without a price, and is revealed the old way; then the table goes back to the two cards.
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from "vue";
import * as sfx from "../../audio/sfx";
import { assetUrl } from "../../asset";
import { characterColor, emoteCover } from "../../manifest";
import { collection, error as playerError, loadScratch, online, revealScratch, scratchCard, status } from "../../stores/player";
import { park, parkTry } from "../../stores/park";
import { sendEmote } from "../../stores/room";
import { settings } from "../../stores/settings";
import { reducedMotion } from "../../stores/theme";
import { ACHAO } from "../../ui/achao";
import NamePlate from "../../pet/NamePlate.vue";
import { allPlates, nameBand, plateSize, plateUnlocked } from "../../pet/plates";
import PlateDetail from "../PlateDetail.vue";
import Icon from "../../ui/Icon.vue";
import Modal from "../../ui/Modal.vue";
import asoulLogo from "../../assets/brand/asoul-logo.svg";
import { Coating, HOST, SCRATCH_EMOTES, ownedScratchEmotes } from "../../scratch";
import { parkTab, useBand } from "./band";
import { COIN_SMALL } from "./coin";
import {
  KINDS, SCRATCH, cellOf, faceOf, levelOf, oddsRows,
  outcomeOf, type CardKind, type Level, type ParkCard, type ParkPrize, type ParkReveal, type ParkScratchState,
} from "./scratchCards";

/** The rest of the coating lifts by itself once this much of it is gone. */
const DONE_SHARE = 0.55;
/** Brush radius as a share of the card's width. */
const BRUSH = 0.075;
/** Long enough for the card to land. */
const DEAL_MS = 460;
const NAMES: Record<CardKind, string> = { basic: "普通", premium: "豪华" };
const EMOTE_SET = SCRATCH.cards.basic.emote?.set ?? "";
const fmt = (n: number) => n.toLocaleString("en-US");
/** The best shard prize of a card, at the left of the bottom bar. */
const topPrize = (kind: CardKind) => Math.max(...SCRATCH.cards[kind].prizes.map((p) => p.shards));
/** Result tags by level: a miss and the coins back are plain, then coral, wine and gold. */
const TAGS: Record<string, string> = { 0: "light", plain: "light", 1: "", 2: "dark", 3: "gold" };
/** Stickers in the album lean a little, each its own way. */
const leanOf = (n: number) => `${((n * 7) % 5) * 2 - 4}deg`;
const emoteSrc = (key: string) => assetUrl(emoteCover(key));

const calm = computed(() => reducedMotion.value);
const coins = computed(() => park.value?.coins ?? status.value?.park?.coins ?? 0);
const ownedKeys = computed(() => new Set(ownedScratchEmotes(collection.owned)));
const pity = ref(0);
/** The server's word on the set (an emote on an unrevealed old card counts), else the album's. */
const whole = ref<boolean | null>(null);
const complete = computed(() => whole.value ?? ownedKeys.value.size >= SCRATCH_EMOTES.length);
const pityMax = SCRATCH.cards.basic.emote?.pity ?? 10;
const pityPercent = computed(() => Math.min(100, (pity.value / pityMax) * 100));

/** The plate the whole set unlocks, under the album as a partner at x0.7 would see it, standing still. */
const albumPlate = allPlates().find((p) => p.kind === "sweep" && p.set === EMOTE_SET) ?? null;
const PLATE_SCALE = 0.7;
const plateBox = plateSize(PLATE_SCALE);
const plateFont = nameBand(PLATE_SCALE).font;
const plateOpen = computed(() => !!albumPlate && plateUnlocked(albumPlate.id, collection.owned));
const plateNick = computed(() => settings.nick.trim() || "匿名小面包");
const plateView = ref(false);

/** The card lying in front. */
const kind = ref<CardKind>("basic");
const table = computed(() => SCRATCH.cards[kind.value]);
/** The card on the table: under its coating, then open. */
const card = ref<ParkCard | null>(null);
/** The card on the table is an old shard card (its cells read the same, its amounts are shards like the basic card's). */
const old = ref(false);
/** A coin card still to reveal while an old card holds the table: it comes next. */
let waiting: ParkCard | null = null;
/** Old cards revealed here: the panel's copy of the desk's state may still hold one for a moment. */
const doneOld = new Set<number>();
const open = ref(false);
/** The open card's prize, once it has reached the save. */
const prize = ref<ParkPrize | null>(null);
const paying = ref(false);
const buying = ref(false);
/** The card is on its way down to the table. */
const dealing = ref(false);
/** The coating is drawn for this card; the cells stay hidden until it is. */
const coated = ref(0);
/** Nothing has touched the coating yet, so it keeps its sheen. */
const untouched = ref(true);
/** The emote the open card just added to the album. */
const fresh = ref("");
const odds = ref(false);
const error = ref("");

/** The tickets on the table: both, or the old card alone. */
const deck = computed<readonly CardKind[]>(() => (old.value ? [kind.value] : KINDS));
const other = computed<CardKind>(() => (kind.value === "basic" ? "premium" : "basic"));

const outcome = computed(() => (card.value ? outcomeOf(card.value.cells) : null));
const cells = computed(() => card.value?.cells.map(cellOf) ?? Array.from({ length: 9 }, () => null));
const result = computed(() => (open.value ? outcome.value : null));
const level = computed<Level>(() => (result.value && card.value ? levelOf(result.value, card.value.kind, prize.value) : 0));
const winAt = computed(() => new Set(result.value && result.value.kind !== "miss" ? result.value.at : []));
/** What the card paid, as its tag says it: an amount once known, else the thing won. */
const resultText = computed(() => {
  const r = result.value;
  if (!r) return "";
  const p = prize.value;
  if (p && p.shards && !p.item) return `+${fmt(p.shards)}`;
  switch (r.kind) {
    case "shards": return `+${fmt(r.amount)}`;
    case "emote": return "新表情";
    case "again": return "再来一张";
    case "skin": return "新皮肤";
    case "big": return "大隐藏卡";
    case "jackpot": return "全服奖池";
    default: return "没中";
  }
});
const resultAmount = computed(() => resultText.value.startsWith("+"));

const cost = computed(() => table.value.coins);
const short = computed(() => coins.value < cost.value);
/** 阿草 touts while the stall is open, watches a card being scratched, and takes each result personally. */
const hostFace = computed(() => {
  if (result.value) return faceOf(result.value, level.value);
  if (card.value) return HOST.watching;
  return short.value ? HOST.closed : HOST.open;
});
useBand("scratch", () => ({ host: ACHAO[hostFace.value], info: { label: "概率", open: () => (odds.value = true) } }));

/** The open card's prize did not get through: the key collects it again before anything else. */
const unpaid = computed(() => !!card.value && open.value && !prize.value && !paying.value);
const settled = computed(() => !card.value || (open.value && !!prize.value));
const canBuy = computed(() => online.value && !old.value && !short.value && !buying.value && !paying.value && settled.value);
/** The card behind can come to the front: nothing is being scratched, bought or paid. */
const canSwap = computed(() => !old.value && settled.value && !buying.value && !paying.value);
/** Too few coins for the card in front: the main key's place sends the player to the coin page. */
const toCoins = computed(() => online.value && short.value && !unpaid.value && !old.value && settled.value);
const keyLabel = computed(() => {
  if (unpaid.value) return "再试一次";
  if (old.value) return "下一张";
  if (!online.value) return "未连接";
  return card.value ? "再来一张" : "买一张";
});

let timers: ReturnType<typeof setTimeout>[] = [];
const later = (ms: number, fn: () => void) => timers.push(setTimeout(fn, ms));

// ---- the coating: foil on a canvas over the cells, erased along the pointer
/** The live coating of the card on the table. */
const canvas = ref<HTMLCanvasElement | null>(null);
/** The coating printed on each empty ticket: drawn the same way, never scratched. */
const idle: Partial<Record<CardKind, HTMLCanvasElement>> = {};
const deckEl = ref<HTMLElement>();
let coating = new Coating();
let last: { x: number; y: number } | null = null;

function setCanvas(el: unknown) {
  const next = (el as HTMLCanvasElement | null) ?? null;
  if (canvas.value !== next) canvas.value = next;
}
function setIdle(k: CardKind, el: unknown) {
  const next = (el as HTMLCanvasElement | null) ?? undefined;
  if (idle[k] === next) return;
  idle[k] = next;
  if (next) void nextTick(paintIdle);
}

/** The A-SOUL mark pressed into the middle of the coating; drawn once it has loaded. */
const mark = new Image();
mark.src = asoulLogo;
mark.onload = () => {
  paintIdle();
  // A card dealt before the mark arrived gets its coating again, as long as nobody has scratched it.
  if (card.value && !open.value && untouched.value && coated.value === card.value.id) {
    coated.value = 0;
    paint();
  }
};
const MARK_RATIO = 2287 / 721;

const FALLBACK: Record<string, string> = {
  "--c-400": "#FFAD8A", "--c-500": "#FC966E", "--c-600": "#F17D5C", "--c-700": "#C34637", "--gold": "#E59B35", "--gold-soft": "#FFE3A6",
};
const rgbOf = (hex: string) => {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.replace(/./g, "$&$&") : h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};
/** `a` mixed into `b` at share `t`: canvas takes no color-mix(). */
const mix = (a: string, b: string, t: number) => {
  const pa = rgbOf(a);
  const pb = rgbOf(b);
  return `rgb(${pa.map((v, i) => Math.round(v * t + pb[i]! * (1 - t))).join(", ")})`;
};

/** The mark in one flat colour, on a canvas of its own (the file is black). */
function markIn(color: string, w: number, h: number): HTMLCanvasElement | null {
  const tint = document.createElement("canvas");
  tint.width = w;
  tint.height = h;
  const t = tint.getContext("2d");
  if (!t) return null;
  t.drawImage(mark, 0, 0, w, h);
  t.globalCompositeOperation = "source-in";
  t.fillStyle = color;
  t.fillRect(0, 0, w, h);
  return tint;
}

/**
 * Sizes `el` to its box and fills it with the coating of a [k] card: coral foil for the basic card, gold for the
 * premium one; one diagonal band of light across it, and the A-SOUL mark pressed in white in the middle. False while
 * the page has no size.
 */
function drawCoat(el: HTMLCanvasElement, k: CardKind): boolean {
  const w = el.clientWidth;
  const h = el.clientHeight;
  const ctx = w && h ? el.getContext("2d") : null;
  if (!ctx) return false;
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  el.width = Math.round(w * dpr);
  el.height = Math.round(h * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const css = getComputedStyle(el);
  const tok = (name: string) => css.getPropertyValue(name).trim() || FALLBACK[name]!;
  const gold = k === "premium";
  const fill = ctx.createLinearGradient(0, 0, w, h);
  let shade: string;
  if (gold) {
    // --grad-gold, laid across the diagonal.
    shade = mix(tok("--gold"), tok("--c-700"), 0.78);
    fill.addColorStop(0, tok("--gold-soft"));
    fill.addColorStop(0.54, tok("--gold"));
    fill.addColorStop(1, shade);
  } else {
    shade = tok("--c-600");
    fill.addColorStop(0, tok("--c-400"));
    fill.addColorStop(1, tok("--c-500"));
  }
  ctx.fillStyle = fill;
  ctx.fillRect(0, 0, w, h);
  const shine = ctx.createLinearGradient(0, 0, w, h);
  shine.addColorStop(0.3, "rgba(255, 255, 255, 0)");
  shine.addColorStop(0.41, `rgba(255, 255, 255, ${gold ? 0.5 : 0.36})`);
  shine.addColorStop(0.47, "rgba(255, 255, 255, 0.12)");
  shine.addColorStop(0.55, "rgba(255, 255, 255, 0)");
  ctx.fillStyle = shine;
  ctx.fillRect(0, 0, w, h);
  if (mark.complete && mark.naturalWidth) {
    const mw = Math.round(w * 0.5);
    const mh = Math.round(mw / MARK_RATIO);
    const pw = Math.round(mw * dpr);
    const ph = Math.round(mh * dpr);
    const x = (w - mw) / 2;
    const y = (h - mh) / 2;
    // Pressed in: the foil's shade along the lower edge, the white face over it.
    const under = markIn(shade, pw, ph);
    const face = markIn("#fff", pw, ph);
    if (under && face) {
      ctx.globalAlpha = 0.75;
      ctx.drawImage(under, x + 1, y + 1.5, mw, mh);
      ctx.globalAlpha = 0.95;
      ctx.drawImage(face, x, y, mw, mh);
      ctx.globalAlpha = 1;
    }
  }
  return true;
}

function paintIdle() {
  for (const k of KINDS) {
    const el = idle[k];
    if (el && el.isConnected) drawCoat(el, k);
  }
}

/** Draws a fresh coating for the card on the table. Does nothing while the page has no size (it is turned away). */
function paint() {
  const el = canvas.value;
  const current = card.value;
  if (!el || !current || open.value || coated.value === current.id) return;
  if (!drawCoat(el, current.kind)) return;
  coating = new Coating();
  last = null;
  untouched.value = true;
  coated.value = current.id;
}
watch(canvas, () => void nextTick(paint), { flush: "post" });

// The ticket follows the panel's height: coatings are drawn again at the new size (a scratched one is left as it is).
const resized = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => {
  paintIdle();
  if (card.value && !open.value && untouched.value) {
    coated.value = 0;
    paint();
  }
});
watch(deckEl, (el, was) => {
  if (was) resized?.unobserve(was);
  if (el) resized?.observe(el);
});
onBeforeUnmount(() => resized?.disconnect());

function scratchTo(e: PointerEvent) {
  const el = canvas.value;
  const ctx = el?.getContext("2d");
  if (!el || !ctx || open.value) return;
  const w = el.clientWidth;
  const h = el.clientHeight;
  const to = { x: e.offsetX / w, y: e.offsetY / h };
  const from = last ?? to;
  last = to;
  ctx.globalCompositeOperation = "destination-out";
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  ctx.lineWidth = BRUSH * 2 * w;
  ctx.beginPath();
  ctx.moveTo(from.x * w, from.y * h);
  ctx.lineTo(to.x * w, to.y * h);
  ctx.stroke();
  // A press that never moves still takes a dab off.
  ctx.beginPath();
  ctx.arc(to.x * w, to.y * h, BRUSH * w, 0, Math.PI * 2);
  ctx.fill();
  ctx.globalCompositeOperation = "source-over";
  untouched.value = false;
  if (coating.stroke(from.x, from.y, to.x, to.y, BRUSH) >= DONE_SHARE) finish();
}
function down(e: PointerEvent) {
  if (e.button !== 0 || open.value) return;
  (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  last = null;
  scratchTo(e);
}
function move(e: PointerEvent) {
  if (last && e.buttons & 1) scratchTo(e);
}
function up() {
  last = null;
}

// ---- the round: buy, scratch, collect; swap the cards between rounds
function take(state: ParkScratchState) {
  pity.value = state.pity;
  whole.value = state.emotesWhole;
}

/** A card comes onto the table: the one just bought, or one left unrevealed by an earlier visit. */
function put(next: ParkCard, fromOld = false) {
  old.value = fromOld;
  kind.value = next.kind;
  card.value = next;
  open.value = false;
  prize.value = null;
  fresh.value = "";
  sfx.flip(true);
  if (!calm.value) {
    dealing.value = true;
    later(DEAL_MS, () => (dealing.value = false));
  }
  void nextTick(paint);
}

/** Clears a settled card off the table; a card waiting to be revealed, or an old one, comes next. */
function clear() {
  if (!settled.value) return;
  card.value = null;
  old.value = false;
  open.value = false;
  prize.value = null;
  fresh.value = "";
  error.value = "";
  const next = waiting;
  waiting = null;
  if (next) put(next);
  else offerOld();
  void nextTick(paintIdle);
}

/** The card behind comes to the front. */
function swap(next: CardKind) {
  if (!canSwap.value || next === kind.value) return;
  kind.value = next;
  sfx.flip(true);
  clear();
}

/** An old card still to reveal takes the table when nothing else is on it. */
function offerOld() {
  const pending = scratchCard.value;
  if (pending && !doneOld.has(pending.id) && !card.value) put({ id: pending.id, kind: "basic", cells: pending.cells }, true);
}
watch(scratchCard, offerOld);

let loading = false;
async function load() {
  if (loading) return;
  loading = true;
  const r = await parkTry<ParkScratchState>("GET", "/api/park/scratch");
  loading = false;
  if (!r.ok) return;
  take(r.data);
  const pending = r.data.card;
  if (!pending || (pending.id === card.value?.id && !old.value)) return;
  // An old card keeps the table until its result has been seen.
  if (card.value && (old.value || !settled.value)) waiting = pending;
  else put(pending);
}

async function buy() {
  if (!canBuy.value) return;
  error.value = "";
  buying.value = true;
  const r = await parkTry<ParkScratchState>("POST", "/api/park/scratch", { kind: kind.value });
  buying.value = false;
  if (!r.ok) {
    error.value = r.error.message;
    return;
  }
  take(r.data);
  if (r.data.card) put(r.data.card);
}

/** The coating is off: the card shows what it pays and the prize is collected. */
function finish() {
  if (!card.value || open.value) return;
  open.value = true;
  last = null;
  sfx.flip();
  const lv = outcome.value ? levelOf(outcome.value, card.value.kind) : 0;
  if (lv === 2 || lv === 3) sfx.pageTurn();
  void collect();
}

async function collect() {
  const current = card.value;
  if (!current || paying.value || prize.value) return;
  error.value = "";
  if (old.value) return collectOld(current);
  paying.value = true;
  const r = await parkTry<ParkReveal>("POST", "/api/park/scratch/reveal", { card: current.id });
  paying.value = false;
  if (!r.ok) {
    error.value = r.error.message;
    return;
  }
  take(r.data);
  if (card.value?.id !== current.id) return;
  prize.value = r.data.prize;
  const item = r.data.prize.item;
  if (item?.startsWith("emote:")) {
    fresh.value = item.slice(6);
    // The pet shows the new sticker off, to the room as well.
    sendEmote(fresh.value);
  }
}

async function collectOld(current: ParkCard) {
  paying.value = true;
  let p: Awaited<ReturnType<typeof revealScratch>> = null;
  try {
    p = await revealScratch(current.id);
  } catch (e) {
    // The desk window did not answer in time.
    playerError.value = e instanceof Error ? e.message : String(e);
  } finally {
    paying.value = false;
  }
  if (!p) {
    error.value = playerError.value || "无法连接服务器";
    return;
  }
  doneOld.add(current.id);
  if (card.value?.id !== current.id || !old.value) return;
  prize.value = { tier: p.item ? "emote" : p.shards ? "shards" : "miss", shards: p.shards, coins: 0, item: p.item };
  if (p.item?.startsWith("emote:")) {
    fresh.value = p.item.slice(6);
    sendEmote(fresh.value);
  }
  void load();
}

function press() {
  if (unpaid.value) void collect();
  else if (old.value) clear();
  else void buy();
}

let active = false;
// The page is kept alive: mounting (the park may open while the page is shown) and coming back both load the table.
onMounted(() => {
  sfx.prime();
  enter();
});
onActivated(enter);
function enter() {
  if (active) return;
  active = true;
  void load();
  void loadScratch();
  void nextTick(() => {
    paint();
    paintIdle();
  });
}
onDeactivated(() => {
  active = false;
  timers.forEach(clearTimeout);
  timers = [];
  dealing.value = false;
  last = null;
});
// Another save: its table starts empty, and its card still to reveal is asked for.
watch(() => status.value?.player, (player, was) => {
  if (!was || player === was) return;
  card.value = null;
  kind.value = "basic";
  old.value = false;
  waiting = null;
  prize.value = null;
  whole.value = null;
  void nextTick(paintIdle);
  if (active && player) {
    void load();
    void loadScratch();
  }
});
</script>

<template>
  <section class="stall" :class="[kind, { calm }]" aria-label="刮刮乐">
    <div class="floor">
      <div class="table" data-rise>
        <div ref="deckEl" class="deck" :class="{ solo: deck.length === 1 }">
          <!-- 16 times and up: a ring of light goes out from the card once; 100 times and the top prizes: gold rays. -->
          <i v-if="level === 2 || level === 3" :key="`burst-${card?.id}`" class="burst" :class="`burst-${level}`" aria-hidden="true"></i>

          <div
            v-for="k in deck" :key="k" class="ticket"
            :class="[k, k === kind
              ? ['front', level !== 0 ? `lv-${level}` : '', { on: !!card, deal: dealing, open }]
              : ['behind', { locked: !canSwap }]]"
          >
            <div class="paper">
              <!-- The stub: the A-SOUL mark, the card's name and price, and the number of the card on the table. -->
              <p class="stub" aria-hidden="true">
                <i class="stub-mark"></i>
                <template v-if="!(old && k === kind)">
                  <b class="name">{{ NAMES[k] }}</b>
                  <span class="price"><img :src="COIN_SMALL" alt="" draggable="false" />×{{ SCRATCH.cards[k].coins }}</span>
                </template>
                <span v-if="k === kind && card" class="serial">No.{{ String(card.id).padStart(6, "0") }}</span>
              </p>
              <div class="field">
                <template v-if="k === kind">
                  <ol class="cells" :class="{ veiled: !card || (!open && coated !== card.id) }">
                    <li v-for="(c, i) in cells" :key="i" :class="{ win: winAt.has(i), lose: !!result && !winAt.has(i) }">
                      <template v-if="c">
                        <span v-if="c.kind === 'shards'" class="amount" :class="{ long: c.amount >= 10000, longer: c.amount >= 100000 }">
                          <Icon name="shard" :size="16" />{{ c.amount }}
                        </span>
                        <img v-else-if="c.kind === 'emote'" :src="emoteSrc(c.key)" alt="" draggable="false" />
                        <span v-else-if="c.kind === 'again'" class="sym again"><img :src="COIN_SMALL" alt="" draggable="false" /><small>再来</small></span>
                        <span v-else-if="c.kind === 'jackpot'" class="sym pot"><Icon name="crown" :size="26" /><small>奖池</small></span>
                        <span v-else-if="c.kind === 'skin'" class="sym item"><Icon name="shirt" :size="26" /><small>皮肤</small></span>
                        <span v-else-if="c.kind === 'big'" class="sym item"><Icon name="card-spark" :size="26" /><small>大隐藏</small></span>
                        <i v-else class="sym blank stub-mark"></i>
                      </template>
                    </li>
                  </ol>
                  <canvas
                    v-show="card" :ref="setCanvas" class="coat" :class="{ gone: open }" aria-hidden="true"
                    @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up" @lostpointercapture="up"
                  ></canvas>
                </template>
                <canvas v-if="k !== kind || !card" :ref="(el) => setIdle(k, el)" class="coat idle" aria-hidden="true"></canvas>
                <i v-if="k === kind && card && !open && untouched && !calm" class="sheen" aria-hidden="true"></i>
              </div>
            </div>
            <b
              v-if="k === kind && result" :key="card?.id" class="ui-tag result"
              :class="[TAGS[String(level)], { word: !resultAmount, still: level === 0 || level === 'plain' }]" role="status"
            >
              <Icon v-if="resultAmount" name="shard" :size="26" />{{ resultText }}
            </b>
            <button
              v-if="k !== kind" type="button" class="swap" :aria-label="NAMES[k]" :disabled="!canSwap" @click="swap(k)"
            ></button>
          </div>
        </div>
      </div>

      <aside v-if="kind === 'basic'" class="album" data-rise>
        <h4 class="ui-label"><span>阿草表情</span><small>{{ ownedKeys.size }} / {{ SCRATCH_EMOTES.length }}</small></h4>
        <ol class="stickers ui-scroll">
          <li
            v-for="(e, i) in SCRATCH_EMOTES" :key="e.key"
            :class="{ has: ownedKeys.has(e.key), fresh: fresh === e.key }" :title="ownedKeys.has(e.key) ? e.name : undefined"
            :style="{ '--lean': leanOf(i) }"
          >
            <img :src="emoteSrc(e.key)" :alt="ownedKeys.has(e.key) ? e.name : ''" loading="lazy" decoding="async" draggable="false" />
          </li>
        </ol>
        <div class="album-foot">
          <b v-if="complete" class="done">已集齐</b>
          <div v-else class="pity">
            <span>保底<b>{{ pity }}</b><i>/ {{ pityMax }}</i></span>
            <div class="ui-bar"><i :style="{ width: `${pityPercent}%` }"></i></div>
          </div>
          <button
            v-if="albumPlate" type="button" class="album-plate" :class="{ locked: !plateOpen }"
            :title="`预览铭牌：${albumPlate.name}`" @click="plateView = true"
          >
            <NamePlate
              :card="albumPlate.id" :nick="plateNick" :color="characterColor(settings.character)"
              :width="plateBox.width" :height="plateBox.height" :font="plateFont" still
            />
          </button>
        </div>
      </aside>

      <!-- What only the premium card can win, as three emblems: the jackpot in gold, a skin and a big hidden card. -->
      <aside v-else class="prizes" data-rise>
        <figure class="emblem pot">
          <span class="medal"><Icon name="crown" :size="56" /></span>
          <figcaption>奖池</figcaption>
        </figure>
        <figure class="emblem">
          <span class="medal"><Icon name="shirt" :size="40" /></span>
          <figcaption>皮肤</figcaption>
        </figure>
        <figure class="emblem">
          <span class="medal"><Icon name="card-spark" :size="40" /></span>
          <figcaption>大隐藏</figcaption>
        </figure>
      </aside>
    </div>

    <PlateDetail v-if="plateView && albumPlate" :plate="albumPlate" @close="plateView = false" />
    <Modal v-if="odds" title="刮刮乐概率" heading @close="odds = false">
      <div class="odds">
        <table v-for="k in [kind, other]" :key="k" class="rates">
          <thead><tr><th>{{ NAMES[k] }}</th><th>概率</th><th v-if="k === 'basic' && !complete">保底</th></tr></thead>
          <tbody>
            <tr v-for="(row, n) in oddsRows(k, complete)" :key="n">
              <td>
                <span v-if="row.kind === 'shards'" class="prize"><Icon name="shard" :size="14" />{{ fmt(row.shards ?? 0) }}</span>
                <template v-else>{{ { jackpot: "全服奖池", skin: "皮肤", big: "大隐藏卡", emote: "阿草表情", again: "再来一张", miss: "没中" }[row.kind] }}</template>
              </td>
              <td>{{ row.rate }}</td>
              <td v-if="k === 'basic' && !complete">{{ row.pity ? `${row.pity} 张` : "—" }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </Modal>

    <div class="park-actions">
      <!-- A refusal stands in the bar beside the key, so the table does not move. -->
      <p v-if="error" class="ui-error stall-error" role="alert">{{ error }}</p>
      <span v-else-if="!old" class="top"><small>最高</small><Icon name="shard" :size="18" /><b>{{ fmt(topPrize(kind)) }}</b></span>
      <div class="park-actions-main">
        <button v-if="card && !open" type="button" class="ui-btn large peel" @click="finish">全部刮开</button>
        <template v-else-if="toCoins">
          <span class="price"><img :src="COIN_SMALL" alt="" draggable="false" />×{{ cost }}</span>
          <button type="button" class="ui-btn large go" @click="parkTab = 'coin'">去换驼币</button>
        </template>
        <button
          v-else type="button" class="ui-btn primary large buy" :class="{ pulse: canBuy && !card }"
          :disabled="!canBuy && !unpaid && !(old && settled)" :aria-busy="buying || paying" @click="press"
        >
          <span>{{ keyLabel }}</span>
          <small v-if="!unpaid && !old && online" class="buy-cost"><img :src="COIN_SMALL" alt="" draggable="false" />×{{ cost }}</small>
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* The stall, on the park's sheet under the coral band: the table and the column beside it, then the bottom bar. */
.stall {
  display: flex;
  flex-direction: column;
}
.stall-error {
  min-width: 0;
  margin: 0;
}
.floor {
  flex: 1;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(212px, 31%);
  align-items: center;
  gap: 20px;
  --floor-l: 18px;
  --floor-t: 4px;
  padding: var(--floor-t) 26px 4px var(--floor-l);
}

/* ---- the table: two tickets, one in front and one tilted behind it */
.table {
  align-self: stretch;
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
  /* Out to the sheet's left and top edges, so the rays of a big win end where the paper does. */
  margin: calc(var(--floor-t) * -1) 0 0 calc(var(--floor-l) * -1);
  padding: var(--floor-t) 0 22px var(--floor-l);
  /* The rays stay inside the table: the body would scroll. The bottom padding is room for the result tag. */
  overflow: clip;
}
/*
 * Sized by the panel's height. The ticket's width follows from its height: the field under the stub is square.
 * The deck leaves room above and to the right for the ticket behind.
 */
.deck {
  --h: clamp(260px, calc(100cqh - 322px), 400px);
  --stub-h: 46px;
  --pad: 16px;
  --w: calc(var(--h) - var(--stub-h) + var(--pad));
  /* Far enough up that the name and price on the stub behind clear the front ticket. */
  --dx: calc(var(--w) * 0.1);
  --dy: 34px;
  position: relative;
  flex: none;
  width: calc(var(--w) * 1.1 + 26px);
  height: calc(var(--h) + 56px);
}
/* The old card alone: no room kept for a ticket behind. */
.deck.solo {
  width: var(--w);
}
/* A ticket is a thing to keep, not a key: no lip. The shadow is a filter on the outer box, as the paper is cut. */
.ticket {
  position: absolute;
  left: 0;
  bottom: 0;
  width: var(--w);
  height: var(--h);
  filter: drop-shadow(0 1px 2px rgba(var(--c-900-rgb), 0.14)) drop-shadow(0 6px 10px rgba(var(--c-900-rgb), 0.12));
  transition: transform var(--dur-stage) var(--ease-out), filter var(--dur-base) var(--ease-out);
}
.ticket.front {
  z-index: 2;
}
/* The card being scratched lifts off the page a little more. */
.ticket.front.on {
  filter: drop-shadow(0 2px 2px rgba(var(--c-900-rgb), 0.16)) drop-shadow(0 14px 18px rgba(var(--c-900-rgb), 0.2));
}
.ticket.behind {
  z-index: 1;
  transform: translate(var(--dx), calc(var(--dy) * -1)) rotate(6deg);
}
.ticket.behind:not(.locked):hover {
  transform: translate(var(--dx), calc(var(--dy) * -1 - 6px)) rotate(4deg);
}
.swap {
  position: absolute;
  z-index: 3;
  inset: 0;
  padding: 0;
  border: 0;
  border-radius: var(--radius-l);
  background: none;
  cursor: pointer;
}
.swap:disabled {
  cursor: default;
}
.swap:focus-visible {
  outline: 2px solid var(--ink);
  outline-offset: 3px;
}
/* The card itself: coral, with a half-round bite out of each side on the stub's perforations. */
.paper {
  --notch: calc(var(--stub-h) - 6px);
  position: relative;
  height: 100%;
  display: flex;
  flex-direction: column;
  border-radius: var(--radius-l);
  background: var(--grad-sky);
  mask:
    radial-gradient(circle at 0 var(--notch), transparent 11px, #000 11.5px),
    radial-gradient(circle at 100% var(--notch), transparent 11px, #000 11.5px);
  mask-composite: intersect;
}
/* The inner rule of the card backs; the premium card's is gold. */
.paper::before {
  content: "";
  position: absolute;
  inset: 6px;
  border-radius: var(--radius-m);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.6);
  pointer-events: none;
}
.premium .paper::before {
  box-shadow: inset 0 0 0 3px var(--gold-soft), inset 0 0 0 4px rgba(var(--gold-rgb), 0.6);
}
/* Printed on the stub: the A-SOUL mark, the name, the price and the card's number; a row of perforations under it. */
.stub {
  position: relative;
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  height: var(--stub-h);
  margin: 0;
  padding: 2px 22px 0;
  box-sizing: border-box;
  color: var(--ink);
  white-space: nowrap;
  container: stub / inline-size;
}
.stub::after {
  content: "";
  position: absolute;
  left: 20px;
  right: 20px;
  bottom: 5px;
  height: 3px;
  background: radial-gradient(circle, rgba(255, 255, 255, 0.85) 1.1px, transparent 1.6px) 0 50% / 8px 3px repeat-x;
}
.stub-mark {
  flex: none;
  width: 58px;
  aspect-ratio: 3.172;
  background: #fff;
  mask: url("../../assets/brand/asoul-logo.svg") center / contain no-repeat;
  -webkit-mask: url("../../assets/brand/asoul-logo.svg") center / contain no-repeat;
}
.name {
  font: 800 var(--fs-section)/1 var(--font);
  letter-spacing: 0.06em;
}
.price,
.buy-cost {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: var(--ink);
}
.price img,
.buy-cost img {
  width: 18px;
  height: 18px;
  filter: drop-shadow(0 1px 1px rgba(var(--c-900-rgb), 0.25));
}
.serial {
  margin-left: auto;
  font: 800 var(--fs-label)/1 var(--font-latin);
  letter-spacing: 0.12em;
  opacity: 0.72;
}
/* A small ticket keeps its name and price; the number goes. */
@container stub (max-width: 300px) {
  .serial {
    display: none;
  }
}
/* The nine cells, and over them the coating, in a white window. */
.field {
  position: relative;
  flex: 1;
  container-type: inline-size;
  margin: 2px var(--pad) var(--pad);
  border-radius: var(--radius-m);
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.92);
}
.ticket.deal {
  animation: deal-in 440ms var(--ease-out) both;
}
@keyframes deal-in {
  from { opacity: 0; transform: translateY(-18px) rotate(-3deg) scale(0.94); }
}
.cells {
  position: absolute;
  inset: 0;
  display: grid;
  grid-template: repeat(3, minmax(0, 1fr)) / repeat(3, minmax(0, 1fr));
  gap: 2.8cqw;
  margin: 0;
  padding: 0;
  list-style: none;
}
/* Nothing shows through before the coating is drawn. */
.cells.veiled {
  visibility: hidden;
}
.cells li {
  position: relative;
  display: grid;
  place-items: center;
  min-width: 0;
  min-height: 0;
  border-radius: var(--radius-m);
  background: var(--c-100);
}
.ticket.on .cells li {
  background: var(--surface);
}
.cells img {
  max-width: 84%;
  max-height: 84%;
  object-fit: contain;
  filter: var(--sticker);
  user-select: none;
}
/* An emote is sized by its cell, not by the picture: the cell's row is sized by its content, so a percentage
 * max-height there does not hold and a tall emote spills out. */
.cells > li > img {
  position: absolute;
  inset: 8%;
  width: 84%;
  height: 84%;
  max-width: none;
  max-height: none;
}
/* Amounts scale with the card, so a long one stays inside its cell on a small panel. */
.amount {
  display: inline-flex;
  align-items: center;
  gap: 0.06em;
  font: 800 11.5cqw/1 var(--font-latin);
  color: var(--ink);
}
.amount.long {
  font-size: 9.6cqw;
}
.amount.longer {
  font-size: 8.2cqw;
}
.amount svg {
  width: 0.56em;
  height: 0.56em;
  color: var(--c-600);
}
/* The named symbols: a mark and a word under it. */
.sym {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.8cqw;
  color: var(--c-700);
}
.sym svg {
  width: 11cqw;
  height: 11cqw;
}
.sym small {
  font: 800 clamp(11px, 4.2cqw, 15px)/1 var(--font);
  color: var(--ink-2);
}
.sym.again img {
  width: 12cqw;
  height: 12cqw;
  filter: drop-shadow(0 1px 1px rgba(var(--c-900-rgb), 0.25));
}
.sym.pot {
  color: var(--gold);
}
.sym.blank {
  width: 52%;
  background: var(--c-200);
}
/* The three alike: framed in the prize's tone, the other six step back. */
.cells .win {
  --burst: rgba(var(--c-500-rgb), 0.7);
  z-index: 1;
  box-shadow: 0 0 0 3px var(--c-700), 0 0 14px 1px var(--burst);
  animation: cell-pop 520ms var(--ease-spring) both;
}
/* The coins back: framed, no glow and no pop. */
.lv-plain .cells .win {
  box-shadow: 0 0 0 2px var(--c-300);
  animation: none;
}
.lv-2 .cells .win {
  box-shadow: 0 0 0 3px var(--c-800), 0 0 16px 2px var(--burst);
}
.lv-3 .cells .win {
  box-shadow: 0 0 0 3px var(--gold), 0 0 20px 3px rgba(var(--gold-rgb), 0.8);
  background: linear-gradient(180deg, #FFFBF1, var(--gold-soft));
}
.cells .lose > * {
  opacity: 0.38;
  transition: opacity var(--dur-slow) var(--ease-out);
}
@keyframes cell-pop {
  0% { transform: scale(0.86); }
  55% { transform: scale(1.1); }
  100% { transform: none; }
}
/* Behind both tickets, centred on the front one. */
.burst {
  position: absolute;
  z-index: 0;
  left: calc(var(--w) / 2);
  top: calc(100% - var(--h) / 2);
  width: calc(var(--w) * 1.5);
  aspect-ratio: 1;
  border-radius: 50%;
  pointer-events: none;
  translate: -50% -50%;
}
.burst-2 {
  background: radial-gradient(circle, transparent 38%, rgba(var(--c-500-rgb), 0.55) 46%, transparent 60%);
  animation: ring-out 900ms var(--ease-out) both;
}
.burst-3 {
  width: calc(var(--w) * 1.6);
  background:
    radial-gradient(circle, rgba(var(--gold-rgb), 0.5), transparent 58%),
    repeating-conic-gradient(rgba(var(--gold-rgb), 0.55) 0deg 9deg, transparent 9deg 24deg);
  mask: radial-gradient(circle closest-side, #000 46%, transparent 94%);
  animation: rays 3.2s var(--ease-out) both;
}
@keyframes ring-out {
  from { opacity: 1; scale: 0.6; }
  to { opacity: 0; scale: 1.3; }
}
@keyframes rays {
  0% { opacity: 0; rotate: 0deg; scale: 0.7; }
  15% { opacity: 1; scale: 1; }
  70% { opacity: 1; }
  100% { opacity: 0; rotate: 70deg; }
}
.ticket.lv-3 {
  animation: lift 700ms var(--ease-spring) both;
}
@keyframes lift {
  40% { transform: translateY(-8px) scale(1.03); }
}

/* The coating: foil over the cells, scratched off along the pointer. */
.coat {
  position: absolute;
  left: 0;
  top: 0;
  width: 100%;
  height: 100%;
  border-radius: var(--radius-m);
  cursor: crosshair;
  touch-action: none;
}
/* An empty ticket's coating is only printed: nothing to scratch until a card is bought. */
.coat.idle {
  cursor: default;
  pointer-events: none;
}
/* Fades only on its way off: a new card's coating is there at once, so its cells never show through. */
.coat.gone {
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--dur-slow) var(--ease-out);
}
/* A band of light keeps crossing an untouched card. */
.sheen {
  position: absolute;
  inset: 0;
  border-radius: var(--radius-m);
  background: linear-gradient(105deg, transparent 38%, rgba(255, 255, 255, 0.4) 50%, transparent 62%) 160% 0 / 260% 100% no-repeat;
  animation: coat-sheen 3.2s var(--ease-in-out) infinite;
  pointer-events: none;
}
@keyframes coat-sheen {
  0%, 55% { background-position: 160% 0; }
  100% { background-position: -60% 0; }
}
/* What the card paid, stuck across its bottom edge. */
.result {
  position: absolute;
  z-index: 3;
  left: 50%;
  bottom: 0;
  translate: -50% 50%;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0 18px;
  border-radius: var(--radius-m);
  box-shadow: 0 3px 8px -3px rgba(var(--c-900-rgb), 0.35);
  font: 800 36px/50px var(--font-latin);
  animation: tag-in 420ms var(--ease-pop) 120ms both;
}
/* Words, not an amount: set in the text face. */
.result.word {
  font: 800 22px/50px var(--font);
  letter-spacing: 0.04em;
}
/* A miss and the coins back: the tag is just there. */
.result.still {
  animation: none;
}
@keyframes tag-in {
  from { opacity: 0; scale: 0.5; }
}

/* ---- the album: 阿草's twenty stickers, a slot each */
.album {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.album .ui-label {
  margin-bottom: 8px;
}
.stickers {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 7px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.stickers li {
  position: relative;
  display: grid;
  place-items: center;
  aspect-ratio: 1;
  border-radius: var(--radius-m);
  background: var(--c-50);
}
.stickers .has {
  background: var(--c-100);
}
/* Owned: the sticker in colour, stuck on a little crooked; it straightens under the pointer. Contour only: a fifth
 * pass over twenty tiles drops frames during page turns. */
.stickers img {
  position: absolute;
  inset: 12%;
  width: 76%;
  height: 76%;
  object-fit: contain;
  filter: var(--contour);
  user-select: none;
  transition: rotate var(--dur-base) var(--ease-out), scale var(--dur-base) var(--ease-out), filter var(--dur-base) var(--ease-out);
}
.stickers .has img {
  inset: 3%;
  width: 94%;
  height: 94%;
  rotate: var(--lean);
}
.stickers .has:hover img {
  rotate: 0deg;
  scale: 1.08;
}
/* Not owned yet: the same picture in grey, opaque and straight, without the white edge; it lights up under the pointer. */
.stickers li:not(.has) img {
  filter: grayscale(1);
}
.stickers li:not(.has):hover img {
  filter: none;
}
.stickers .fresh {
  outline: 2px solid var(--c-500);
  outline-offset: 2px;
}
.stickers .fresh img {
  animation: cell-pop 560ms var(--ease-spring) 200ms both;
}
.album-foot {
  display: flex;
  flex-direction: column;
}
.pity {
  padding-top: 12px;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-2);
}
.pity span {
  display: flex;
  align-items: baseline;
  gap: 4px;
  white-space: nowrap;
}
.pity b {
  margin-left: auto;
  font: 800 var(--fs-strong)/1 var(--font-latin);
  color: var(--ink);
}
.pity span i {
  font: 800 var(--fs-label)/1 var(--font-latin);
  font-style: normal;
  color: var(--ink-3);
}
.pity .ui-bar {
  height: 6px;
  margin-top: 4px;
}
.done {
  padding-top: 12px;
  font-size: var(--fs-strong);
  color: var(--c-700);
}
/* 阿草's plate under the album: grey until the set is whole. */
.album-plate {
  display: flex;
  justify-content: center;
  margin-top: 8px;
  padding: 4px 0;
  border: 0;
  border-radius: var(--radius-m);
  background: none;
  cursor: pointer;
}
.album-plate > * {
  transition: transform var(--dur-base) var(--ease-out);
}
.album-plate:hover > * {
  transform: translateY(-2px);
}
.album-plate.locked > * {
  filter: grayscale(1);
}
.album-plate:focus-visible {
  outline: 2px solid var(--c-500);
  outline-offset: 2px;
}

/* ---- the premium card's top prizes: three emblems, the jackpot's in gold */
.prizes {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  justify-items: center;
  align-content: center;
  gap: 20px 12px;
}
.emblem {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  margin: 0;
}
.emblem.pot {
  grid-column: 1 / -1;
}
.medal {
  display: grid;
  place-items: center;
  width: 92px;
  aspect-ratio: 1;
  border-radius: 50%;
  background: var(--grad-sky);
  color: #fff;
  box-shadow: 0 0 0 4px #fff, 0 7px 14px -6px rgba(var(--c-900-rgb), 0.45);
  rotate: 4deg;
}
.emblem:nth-child(2) .medal {
  rotate: -5deg;
}
.pot .medal {
  width: 132px;
  background: var(--grad-gold);
  color: var(--ink);
  rotate: -3deg;
}
.emblem figcaption {
  font: 800 var(--fs-strong)/1 var(--font);
  color: var(--ink-2);
}
.pot figcaption {
  font-size: var(--fs-number);
  color: var(--ink);
}

/* ---- the bottom bar: the card's top prize, and the main key */
.top {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.top small {
  margin-right: 4px;
  font: 700 var(--fs-label)/1 var(--font);
  color: var(--ink-2);
}
.top svg {
  color: var(--c-600);
}
.top b {
  font: 800 26px/1 var(--font-latin);
  color: var(--ink);
}
.buy,
.peel,
.go {
  min-width: 176px;
}
.buy-cost {
  margin-left: 4px;
  color: inherit;
}

/* ---- the odds: one table a card */
.odds {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.rates {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--fs-body);
}
th, td {
  text-align: left;
  padding: 10px 6px;
  border-bottom: 1px solid var(--c-100);
}
.prize {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font: 800 var(--fs-number)/1 var(--font-latin);
}
.prize svg {
  color: var(--c-600);
}

.calm .ticket,
.calm .stickers img {
  transition: none;
}
.calm .ticket.deal,
.calm .ticket.lv-3,
.calm .cells .win,
.calm .result,
.calm .stickers .fresh img {
  animation: none;
}
.calm .burst {
  display: none;
}

/* Narrow: the column goes under the table, the stickers in one row that scrolls sideways. */
@container panel (max-width: 760px) {
  .floor {
    grid-template-columns: minmax(0, 1fr);
    gap: 10px;
    --floor-l: 16px;
    --floor-t: 10px;
    padding: var(--floor-t) 16px 14px var(--floor-l);
  }
  .album .ui-label {
    margin-bottom: 6px;
  }
  .stickers {
    display: flex;
    gap: 6px;
    overflow-x: auto;
    padding-bottom: 6px;
  }
  .stickers li {
    flex: none;
    width: 52px;
  }
  .album-foot {
    flex-direction: row;
    align-items: center;
    gap: 16px;
  }
  .pity,
  .done {
    flex: 1;
    padding-top: 4px;
  }
  .album-plate {
    margin-top: 0;
  }
  .prizes {
    grid-template-columns: repeat(3, auto);
    justify-content: center;
    align-items: end;
    gap: 12px 28px;
    padding-block: 4px 8px;
  }
  .emblem.pot {
    grid-column: auto;
  }
  .medal {
    width: 68px;
  }
  .medal svg {
    width: 32px;
    height: 32px;
  }
  .pot .medal {
    width: 88px;
  }
  .pot .medal svg {
    width: 44px;
    height: 44px;
  }
  .buy,
  .peel,
  .go {
    min-width: 140px;
  }
}
@container panel (max-height: 560px) {
  .floor {
    --floor-t: 6px;
    padding-bottom: 10px;
  }
  .buy,
  .peel,
  .go {
    height: 40px;
  }
  .top b {
    font-size: 22px;
  }
}
</style>
