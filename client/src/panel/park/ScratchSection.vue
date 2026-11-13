<script setup lang="ts">
// The park's scratch cards (docs/design/amusement-park.md §5): 阿草 keeps a stall under a coral head. The sheet
// first holds the two cards, basic and premium; picking one opens the table, where a card is nine cells under a
// coating. Dragging over it scratches the coating off, and three cells alike are the prize. The server decides the
// prize when the card is bought and pays it when the card is revealed (scratchCards.ts), so the balance gives
// nothing away while the coating is on. Wins are celebrated by size: the coins back plainly, then three steps.
// A card of the old shard scratch cards (/api/scratch, stores/player.ts) still unrevealed comes onto the table first,
// without a price, and is revealed the old way; then the sheet goes back to the two cards.
import { computed, nextTick, onActivated, onDeactivated, onMounted, ref, watch } from "vue";
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
/** The best shard prize of a card, printed on it in the picker. */
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

/** The card picked in the sheet; null while the sheet shows both. */
const kind = ref<CardKind | null>(null);
const table = computed(() => (kind.value ? SCRATCH.cards[kind.value] : null));
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
/** 阿草 touts while the stall is open, watches a card being scratched, and takes each result personally. */
const hostFace = computed(() => {
  if (result.value) return faceOf(result.value, level.value);
  if (card.value) return HOST.watching;
  return kind.value && table.value && coins.value < table.value.coins ? HOST.closed : HOST.open;
});

const cost = computed(() => table.value?.coins ?? 0);
const short = computed(() => coins.value < cost.value);
/** The open card's prize did not get through: the key collects it again before anything else. */
const unpaid = computed(() => !!card.value && open.value && !prize.value && !paying.value);
const settled = computed(() => !card.value || (open.value && !!prize.value));
const canBuy = computed(() => online.value && !!kind.value && !old.value && !short.value && !buying.value && !paying.value && settled.value);
const keyLabel = computed(() => {
  if (unpaid.value) return "再试一次";
  if (old.value) return "返回";
  if (!online.value) return "未连接";
  if (short.value) return "驼币不足";
  return "刮一张";
});

let timers: ReturnType<typeof setTimeout>[] = [];
const later = (ms: number, fn: () => void) => timers.push(setTimeout(fn, ms));

// ---- the coating: a canvas over the cells, erased along the pointer
const canvas = ref<HTMLCanvasElement>();
/** The coating printed on the empty ticket before a card is bought: drawn the same way, never scratched. */
const idleCanvas = ref<HTMLCanvasElement>();
let coating = new Coating();
let last: { x: number; y: number } | null = null;

/** The A-SOUL mark printed in the middle of the coating; drawn once it has loaded. */
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

/** Sizes `el` to its box and fills it with the coating: wine foil, halftone dots and the A-SOUL mark. False while the page has no size. */
function drawCoat(el: HTMLCanvasElement): boolean {
  const w = el.clientWidth;
  const h = el.clientHeight;
  const ctx = w && h ? el.getContext("2d") : null;
  if (!ctx) return false;
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  el.width = Math.round(w * dpr);
  el.height = Math.round(h * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const css = getComputedStyle(el);
  const fill = ctx.createLinearGradient(0, 0, w, h);
  fill.addColorStop(0, css.getPropertyValue("--c-700").trim() || "#C34637");
  fill.addColorStop(1, css.getPropertyValue("--c-800").trim() || "#A12F35");
  ctx.fillStyle = fill;
  ctx.fillRect(0, 0, w, h);
  // Halftone dots growing toward the bottom right, as on the page-turn bands.
  ctx.fillStyle = "rgba(255, 255, 255, 0.2)";
  const step = 12;
  for (let row = 0, y = step / 2; y < h; y += step, row++) {
    for (let x = step / 2 + (row % 2) * (step / 2); x < w; x += step) {
      ctx.beginPath();
      ctx.arc(x, y, 0.8 + 2.6 * ((x / w + y / h) / 2), 0, Math.PI * 2);
      ctx.fill();
    }
  }
  if (mark.complete && mark.naturalWidth) {
    // The mark is black in its file: tint it white on a scratch layer first.
    const mw = Math.round(w * 0.5);
    const mh = Math.round(mw / MARK_RATIO);
    const tint = document.createElement("canvas");
    tint.width = Math.round(mw * dpr);
    tint.height = Math.round(mh * dpr);
    const t = tint.getContext("2d");
    if (t) {
      t.drawImage(mark, 0, 0, tint.width, tint.height);
      t.globalCompositeOperation = "source-in";
      t.fillStyle = "#fff";
      t.fillRect(0, 0, tint.width, tint.height);
      ctx.globalAlpha = 0.92;
      ctx.drawImage(tint, (w - mw) / 2, (h - mh) / 2, mw, mh);
      ctx.globalAlpha = 1;
    }
  }
  return true;
}

function paintIdle() {
  if (idleCanvas.value && !card.value) drawCoat(idleCanvas.value);
}
watch(idleCanvas, () => void nextTick(paintIdle), { flush: "post" });

/** Draws a fresh coating for the card on the table. Does nothing while the page has no size (it is turned away). */
function paint() {
  const el = canvas.value;
  const current = card.value;
  if (!el || !current || open.value || coated.value === current.id) return;
  if (!drawCoat(el)) return;
  coating = new Coating();
  last = null;
  untouched.value = true;
  coated.value = current.id;
}
watch(canvas, () => void nextTick(paint), { flush: "post" });

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

// ---- the round: pick a card, buy, scratch, collect
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

/** Opens a card's table. A card still to reveal comes first, whichever it is. */
function pick(next: CardKind) {
  error.value = "";
  kind.value = next;
  void nextTick(paintIdle);
}
function back() {
  if (!settled.value) return;
  kind.value = null;
  card.value = null;
  old.value = false;
  open.value = false;
  prize.value = null;
  error.value = "";
  const next = waiting;
  waiting = null;
  if (next) put(next);
  else offerOld();
}

/** An old card still to reveal takes the table when nothing else is on it. */
function offerOld() {
  const pending = scratchCard.value;
  if (pending && !doneOld.has(pending.id) && !card.value && !kind.value) put({ id: pending.id, kind: "basic", cells: pending.cells }, true);
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
  if (!canBuy.value || !kind.value) return;
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
  else if (old.value) back();
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
  kind.value = null;
  old.value = false;
  waiting = null;
  prize.value = null;
  whole.value = null;
  if (active && player) {
    void load();
    void loadScratch();
  }
});
</script>

<template>
  <section class="stall" :class="{ calm }" aria-label="刮刮乐">
    <header class="head" data-rise>
      <button v-if="kind" type="button" class="ui-btn ghost small back" aria-label="返回" title="返回" :disabled="!settled" @click="back">
        <Icon name="back" :size="18" />
      </button>
      <div class="title">
        <span class="eyebrow" aria-hidden="true">SCRATCH</span>
        <h2 class="name">{{ kind && !old ? `${NAMES[kind]}刮刮乐` : "刮刮乐" }}</h2>
      </div>
      <button type="button" class="ui-btn ghost small rates-btn" title="概率" aria-label="概率" @click="odds = true">
        <Icon name="info" :size="18" />
      </button>
      <Transition name="host" mode="out-in" :css="!calm">
        <img :key="hostFace" class="host" :src="ACHAO[hostFace]" alt="" draggable="false" />
      </Transition>
    </header>

    <div class="sheet" :class="{ solo: kind !== 'basic' }">
      <p v-if="error" class="ui-error sheet-error" role="alert">{{ error }}</p>

      <!-- The two cards, side by side: the price on the stub, the best prize across the middle. -->
      <div v-if="!kind" class="picker" data-rise>
        <button v-for="k in KINDS" :key="k" type="button" class="pick" :class="k" @click="pick(k)">
          <span class="pick-stub" aria-hidden="true"><i class="stub-mark"></i></span>
          <b class="pick-name">{{ NAMES[k] }}</b>
          <span class="pick-top"><Icon name="shard" :size="16" />{{ fmt(topPrize(k)) }}</span>
          <span class="pick-cost"><img :src="COIN_SMALL" alt="" draggable="false" />×{{ SCRATCH.cards[k].coins }}</span>
        </button>
      </div>

      <template v-else>
        <div class="table" data-rise>
          <div
            class="ticket" :class="[kind, level !== 0 ? `lv-${level}` : '', { on: !!card, deal: dealing, open }]"
          >
            <i v-if="level === 2 || level === 3" :key="`burst-${card?.id}`" class="burst" :class="`burst-${level}`" aria-hidden="true"></i>
            <!-- The stub printed across the top: the mark, the price and the card's number. -->
            <p class="stub" aria-hidden="true">
              <i class="stub-mark"></i>
              <span v-if="!old" class="price"><img :src="COIN_SMALL" alt="" draggable="false" />×{{ cost }}</span>
              <span v-if="card" class="serial">No.{{ String(card.id).padStart(6, "0") }}</span>
            </p>
            <i class="notch left" aria-hidden="true"></i>
            <i class="notch right" aria-hidden="true"></i>
            <div class="field">
              <ol class="cells" :class="{ veiled: !card || (!open && coated !== card.id) }">
                <li v-for="(c, i) in cells" :key="i" :class="{ win: winAt.has(i), lose: !!result && !winAt.has(i) }">
                  <template v-if="c">
                    <span v-if="c.kind === 'shards'" class="amount" :class="{ long: c.amount >= 10000, longer: c.amount >= 100000 }">
                      <Icon name="shard" :size="c.amount >= 10000 ? 13 : 16" />{{ c.amount }}
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
                v-show="card" ref="canvas" class="coat" :class="{ gone: open }" aria-hidden="true"
                @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up" @lostpointercapture="up"
              ></canvas>
              <canvas v-if="!card" ref="idleCanvas" class="coat idle" aria-hidden="true"></canvas>
              <i v-if="card && !open && untouched && !calm" class="sheen" aria-hidden="true"></i>
            </div>
            <b
              v-if="result" :key="card?.id" class="ui-tag result" :class="[TAGS[String(level)], { word: !resultAmount, still: level === 0 || level === 'plain' }]"
              role="status"
            >
              <Icon v-if="resultAmount" name="shard" :size="16" />{{ resultText }}
            </b>
          </div>

          <div class="keys">
            <button v-if="card && !open" type="button" class="ui-btn large peel" @click="finish">全部刮开</button>
            <button
              v-else type="button" class="ui-btn primary buy" :class="{ pulse: canBuy && !card }"
              :disabled="!canBuy && !unpaid && !(old && settled)" :aria-busy="buying || paying" @click="press"
            >
              <span class="buy-label">{{ keyLabel }}</span>
              <small v-if="!unpaid && !old" class="buy-cost"><img :src="COIN_SMALL" alt="" draggable="false" />×{{ cost }}</small>
            </button>
          </div>
        </div>

        <aside v-if="kind === 'basic'" class="album" data-rise>
          <h4 class="ui-label"><span>阿草表情</span><small>{{ ownedKeys.size }} / {{ SCRATCH_EMOTES.length }}</small></h4>
          <ol class="stickers">
            <li
              v-for="(e, i) in SCRATCH_EMOTES" :key="e.key"
              :class="{ has: ownedKeys.has(e.key), fresh: fresh === e.key }" :title="ownedKeys.has(e.key) ? e.name : undefined"
              :style="{ '--lean': leanOf(i) }"
            >
              <img :src="emoteSrc(e.key)" :alt="ownedKeys.has(e.key) ? e.name : ''" loading="lazy" decoding="async" draggable="false" />
            </li>
          </ol>
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
        </aside>
      </template>
    </div>

    <PlateDetail v-if="plateView && albumPlate" :plate="albumPlate" @close="plateView = false" />
    <Modal v-if="odds" title="刮刮乐概率" heading @close="odds = false">
      <div class="odds">
        <table v-for="k in kind ? [kind] : KINDS" :key="k" class="rates">
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
  </section>
</template>

<style scoped>
/* The stall: a coral head over one sheet of paper, the same build as the park's top block. */
.stall {
  flex: none;
  display: flex;
  flex-direction: column;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: var(--shadow-paper);
}

/* ---- the head: the name, the odds, and 阿草 behind the sheet with its face over the top */
.head {
  --host-h: 144px;
  --host-room: 176px;
  position: relative;
  display: flex;
  align-items: flex-end;
  gap: 14px;
  min-height: 92px;
  padding: 14px 22px 14px;
  box-sizing: border-box;
  border-radius: var(--radius-l) var(--radius-l) 0 0;
  background: var(--grad-sky);
}
/* Printed into the coral, faint and behind the type: halftone dots that grow toward the sheet. */
.head::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: #fff;
  pointer-events: none;
  opacity: 0.32;
  mask:
    url("../../assets/patterns/halftone.svg") 0 -28px / 280px 140px repeat-x,
    linear-gradient(90deg, transparent 34%, #000 72%);
  mask-composite: intersect;
}
.title,
.back,
.rates-btn,
.host {
  position: relative;
  z-index: 1;
}
.title {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.eyebrow {
  font: 800 12px/1 var(--font-latin);
  letter-spacing: 0.26em;
  color: var(--ink);
  opacity: 0.72;
}
.name {
  margin: 0;
  font: 800 38px/1 var(--font);
  letter-spacing: 0.06em;
  color: #fff;
  white-space: nowrap;
}
.back,
.rates-btn {
  width: 36px;
  padding: 0;
  color: var(--ink);
}
.back {
  align-self: center;
}
.rates-btn {
  margin: 0 var(--host-room) 2px auto;
}
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
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(200px, 37%);
  gap: 24px;
  padding: 24px 22px 20px;
  border-radius: 0 0 var(--radius-l) var(--radius-l);
  background: var(--surface);
}
.sheet.solo {
  grid-template-columns: minmax(0, 1fr);
}
.sheet-error {
  grid-column: 1 / -1;
  margin: 0;
}

/* ---- the picker: two cards to keep, not keys: they lift off the paper under the pointer */
.picker {
  grid-column: 1 / -1;
  display: flex;
  justify-content: center;
  gap: 24px;
  padding: 6px 0 4px;
}
.pick {
  position: relative;
  flex: 0 1 220px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 0 14px 18px;
  border: 0;
  border-radius: var(--radius-l);
  background: var(--grad-sky);
  box-shadow: var(--shadow-paper);
  color: #fff;
  cursor: pointer;
  transition: transform var(--dur-base) var(--ease-out), box-shadow var(--dur-base) var(--ease-out);
}
.pick::before {
  content: "";
  position: absolute;
  inset: 6px;
  border-radius: var(--radius-m);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.6);
  pointer-events: none;
}
/* The premium card wears the gold of the coin and the big hidden cards. */
.pick.premium::before,
.ticket.premium::before {
  box-shadow: inset 0 0 0 3px var(--gold-soft), inset 0 0 0 4px rgba(var(--gold-rgb), 0.6);
}
.pick:hover {
  transform: translateY(-3px) rotate(-1deg);
  box-shadow: var(--shadow-key), var(--shadow-backlight);
}
.pick:focus-visible {
  outline: 2px solid var(--c-700);
  outline-offset: 3px;
}
.pick-stub {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 40px;
  border-bottom: 3px dotted rgba(255, 255, 255, 0.85);
}
.pick-name {
  margin-top: 6px;
  font: 800 34px/1 var(--font);
  letter-spacing: 0.08em;
}
.pick-top {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font: 800 26px/1 var(--font-latin);
  color: var(--ink);
}
.pick-top svg {
  color: #fff;
}
.pick-cost,
.price,
.buy-cost {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: var(--ink);
}
.pick-cost img,
.price img,
.buy-cost img {
  width: 18px;
  height: 18px;
  filter: drop-shadow(0 1px 1px rgba(var(--c-900-rgb), 0.25));
}

/* ---- the table: the card, and under it the one key that buys the next */
.table {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 18px;
  min-width: 0;
}
/*
 * A card is a thing to keep, not a key: no lip. Before one is bought the ticket lies flat on the paper under its
 * coating, with nothing to press; the card being scratched lifts off the page in the coral backlight.
 */
.ticket {
  --pad: 14px;
  --stub-h: 40px;
  --burst: rgba(var(--c-500-rgb), 0.7);
  position: relative;
  width: min(100%, clamp(240px, calc(50cqh - 20px), 360px));
  border-radius: var(--radius-l);
  background: var(--grad-sky);
  box-shadow: var(--shadow-paper);
}
.ticket.on {
  box-shadow: var(--shadow-key), var(--shadow-backlight);
}
/* The inner rule of the card backs the resonance deals. */
.ticket::before {
  content: "";
  position: absolute;
  inset: 6px;
  border-radius: var(--radius-m);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.6);
  pointer-events: none;
}
/* Printed on the stub: the A-SOUL mark, the price and the card's number; a row of perforations under it. */
.stub {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  height: var(--stub-h);
  margin: 0;
  padding: 2px calc(var(--pad) + 6px) 0;
  box-sizing: border-box;
  color: var(--ink);
}
.stub::after {
  content: "";
  position: absolute;
  left: calc(var(--pad) + 4px);
  right: calc(var(--pad) + 4px);
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
.serial {
  margin-left: auto;
  font: 800 var(--fs-label)/1 var(--font-latin);
  letter-spacing: 0.12em;
  opacity: 0.72;
}
/* The two half-round bites of a ticket, level with the perforations: the paper shows through. */
.notch {
  position: absolute;
  top: calc(var(--stub-h) - 17px);
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--surface);
  box-shadow: inset 0 1px 2px rgba(var(--shadow-rgb), 0.1);
}
.notch.left {
  left: -11px;
}
.notch.right {
  right: -11px;
}
/* The nine cells, and over them the coating. */
.field {
  position: relative;
  aspect-ratio: 1;
  container-type: inline-size;
  margin: 0 var(--pad) var(--pad);
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
  gap: 8px;
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
.amount {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  /* Scales with the card, so a long amount stays inside its cell on a small panel. */
  font: 800 min(27px, 8.6cqw)/1 var(--font-latin);
  color: var(--ink);
}
.amount.long {
  font-size: min(21px, 6.6cqw);
}
.amount.longer {
  font-size: min(18px, 5.6cqw);
}
.amount svg {
  color: var(--c-600);
}
/* The named symbols: a mark and a word under it. */
.sym {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  color: var(--c-700);
}
.sym small {
  font: 800 min(var(--fs-label), 4.4cqw)/1 var(--font);
  color: var(--ink-2);
}
.sym.again img {
  width: min(34px, 10cqw);
  height: min(34px, 10cqw);
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
/* 16 times and up: a ring of light goes out from the card once. 100 times, the jackpot and a skin or big card: gold
 * rays turn behind it for a while. */
.burst {
  position: absolute;
  z-index: -1;
  left: 50%;
  top: 50%;
  width: 150%;
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
  width: 190%;
  background:
    radial-gradient(circle, rgba(var(--gold-rgb), 0.5), transparent 58%),
    repeating-conic-gradient(rgba(var(--gold-rgb), 0.55) 0deg 9deg, transparent 9deg 24deg);
  mask: radial-gradient(circle, #000 30%, transparent 68%);
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
.lv-3.ticket {
  animation: lift 700ms var(--ease-spring) both;
}
@keyframes lift {
  40% { transform: translateY(-8px) scale(1.03); }
}

/* The coating: wine foil over the cells, scratched off along the pointer. */
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
/* The empty ticket's coating is only printed: nothing to scratch until a card is bought. */
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
/* What the card paid, stuck on its corner like a price tag. */
.result {
  position: absolute;
  z-index: 2;
  right: -12px;
  top: -14px;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 0 12px;
  rotate: 5deg;
  font: 800 22px/34px var(--font-latin);
  box-shadow: var(--shadow-key);
  animation: tag-in 420ms var(--ease-pop) 120ms both;
}
/* Words, not an amount: set in the text face. */
.result.word {
  font: 800 var(--fs-number)/32px var(--font);
}
/* A miss and the coins back: the tag is just there. */
.result.still {
  animation: none;
}
@keyframes tag-in {
  from { opacity: 0; scale: 0.5; }
}

.keys {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-bottom: 3px;
}
.buy {
  flex-direction: column;
  gap: 3px;
  height: 58px;
  min-width: 196px;
  padding: 0 28px;
  font-size: 18px;
}
.peel {
  height: 58px;
  min-width: 196px;
}
.buy-cost {
  font-size: var(--fs-label);
  letter-spacing: 0.04em;
  color: inherit;
  opacity: 0.85;
}
.buy-cost img {
  width: 14px;
  height: 14px;
}

/* ---- the album: 阿草's twenty stickers, a slot each */
.album {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.stickers {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
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
.pity {
  margin-top: auto;
  padding-top: 14px;
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
  margin-top: auto;
  padding-top: 14px;
  font-size: var(--fs-strong);
  color: var(--c-700);
}
/* 阿草's plate under the album: grey until the set is whole. */
.album-plate {
  display: flex;
  justify-content: center;
  margin-top: 12px;
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

.calm .stickers img,
.calm .pick {
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

@container panel (max-width: 760px) {
  .head {
    --host-h: 118px;
    --host-room: 132px;
    gap: 10px;
    padding-inline: 18px;
  }
  .name {
    font-size: 32px;
  }
  .sheet {
    grid-template-columns: minmax(0, 1fr) minmax(168px, 34%);
    gap: 16px;
    padding-inline: 16px;
  }
  .picker {
    gap: 16px;
  }
  .buy,
  .peel {
    min-width: 150px;
    padding: 0 18px;
  }
}
@container panel (max-height: 600px) {
  .head {
    --host-h: 120px;
    min-height: 78px;
  }
  .name {
    font-size: 32px;
  }
  .sheet {
    padding-block: 18px 14px;
  }
  .table {
    gap: 12px;
  }
  .buy,
  .peel {
    height: 50px;
  }
  .stickers {
    gap: 6px;
  }
}
</style>
