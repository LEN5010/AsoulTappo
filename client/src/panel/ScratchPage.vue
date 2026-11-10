<script setup lang="ts">
// Scratch cards: 阿草 keeps a stall under a coral head, as on the check-in calendar. A card is nine cells under a
// coating; dragging over it scratches the coating off, and three cells alike are the prize. The server decides
// the prize when the card is bought and pays it when the card is revealed (../scratch.ts, stores/player.ts), so
// the balance in the top bar gives nothing away while the coating is on.
import { computed, nextTick, onActivated, onDeactivated, onMounted, ref, watch } from "vue";
import * as sfx from "../audio/sfx";
import { assetUrl } from "../asset";
import { characterColor, emoteCover, manifest } from "../manifest";
import type { ScratchCard } from "../net/api";
import { buyScratch, collection, error, loadScratch, online, revealScratch, scratchCard, shards, status } from "../stores/player";
import { sendEmote } from "../stores/room";
import { settings } from "../stores/settings";
import { reducedMotion } from "../stores/theme";
import { ACHAO } from "../ui/achao";
import NamePlate from "../pet/NamePlate.vue";
import { allPlates, nameBand, plateSize, plateUnlocked } from "../pet/plates";
import PlateDetail from "./PlateDetail.vue";
import Icon from "../ui/Icon.vue";
import Modal from "../ui/Modal.vue";
import asoulLogo from "../assets/brand/asoul-logo.svg";
import { Coating, HOST, SCRATCH_EMOTES, cellOf, faceOf, oddsRows, outcomeOf, ownedScratchEmotes, toneOf } from "../scratch";

const CFG = manifest.economy.scratch;
/** The rest of the coating lifts by itself once this much of it is gone. */
const DONE_SHARE = 0.55;
/** Brush radius as a share of the card's width. */
const BRUSH = 0.075;
/** Long enough for the card to land. */
const DEAL_MS = 460;
/** Result tags in the tone of the prize: gold, wine, coral; a miss is plain. */
const TAGS: Record<string, string> = { "tone-legendary": "gold", "tone-epic": "dark", "tone-rare": "", "": "light" };
/** Stickers in the album lean a little, each its own way. */
const leanOf = (n: number) => `${((n * 7) % 5) * 2 - 4}deg`;
const emoteSrc = (key: string) => assetUrl(emoteCover(key));

const calm = computed(() => reducedMotion.value);
const left = computed(() => status.value?.scratch?.left ?? 0);
const pity = computed(() => status.value?.scratch?.pity ?? 0);
const closedServer = computed(() => !!status.value && !status.value.scratch);
const ownedKeys = computed(() => new Set(ownedScratchEmotes(collection.owned)));
const complete = computed(() => ownedKeys.value.size >= SCRATCH_EMOTES.length);
const pityPercent = computed(() => Math.min(100, (pity.value / CFG.emote.pity) * 100));

/** The plate the whole set unlocks, under the album as a partner at x0.7 would see it, standing still. */
const albumPlate = allPlates().find((p) => p.kind === "sweep" && p.set === CFG.emote.set) ?? null;
const PLATE_SCALE = 0.7;
const plateBox = plateSize(PLATE_SCALE);
const plateFont = nameBand(PLATE_SCALE).font;
const plateOpen = computed(() => !!albumPlate && plateUnlocked(albumPlate.id, collection.owned));
const plateNick = computed(() => settings.nick.trim() || "匿名小面包");
const plateView = ref(false);

/** The card on the table: under its coating, then open. */
const card = ref<ScratchCard | null>(null);
const open = ref(false);
/** The open card's prize has reached the save. */
const paid = ref(false);
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

const outcome = computed(() => (card.value ? outcomeOf(card.value.cells) : null));
const cells = computed(() => card.value?.cells.map(cellOf) ?? Array.from({ length: 9 }, () => null));
const result = computed(() => (open.value ? outcome.value : null));
const winAt = computed(() => new Set(result.value && result.value.kind !== "miss" ? result.value.at : []));
const tone = computed(() => (result.value ? toneOf(result.value) : ""));
const resultText = computed(() => {
  const r = result.value;
  if (!r) return "";
  return r.kind === "miss" ? "没中" : r.kind === "shards" ? `+${r.amount}` : "新表情";
});
/** 阿草 touts while the stall is open, watches a card being scratched, and takes each result personally. */
const hostFace = computed(() => {
  if (result.value) return faceOf(result.value);
  if (card.value) return HOST.watching;
  return status.value?.scratch && left.value === 0 ? HOST.closed : HOST.open;
});

const short = computed(() => Math.max(0, CFG.price - shards.value));
/** The open card's prize did not get through: the key collects it again before anything else. */
const unpaid = computed(() => !!card.value && open.value && !paid.value && !paying.value);
const canBuy = computed(() => online.value && !!status.value?.scratch && left.value > 0 && short.value === 0
  && !buying.value && !paying.value && (!card.value || (open.value && paid.value)));
const keyLabel = computed(() => {
  if (unpaid.value) return "再试一次";
  if (!online.value) return "未连接";
  if (closedServer.value) return "未开放";
  if (left.value === 0) return "今日售罄";
  if (short.value > 0) return `还差 ${short.value} 碎片`;
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

// ---- the round: buy, scratch, collect
/** A card comes onto the table: the one just bought, or one left unrevealed by an earlier visit. */
function put(next: ScratchCard) {
  card.value = next;
  open.value = false;
  paid.value = false;
  fresh.value = "";
  sfx.flip(true);
  if (!calm.value) {
    dealing.value = true;
    later(DEAL_MS, () => (dealing.value = false));
  }
  void nextTick(paint);
}
watch(scratchCard, (pending) => {
  if (pending && pending.id !== card.value?.id) put(pending);
}, { immediate: true });
// Another save: its table starts empty.
watch(() => status.value?.player, (player, was) => {
  if (was && player !== was && card.value?.id !== scratchCard.value?.id) card.value = null;
});

async function buy() {
  if (!canBuy.value) return;
  error.value = "";
  buying.value = true;
  try {
    await buyScratch();
  } catch (e) {
    // The desk window did not answer in time.
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    buying.value = false;
  }
}

/** The coating is off: the card shows what it pays and the prize is collected. */
function finish() {
  if (!card.value || open.value) return;
  open.value = true;
  last = null;
  sfx.flip();
  if (outcome.value && toneOf(outcome.value) === "tone-legendary") sfx.pageTurn();
  void collect();
}

async function collect() {
  const current = card.value;
  if (!current || paying.value || paid.value) return;
  error.value = "";
  paying.value = true;
  let prize: Awaited<ReturnType<typeof revealScratch>> = null;
  try {
    prize = await revealScratch(current.id);
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e);
  } finally {
    paying.value = false;
  }
  if (!prize || card.value?.id !== current.id) return;
  paid.value = true;
  if (prize.item?.startsWith("emote:")) {
    fresh.value = prize.item.slice(6);
    // The pet shows the new sticker off, to the room as well.
    sendEmote(fresh.value);
  }
}

function press() {
  if (unpaid.value) void collect();
  else void buy();
}

onMounted(sfx.prime);
let active = false;
onActivated(() => {
  active = true;
  void loadScratch();
  void nextTick(() => {
    paint();
    paintIdle();
  });
});
onDeactivated(() => {
  active = false;
  timers.forEach(clearTimeout);
  timers = [];
  dealing.value = false;
  last = null;
});
// A new day, another save, or a server that has just gained scratch cards: ask again whether a card is waiting.
watch(() => [status.value?.player, status.value?.scratch?.left] as const, ([player, now], [was, before]) => {
  if (active && player && now !== undefined && (player !== was || before === undefined || now > before)) void loadScratch();
});
</script>

<template>
  <div class="scratch-page ui-scroll" :class="{ calm }">
    <p v-if="error" class="ui-error" role="alert">{{ error }}</p>
    <p v-else-if="closedServer" class="ui-error" role="status">当前服务器未开放刮刮乐</p>

    <section class="stall" aria-label="刮刮乐">
      <header class="head" data-rise>
        <div class="title">
          <span class="eyebrow" aria-hidden="true">SCRATCH</span>
          <h2 class="name">刮刮乐</h2>
        </div>
        <p class="tally">
          <span>今日剩余<b>{{ left }}</b>张</span>
        </p>
        <Transition name="host" mode="out-in" :css="!calm">
          <img :key="hostFace" class="host" :src="ACHAO[hostFace]" alt="" draggable="false" />
        </Transition>
      </header>

      <div class="sheet">
        <div class="table" data-rise>
          <div class="ticket" :class="[tone, { on: !!card, deal: dealing, open, soldout: !card && !!status?.scratch && left === 0 }]">
            <!-- The stub printed across the top: the mark, the card's number and its price. -->
            <p class="stub" aria-hidden="true">
              <i class="stub-mark"></i>
              <span class="price"><Icon name="shard" :size="13" />{{ CFG.price }}</span>
              <span v-if="card" class="serial">No.{{ String(card.id).padStart(6, "0") }}</span>
            </p>
            <i class="notch left" aria-hidden="true"></i>
            <i class="notch right" aria-hidden="true"></i>
            <div class="field">
              <ol class="cells" :class="{ veiled: !card || (!open && coated !== card.id) }">
                <li v-for="(c, i) in cells" :key="i" :class="{ win: winAt.has(i), lose: !!result && !winAt.has(i) }">
                  <template v-if="c">
                    <span v-if="c.kind === 'shards'" class="amount" :class="{ long: c.amount >= 10000 }">
                      <Icon name="shard" :size="c.amount >= 10000 ? 13 : 16" />{{ c.amount }}
                    </span>
                    <img v-else :src="emoteSrc(c.key)" alt="" draggable="false" />
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
            <b v-if="result" :key="card?.id" class="ui-tag result" :class="[TAGS[tone], { word: result.kind !== 'shards' }]" role="status">
              <Icon v-if="result.kind === 'shards'" name="shard" :size="16" />{{ resultText }}
            </b>
          </div>

          <div class="keys">
            <button v-if="card && !open" type="button" class="ui-btn large peel" @click="finish">全部刮开</button>
            <button
              v-else type="button" class="ui-btn primary buy" :class="{ pulse: canBuy }"
              :disabled="!canBuy && !unpaid" :aria-busy="buying || paying" @click="press"
            >
              <span class="buy-label">{{ keyLabel }}</span>
              <small v-if="!unpaid" class="buy-cost"><Icon name="shard" :size="11" />{{ CFG.price }}</small>
            </button>
            <button type="button" class="ui-btn ghost rates-btn" title="概率" aria-label="概率" @click="odds = true">
              <Icon name="info" :size="18" />
            </button>
          </div>
        </div>

        <aside class="album" data-rise>
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
            <span>保底<b>{{ pity }}</b><i>/ {{ CFG.emote.pity }}</i></span>
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
      </div>
    </section>

    <PlateDetail v-if="plateView && albumPlate" :plate="albumPlate" @close="plateView = false" />
    <Modal v-if="odds" title="刮刮乐概率" heading @close="odds = false">
      <table class="rates"><thead><tr><th>奖品</th><th>概率</th><th v-if="!complete">保底</th></tr></thead><tbody>
        <tr v-for="(row, n) in oddsRows(complete)" :key="n">
          <td>
            <span v-if="row.kind === 'shards'" class="prize"><Icon name="shard" :size="14" />{{ row.shards }}</span>
            <template v-else>{{ row.kind === "emote" ? "阿草表情" : "没中" }}</template>
          </td>
          <td>{{ row.rate }}%</td>
          <td v-if="!complete">{{ row.pity ? `${row.pity} 张` : "—" }}</td>
        </tr>
      </tbody></table>
    </Modal>
  </div>
</template>

<style scoped>
.scratch-page {
  height: 100%;
  box-sizing: border-box;
  overflow-y: auto;
  padding: 24px 20px 20px 16px;
  display: flex;
  flex-direction: column;
}

/* The stall: a coral head over one sheet of paper, the same build as the check-in calendar. */
.stall {
  flex: 1 0 auto;
  display: flex;
  flex-direction: column;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: var(--shadow-paper);
}

/* ---- the head: the name, what is left today, and 阿草 behind the sheet with its face over the top */
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
    url("../assets/patterns/halftone.svg") 0 -28px / 280px 140px repeat-x,
    linear-gradient(90deg, transparent 34%, #000 72%);
  mask-composite: intersect;
}
.title,
.tally,
.host {
  z-index: 1;
}
.title,
.tally {
  position: relative;
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
.tally b {
  font: 800 28px/1 var(--font-latin);
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
  flex: 1;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(200px, 37%);
  gap: 24px;
  padding: 20px 22px 20px;
  border-radius: 0 0 var(--radius-l) var(--radius-l);
  background: var(--surface);
}

/* ---- the table: the card, and under it the one key that buys the next */
.table {
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
  --burst: var(--tone-glow, rgba(var(--c-500-rgb), 0.7));
  position: relative;
  width: min(100%, clamp(240px, calc(50cqh - 20px), 360px));
  border-radius: var(--radius-l);
  background: var(--grad-sky);
  box-shadow: var(--shadow-paper);
}
.ticket.on {
  box-shadow: var(--shadow-key), var(--shadow-backlight);
}
/* Sold out for today: the empty ticket goes grey, opaque, so it no longer looks ready to scratch. */
.ticket.soldout {
  filter: grayscale(1);
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
/* Printed on the stub: the A-SOUL mark, the card's number and its price; a row of perforations under it. */
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
  mask: url("../assets/brand/asoul-logo.svg") center / contain no-repeat;
  -webkit-mask: url("../assets/brand/asoul-logo.svg") center / contain no-repeat;
}
.serial {
  margin-left: auto;
  font: 800 var(--fs-label)/1 var(--font-latin);
  letter-spacing: 0.12em;
  opacity: 0.72;
}
.price {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font: 800 var(--fs-number)/1 var(--font-latin);
}
.price svg {
  color: #fff;
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
.amount svg {
  color: var(--c-600);
}
/* The three alike: framed in the prize's tone, the other six step back. */
.cells .win {
  z-index: 1;
  box-shadow: 0 0 0 3px var(--c-700), 0 0 14px 1px var(--burst);
  animation: cell-pop 520ms var(--ease-spring) both;
}
.tone-epic .cells .win {
  box-shadow: 0 0 0 3px var(--c-800), 0 0 14px 1px var(--burst);
}
.tone-legendary .cells .win {
  box-shadow: 0 0 0 3px var(--gold), 0 0 18px 2px var(--burst);
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
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font: 800 var(--fs-label)/1 var(--font-latin);
  letter-spacing: 0.04em;
  opacity: 0.75;
}
.rates-btn {
  width: 36px;
  padding: 0;
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

.calm .stickers img {
  transition: none;
}
.calm .ticket.deal,
.calm .cells .win,
.calm .result,
.calm .stickers .fresh img {
  animation: none;
}

@container panel (max-width: 760px) {
  .head {
    --host-h: 118px;
    --host-room: 132px;
    gap: 14px;
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
  .buy,
  .peel {
    min-width: 150px;
    padding: 0 18px;
  }
}
@container panel (max-height: 600px) {
  .scratch-page {
    padding-top: 18px;
  }
  .head {
    --host-h: 120px;
    min-height: 78px;
  }
  .name {
    font-size: 32px;
  }
  .sheet {
    padding-block: 14px;
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
