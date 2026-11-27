<script setup lang="ts">
// The stage of a limited pool, laid out as the standing pool's (PoolStage.vue): a hero on the left, the pool's name
// and a sheet of paper on the right, with what is left of the pool's time beside the item on show. Where the pool
// raises the limited tier's odds the hero is the standing pool's hand (CardHand.vue) dealing the limited cards, with
// the featured item on show standing at its foot; else it is a pearl card with the featured items piled on it as
// stickers. A pool featuring a skin with an official poster (characters.ts) has no card and no sheet: the poster spreads
// over the left of the panel, from its top edge down under the action bar, and the right is a scrapbook of the skin's
// member (her cards as photos, her emotes as stickers) with the item on show large in front of it and one line of the
// pool under them; the scrapbook fills as the pool comes on screen. Where the poster's title lettering reads the pool's
// name, that title lies on the poster's lower left in place of the name. Where the skin also has a clip of its PV, the
// clip plays there first each time the pool comes on screen, and the poster and its title come in as it ends. A featured
// skin sits at its desk as on the desktop; a two-form skin types for a moment and changes into its second form, as it
// does for the player. The
// sheet lists what the pool holds: its featured items as standees (the one on show times its own turn), then the 衣橱
// series as a row (CollectionRows.vue); under the sheet the 衣橱 cards pass by. A pool with more featured items than a
// row of standees takes keeps a lineup under the hero.
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from "vue";
import { usePageActive } from "../composables/usePageActive";
import { assetUrl } from "../asset";
import { formReach, getCharacter, headAnchor, PET_BASE, skinSeries } from "../characters";
import { cardLabel } from "../cards";
import { characterColor, emoteCover, getCard, manifest, memberOf, RARITY_ORDER } from "../manifest";
import { collectible, RARITY_LABEL, type Item } from "../items";
import type { Rarity } from "../manifest";
import { bannerBaseRates, featuredItems } from "../resonance";
import { collection } from "../stores/player";
import type { Banner } from "../stores/economy";
import { reducedMotion } from "../stores/theme";
import { arrowSelect } from "../ui/focus";
import Icon from "../ui/Icon.vue";
import PetView from "../pet/PetView.vue";
import PetBust from "./PetBust.vue";
import CardHand from "./CardHand.vue";
import CollectionRows from "./CollectionRows.vue";
import type { Plate } from "../pet/plates";

const props = defineProps<{
  banner: Banner;
  busy: boolean;
  paused?: boolean;
  /** What is left of the pool's time, as the pool keys had it. */
  left?: string;
}>();
const emit = defineEmits<{ inspect: [item: Item]; plate: [plate: Plate] }>();

/** A skin types this long in its first form, then shows its second for the rest of its turn. */
const TYPE_MS = 1900;
const KEY_MS = 120;
const PILE = 3;
/** A row of standees takes this many featured items; more get a lineup under the hero. */
const STANDS = 5;
const LEAN_DEG = 8;

const items = computed(() => featuredItems(props.banner));
const at = ref(0);
watch(() => props.banner.id, () => (at.value = 0));
const active = computed(() => items.value[at.value % Math.max(1, items.value.length)]);
const owns = (item: Item) => (collection.owned[item.id] ?? 0) > 0;
const got = computed(() => items.value.filter(owns).length);

/** The official poster of the skin on show, where it has one: spread over the left of the stage in place of the wash. */
const posterArt = computed(() => {
  const item = active.value;
  return item?.kind === "character" ? getCharacter(item.ref)?.poster ?? "" : "";
});
/** The clip of the PV of the skin on show, where it has one: it plays where the poster spreads, before the poster. */
const pvArt = computed(() => {
  const item = active.value;
  return item?.kind === "character" ? getCharacter(item.ref)?.pv ?? "" : "";
});
/** The title cut out of a featured skin's poster, where its lettering reads the pool's name: it lies on the spread
 *  poster for the name. Its pale lines are drawn for the poster, so it never stands on the paper. */
const titleArt = computed(() => {
  if (!showcased.value) return "";
  for (const item of items.value) {
    const title = item.kind === "character" ? getCharacter(item.ref)?.posterTitle : undefined;
    if (title?.text === props.banner.name) return title.src;
  }
  return "";
});
const washArt = computed(() => {
  const item = active.value;
  if (!item) return "";
  return item.kind === "character" ? getCharacter(item.ref)?.bgSmall ?? "" : assetUrl(item.art);
});

interface Figure { item: Item; step: number; skin: boolean; twoForm: boolean; art: string }
const figure = (item: Item, step: number): Figure => {
  const skin = item.kind === "character";
  const card = skin ? undefined : getCard(item.ref);
  return { item, step, skin, twoForm: skin && !!getCharacter(item.ref)?.form, art: card ? assetUrl(card.full) : "" };
};
/** The limited tier's cards (the 衣橱 cards), where this pool raises their odds. */
const LIMITED = collectible.filter((item) => item.rarity === "limited" && item.kind === "card");
const raised = computed(() => !!props.banner.rates?.limited && bannerBaseRates(props.banner).limited > 0);
/** A pool featuring a skin with an official poster spreads the poster over the left in place of the pearl card: the
 *  item on show sits on the paper instead, large. */
const showcased = computed(() =>
  !raised.value && items.value.some((item) => item.kind === "character" && !!getCharacter(item.ref)?.poster));
/** A showcased pool of one item: the paper's middle shows it, so no standee repeats it under the count. */
const soleShow = computed(() => showcased.value && items.value.length === 1);

// A showcased pool has a scrapbook on the right in place of the sheet: the cards of the member of the skin with the
// poster as photos, her emotes as stickers between them, around and behind the item on show. They are what she has
// been, not what the pool gives: they cannot be picked.
/** Where the photos and stickers lie, in parts of the scrapbook (x, y of the top left corner, in %) and their turn. */
interface Slot { x: number; y: number; r: number }
/** Two rows of three photos, the lower one behind the item on show; the stickers on their corners and in their gaps. */
const PHOTO_SLOTS: Slot[] = [
  { x: 5, y: 6, r: -7 }, { x: 38, y: 3, r: 4 }, { x: 70, y: 7, r: 8 },
  { x: 14, y: 35, r: 5 }, { x: 46, y: 33, r: -4 }, { x: 74, y: 37, r: -8 },
];
const STICKER_SLOTS: Slot[] = [
  { x: 27, y: 28, r: -12 }, { x: 62, y: 1, r: 9 }, { x: 20, y: 0, r: -8 },
  { x: 63, y: 29, r: 8 }, { x: 29, y: 58, r: -4 }, { x: 85, y: 73, r: 12 },
];
/** The photos and stickers come in this far apart after the PV; then one catches the light every GLINT_S seconds. */
const MEMORY_STEP_MS = 110;
const GLINT_S = 3.2;
const memories = computed(() => {
  const skin = showcased.value ? items.value.find((i) => i.kind === "character" && !!getCharacter(i.ref)?.poster) : undefined;
  if (!skin) return [];
  const member = memberOf(skin.ref);
  // Her own cards first, the rarer first.
  const cards = manifest.cards.filter((c) => c.characters.includes(member))
    .sort((a, b) => a.characters.length - b.characters.length || RARITY_ORDER.indexOf(b.rarity) - RARITY_ORDER.indexOf(a.rarity));
  const photos = cards.slice(0, PHOTO_SLOTS.length).map((c, i) => ({ kind: "photo", src: assetUrl(c.thumb), slot: PHOTO_SLOTS[i]! }));
  const emotes = manifest.emoteSets.filter((s) => s.character === member && !s.source).flatMap((s) => s.emotes);
  const stickers = emotes.slice(0, STICKER_SLOTS.length)
    .map((e, i) => ({ kind: "sticker", src: assetUrl(emoteCover(e.key)), slot: STICKER_SLOTS[i]! }));
  // They come in a photo and a sticker in turn; the stickers lie over the photos.
  const turn = (kind: string, i: number) => (kind === "photo" ? 2 * i : i < photos.length ? 2 * i + 1 : photos.length + i);
  const all = [...photos, ...stickers];
  // Over a round the light goes from one to another out of the order they came in.
  const gcd = (a: number, b: number): number => (b ? gcd(b, a % b) : a);
  const hop = [7, 5, 3].find((k) => gcd(k, all.length) === 1) ?? 1;
  return all.map((m, n) => {
    const at = turn(m.kind, m.kind === "photo" ? n : n - photos.length);
    return {
      ...m,
      style: {
        left: `${m.slot.x}%`, top: `${m.slot.y}%`, "--rot": `${m.slot.r}deg`, "--at": `${at * MEMORY_STEP_MS}ms`,
        "--glint": `${((at * hop) % all.length) * GLINT_S}s`, "--round": `${all.length * GLINT_S}s`,
      },
    };
  });
});
/** The limited cards a member at a time, so neighbours differ: the hand deals them in this order. */
const DEALT = (() => {
  const by = new Map<string, Item[]>();
  for (const item of LIMITED) {
    const member = item.characters[0] ?? "";
    by.set(member, [...(by.get(member) ?? []), item]);
  }
  const rows = [...by.values()];
  const dealt: Item[] = [];
  for (let i = 0; rows.some((row) => row[i]); i++) for (const row of rows) if (row[i]) dealt.push(row[i]!);
  return dealt;
})();
/** The same cards passing under the sheet. */
const strip = computed(() =>
  (raised.value ? DEALT : []).map((item) => ({ item, art: assetUrl(getCard(item.ref)?.thumb ?? item.art) })));
/** Keyboard focus in the strip stops it and lets it scroll, so the focused card is in view. */
const stripKeyed = ref(false);
function onStripKey(e: KeyboardEvent) {
  const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
  const root = e.currentTarget as HTMLElement | null;
  if (!step || !root) return;
  const cards = [...root.querySelectorAll<HTMLButtonElement>(".strip-group:first-child button:not(:disabled)")];
  const cur = cards.indexOf(document.activeElement as HTMLButtonElement);
  if (cur < 0) return;
  e.preventDefault();
  cards[(cur + step + cards.length) % cards.length]?.focus();
}
/** The pile: the item on show and, on the pearl card, the next ones behind it. */
const pile = computed(() => {
  const n = items.value.length;
  const shown = raised.value ? Math.min(1, n) : Math.min(PILE, n);
  return Array.from({ length: shown }, (_, step) => figure(items.value[(at.value + step) % n]!, step));
});
/** What the pool's featured items are called: skins when they all are. */
const featuredWord = computed(() => (items.value.every((i) => i.kind === "character") ? "本期皮肤" : "本期限定"));
/** With too many featured items for a row of standees, a lineup under the hero picks among them. */
const lined = computed(() => items.value.length > STANDS);
const odds = (r: Rarity) => (props.banner.rates?.[r] ? `${RARITY_LABEL[r]} ${props.banner.rates[r]}%` : "");
/** The odds beside the featured items: their own tier's rate here, or the tiers of theirs this pool rates. */
const featuredOdds = computed(() => {
  if (props.banner.rate) return `UP ${props.banner.rate}%`;
  const tiers = [...new Set(items.value.flatMap((i) => i.rarity ?? []))];
  return tiers.map(odds).filter(Boolean).join(" · ");
});
const front = computed(() => pile.value[0]);
const petReach = computed(() => {
  const extra = Math.max(0, ...items.value.map((item) => item.kind === "character" ? formReach(item.ref) : 0));
  return 1 + extra / PET_BASE.width;
});
/** The two pictures of the skin on show, for its form keys. */
const forms = computed(() => {
  const c = front.value?.twoForm ? getCharacter(front.value.item.ref) : undefined;
  return c?.form ? [c.bgSmall, c.form.bgSmall] : null;
});

/** The skin on show peeks over the top of the sheet, in the form the hero shows; a long pool name leaves it no room,
 *  and a showcased pool has it large on the sheet already. */
const PEEK_NAME = 5;
const peek = computed(() => {
  const item = active.value;
  const c = item?.kind === "character" ? getCharacter(item.ref) : undefined;
  if (!c || showcased.value || props.banner.name.length > PEEK_NAME) return null;
  const second = formShown.value && !!c.form;
  return { key: `${item!.id}${second ? "+" : ""}`, src: second ? c.form!.bg : c.bg };
});

const feature = computed(() => {
  const item = active.value;
  if (!item) return null;
  if (item.kind === "character") {
    const member = memberOf(item.ref);
    return { title: item.name, who: member, color: characterColor(member), series: skinSeries(item.ref), kind: "皮肤", owned: owns(item) };
  }
  const card = getCard(item.ref);
  const label = card ? cardLabel(card) : { title: item.name, who: item.characters.join(" ") };
  return { title: label.title, who: label.who, color: characterColor(item.characters[0] ?? ""), series: item.group, kind: "卡牌", owned: owns(item) };
});

const pageActive = usePageActive();
const pointing = ref(false);
watch(() => props.busy, () => (pointing.value = false));
// A detail sheet hands focus back to the card that opened it: that is not the keyboard walking the strip.
watch(() => props.paused, (paused) => { if (!paused) stripKeyed.value = false; }, { flush: "post" });
const playing = computed(() => pageActive.value && !reducedMotion.value && !props.busy && !props.paused);

// The PV plays each time the pool comes on screen, once; the featured items wait for it before taking turns (`.pv`
// stops their ticks). Anything that stops the stage (a draw, a detail sheet, the page or window going away) ends it,
// and so does a clip that fails or has not started after PV_STALL_MS: the poster comes in instead.
const PV_STALL_MS = 4000;
const pvOn = ref(false);
/** Each start mounts a fresh player, so the clip plays from its first frame. */
const pvRun = ref(0);
let pvStall = 0;
function pvEnd() {
  clearTimeout(pvStall);
  pvStall = 0;
  pvOn.value = false;
}
function pvStart() {
  pvEnd();
  if (!showcased.value || !pvArt.value || !playing.value) return;
  pvRun.value += 1;
  pvOn.value = true;
  pvStall = window.setTimeout(pvEnd, PV_STALL_MS);
}
function pvPlaying() {
  clearTimeout(pvStall);
  pvStall = 0;
}
watch(pageActive, (on) => { if (on) pvStart(); }, { immediate: true });
watch(playing, (on) => { if (!on) pvEnd(); });
watch(pvArt, () => { if (pvOn.value) pvEnd(); });

const hold = computed(() => !playing.value || pointing.value);
// The strip stops where nobody sees it pass: under a detail sheet, the odds or a reveal, and on a page not shown.
const stripCovered = computed(() => !pageActive.value || props.busy || !!props.paused);

// The pearl plate leans toward the pointer, up to LEAN_DEG, and its frame metal and glare follow.
const heroEl = ref<HTMLElement>();
let leanBox: DOMRect | null = null;
let leanFrame = 0;
let leanAt = { x: 0, y: 0 };
function writeLean(x: number, y: number) {
  const el = heroEl.value;
  if (!el) return;
  el.style.setProperty("--lx", x.toFixed(3));
  el.style.setProperty("--ly", y.toFixed(3));
  el.style.setProperty("--frame-x", (0.3 + x * 0.25).toFixed(3));
  el.style.setProperty("--frame-y", (0.2 + y * 0.25).toFixed(3));
}
function leanStart(e: PointerEvent) {
  pointing.value = true;
  leanBox = (e.currentTarget as HTMLElement).getBoundingClientRect();
}
function leanMove(e: PointerEvent) {
  if (!leanBox || !playing.value) return;
  const clampUnit = (v: number) => Math.max(-1, Math.min(1, v));
  leanAt = {
    x: clampUnit(((e.clientX - leanBox.left) / leanBox.width) * 2 - 1),
    y: clampUnit(((e.clientY - leanBox.top) / leanBox.height) * 2 - 1),
  };
  if (!leanFrame) leanFrame = requestAnimationFrame(() => {
    leanFrame = 0;
    writeLean(leanAt.x, leanAt.y);
  });
}
function leanEnd() {
  leanBox = null;
  cancelAnimationFrame(leanFrame);
  leanFrame = 0;
  writeLean(0, 0);
}
watch(playing, (on) => { if (!on) writeLean(0, 0); });

// The front skin's turn: it types in its first form, then changes. A form key pins one of the two while the pointer
// stays on the stage.
const typed = ref(false);
const pinned = ref<boolean | null>(null);
const keyDown = ref(false);
const formPulse = ref(0);
let typeTimer = 0;
let keyTimer = 0;
function stopTurn() {
  window.clearTimeout(typeTimer);
  window.clearInterval(keyTimer);
  typeTimer = keyTimer = 0;
  keyDown.value = false;
}
function startTurn() {
  stopTurn();
  typed.value = false;
  if (!front.value?.twoForm || !playing.value) return;
  keyTimer = window.setInterval(() => (keyDown.value = !keyDown.value), KEY_MS);
  typeTimer = window.setTimeout(() => (typed.value = true), TYPE_MS);
}
watch([() => front.value?.item.id, playing], startTurn, { immediate: true });
const formShown = computed(() => pinned.value ?? typed.value);
watch(formShown, (on, was) => {
  if (on && was === false && !reducedMotion.value) formPulse.value += 1;
});
function pin(form: boolean) {
  pinned.value = form;
}
function unpoint() {
  pointing.value = false;
  pinned.value = null;
  leanEnd();
}
function go(step: number) {
  const n = items.value.length;
  if (!step || props.busy || n < 2) return;
  pinned.value = null;
  at.value = (at.value + step + n) % n;
}
function onFeaturedKey(e: KeyboardEvent) {
  const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
  const root = e.currentTarget as HTMLElement | null;
  if (!step || !root) return;
  const buttons = [...root.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")];
  const cur = buttons.indexOf(document.activeElement as HTMLButtonElement);
  if (cur < 0) return;
  e.preventDefault();
  const next = (cur + step + buttons.length) % buttons.length;
  buttons[next]?.focus();
  go(next - at.value);
}

// Where the stage lies in a row, the spread poster lies on the page's ground (MainPanel.vue), under the sidebar's seam
// and the window keys: it reaches up to the panel's top edge, which the page does not. Narrow, it stays in the stage.
/** How far the spread poster reaches past the hand: on its right, under the paper's edge, and below the stage, under
 *  the action bar. */
const SPREAD = { right: 140, foot: 10 };
const stageEl = ref<HTMLElement>();
const handEl = ref<HTMLElement>();
/** The page is the one shown: under another page the ground is bare (KeepAlive leaves what is teleported there). */
const there = ref(true);
onActivated(() => { there.value = true; });
onDeactivated(() => { there.value = false; });
interface Box { left: number; top: number; width: number; height: number }
/** The spread poster's box on the ground, from the panel's top edge; none while it stays in the stage. */
const grounded = ref<Box | null>(null);
/** The page's scroller: a scrolled page takes the poster up with it. */
let scroller: HTMLElement | null = null;
function placeGround() {
  const stage = stageEl.value, hand = handEl.value;
  const ground = stage?.closest(".main")?.querySelector<HTMLElement>(".page-ground");
  if (!showcased.value || !stage || !hand || !ground || getComputedStyle(stage).flexDirection !== "row") {
    grounded.value = null;
    return;
  }
  const g = ground.getBoundingClientRect(), s = stage.getBoundingClientRect(), h = hand.getBoundingClientRect();
  const up = scroller?.scrollTop ?? 0;
  const box: Box = {
    left: Math.round(s.left - g.left),
    top: -Math.round(up),
    width: Math.round(h.right + SPREAD.right - s.left),
    height: Math.round(s.bottom + SPREAD.foot - g.top + up),
  };
  const was = grounded.value;
  if (!was || was.left !== box.left || was.top !== box.top || was.width !== box.width || was.height !== box.height) {
    grounded.value = box;
  }
}
const groundBox = computed(() => {
  const b = grounded.value;
  return b ? { left: `${b.left}px`, top: `${b.top}px`, width: `${b.width}px`, height: `${b.height}px` } : undefined;
});
const spreadEl = ref<HTMLElement>();
// Going to another pool unmounts the stage at once while its section fades out (ResonancePage.vue), and what lies on
// the ground would go at once: a copy of it fades out with the section instead.
onBeforeUnmount(() => {
  const el = spreadEl.value, ground = el?.parentElement;
  if (!el || !ground || !grounded.value || reducedMotion.value || typeof el.animate !== "function") return;
  const ghost = el.cloneNode(true) as HTMLElement;
  for (const video of ghost.querySelectorAll("video")) video.remove();
  ground.insertBefore(ghost, el.nextSibling);
  const fade = ghost.animate([{ opacity: getComputedStyle(el).opacity }, { opacity: 0 }], { duration: 120, easing: "ease-in", fill: "forwards" });
  void fade.finished.catch(() => {}).finally(() => ghost.remove());
});

// The showcase width sets the pet's canvas size. The card fan reserves room for the second-form wing.
const plateEl = ref<HTMLElement>();
const plateW = ref(0);
const frontScale = computed(() => Math.max(0.5, plateW.value * (raised.value ? 1 : 0.96) / PET_BASE.width));
const backScale = computed(() => frontScale.value * 0.58);
/** The paper's middle, where a showcased pool's item sits: the pet fills it, clear of its sides and of headwear that
 *  reaches above the canvas (a head anchor above 0). */
const showEl = ref<HTMLElement>();
const showBox = ref({ w: 0, h: 0 });
const showScale = computed(() => {
  const { w, h } = showBox.value;
  if (!w || !h) return 1;
  const item = front.value?.item;
  const headroom = item?.kind === "character" ? Math.max(0, 4 - headAnchor(item.ref).y) : 0;
  return Math.max(0.6, Math.min(2.2, (w - 24) / (PET_BASE.width * petReach.value), (h - 16) / (PET_BASE.height + headroom)));
});
let resize: ResizeObserver | undefined;
let measureFrame = 0;
let observing = false;
function measure() {
  measureFrame = 0;
  const w = plateEl.value?.offsetWidth || (heroEl.value ? heroEl.value.clientWidth / 1.3 : 0);
  if (w > 0) plateW.value = w;
  if (showEl.value) showBox.value = { w: showEl.value.clientWidth, h: showEl.value.clientHeight };
  placeGround();
}
function scheduleMeasure() {
  if (!measureFrame) measureFrame = requestAnimationFrame(measure);
}
function connectResize() {
  observing = true;
  resize?.disconnect();
  for (const el of [plateEl.value, heroEl.value, showEl.value, stageEl.value, handEl.value]) if (el) resize?.observe(el);
  scroller?.removeEventListener("scroll", scheduleMeasure);
  scroller = stageEl.value?.closest<HTMLElement>(".ui-scroll") ?? null;
  scroller?.addEventListener("scroll", scheduleMeasure, { passive: true });
  scheduleMeasure();
}
function disconnectResize() {
  observing = false;
  resize?.disconnect();
  scroller?.removeEventListener("scroll", scheduleMeasure);
  scroller = null;
  cancelAnimationFrame(measureFrame);
  measureFrame = 0;
}
onMounted(() => {
  measure();
  resize = new ResizeObserver(scheduleMeasure);
  connectResize();
});
onActivated(connectResize);
onDeactivated(disconnectResize);
// Another pool may stand the item on another plate or swap between the hand and the hero.
watch([plateEl, heroEl, showEl, handEl, showcased], () => { if (observing) connectResize(); }, { flush: "post" });
onBeforeUnmount(() => {
  disconnectResize();
  cancelAnimationFrame(leanFrame);
  stopTurn();
  clearTimeout(pvStall);
});
</script>

<template>
  <section ref="stageEl" class="banner-stage" :class="{ hold, calm: reducedMotion, pv: pvOn }" @pointerleave="unpoint">
    <div v-if="!(showcased && posterArt)" class="wash" aria-hidden="true">
      <Transition name="wash" :css="!reducedMotion">
        <span v-if="active" :key="active.id" class="wash-blob">
          <img v-if="washArt" :src="washArt" alt="" draggable="false" />
        </span>
      </Transition>
    </div>

    <CardHand
      v-if="raised" class="card-hand" bare :items="DEALT" :busy="busy" :paused="paused" :hold="pointing" crest="LIMITED"
      :style="{ '--pet-reach': petReach }"
      @inspect="emit('inspect', $event)" @pointerenter="pointing = true"
    >
      <template #foreground>
        <div v-if="front" ref="plateEl" class="hand-foreground">
          <i v-if="formPulse && !reducedMotion" :key="formPulse" class="form-ring" aria-hidden="true"></i>
          <TransitionGroup name="pile" :css="!reducedMotion">
            <button
              v-for="f in pile" :key="f.item.id" type="button" class="figure s0" :class="{ card: !f.skin }"
              :disabled="busy" :title="f.item.name" :aria-label="`查看${f.item.name}`" @click="emit('inspect', f.item)"
            >
              <PetView v-if="f.skin" class="pet-sticker" :character="f.item.ref" :scale="frontScale" :key-down="keyDown" :form="formShown" />
              <span v-else class="card-face frame-pearl"><img :src="f.art" alt="" draggable="false" /></span>
            </button>
          </TransitionGroup>
        </div>
      </template>
    </CardHand>
    <div v-else ref="handEl" class="feature-hand" :class="{ lined, spread: showcased }">
      <Teleport v-if="showcased" defer to=".page-ground" :disabled="!grounded">
        <Transition name="ground" appear :css="!reducedMotion">
          <div
            v-if="there" ref="spreadEl" class="poster-spread" :class="{ grounded: !!grounded, calm: reducedMotion }"
            :style="groundBox" aria-hidden="true"
          >
            <div class="poster-art">
              <Transition name="wash" :css="!reducedMotion">
                <img v-if="posterArt" :key="posterArt" :class="{ veiled: pvOn }" :src="posterArt" alt="" draggable="false" />
              </Transition>
              <Transition name="pv">
                <video
                  v-if="pvOn" :key="pvRun" :src="pvArt" autoplay muted playsinline disablepictureinpicture
                  @playing="pvPlaying" @ended="pvEnd" @error="pvEnd"
                ></video>
              </Transition>
            </div>
            <div v-if="titleArt" class="poster-title" :class="{ veiled: pvOn }">
              <img :src="titleArt" alt="" draggable="false" />
            </div>
          </div>
        </Transition>
      </Teleport>
      <div
        v-else ref="heroEl" class="hero" :style="{ '--lean': `${LEAN_DEG}deg` }"
        @pointerenter="leanStart" @pointermove="leanMove" @pointerleave="leanEnd"
      >
        <span ref="plateEl" class="plate frame-pearl" aria-hidden="true">
          <span class="plate-face">
            <i class="rays"><i></i></i>
            <i class="glare"></i>
          </span>
          <b class="crest">LIMITED</b>
        </span>
        <i v-if="formPulse && !reducedMotion" :key="formPulse" class="form-ring" aria-hidden="true"></i>
        <TransitionGroup name="pile" :css="!reducedMotion">
          <button
            v-for="f in pile" :key="f.item.id" type="button" class="figure" :class="[`s${f.step}`, { card: !f.skin }]"
            :disabled="busy" :title="f.item.name" :tabindex="f.step ? -1 : undefined"
            :aria-label="f.step ? `换到${f.item.name}` : `查看${f.item.name}`"
            @click="f.step ? go(f.step) : emit('inspect', f.item)"
          >
            <PetView
              v-if="f.skin" class="pet-sticker" :character="f.item.ref" :scale="f.step ? backScale : frontScale"
              :key-down="!f.step && keyDown" :form="f.step ? false : formShown"
            />
            <span v-else class="card-face frame-pearl"><img :src="f.art" alt="" draggable="false" /></span>
          </button>
        </TransitionGroup>
        <span class="inspect-pill" aria-hidden="true"><Icon name="search" :size="11" />查看</span>
        <Icon name="spark" :size="24" class="twinkle top" />
        <Icon name="spark" :size="13" class="twinkle side" />
      </div>
      <div v-if="lined" class="lineup" @pointerenter="pointing = true">
        <button type="button" class="flip ui-btn ghost" aria-label="上一个" :disabled="busy" @click="go(-1)"><Icon name="back" :size="18" /></button>
        <div class="row" @keydown="arrowSelect($event, $event.currentTarget as HTMLElement)">
          <button
            v-for="(item, i) in items" :key="item.id" type="button" class="mini" :class="{ on: i === at, got: owns(item) }"
            :disabled="busy" :title="item.name" :aria-pressed="i === at" @click="go(i - at)"
          >
            <span class="mini-art">
              <PetBust v-if="item.kind === 'character'" :src="getCharacter(item.ref)!.bg" />
              <img v-else :src="assetUrl(item.art)" :alt="item.name" draggable="false" />
            </span>
            <i v-if="i === at && !reducedMotion" class="tick" aria-hidden="true" @animationend="go(1)"></i>
          </button>
        </div>
        <button type="button" class="flip next ui-btn ghost" aria-label="下一个" :disabled="busy" @click="go(1)"><Icon name="back" :size="18" /></button>
      </div>
    </div>

    <div class="info">
      <header class="title">
        <slot name="switch"><span class="ui-eyebrow">RESONANCE</span></slot>
        <h3 :class="{ sr: !!titleArt }">{{ banner.name }}</h3>
      </header>

      <div class="sheet" :class="{ 'has-forms': !!forms, 'has-show': showcased }">
        <div v-if="peek" class="peek" aria-hidden="true">
          <Transition name="peek" mode="out-in" :css="!reducedMotion">
            <PetBust :key="peek.key" class="peek-bust" :src="peek.src" />
          </Transition>
        </div>
        <div v-if="!showcased" class="feature-slot">
          <Transition name="feature" mode="out-in" :css="!reducedMotion">
            <div v-if="feature" :key="active?.id" class="feature">
              <p class="tags">
                <span class="ui-tag up"><em>UP</em>限定{{ feature.kind }}</span>
                <span class="who"><i :style="{ background: feature.color }"></i>{{ feature.who }}</span>
                <span class="series">{{ feature.series }}</span>
              </p>
              <h4>{{ feature.title }}</h4>
              <p class="owned" :class="{ yes: feature.owned }">
                <template v-if="feature.owned"><Icon name="check" :size="14" />已拥有</template>
                <template v-else><Icon name="lock" :size="13" />未获得</template>
              </p>
            </div>
          </Transition>
          <span v-if="left" class="time-left"><Icon name="clock" :size="11" /><span class="sr">剩余</span>{{ left }}</span>
        </div>

        <div v-if="showcased && front" ref="showEl" class="show-stage">
          <div v-if="memories.length" class="memories" :class="{ halt: !playing, hold }" aria-hidden="true">
            <span v-for="(m, i) in memories" :key="i" class="memory" :class="m.kind" :style="m.style">
              <img :src="m.src" alt="" draggable="false" />
            </span>
          </div>
          <button
            type="button" class="showcase" :class="{ card: !front.skin }" :disabled="busy" :title="front.item.name"
            :aria-label="`查看${front.item.name}`" @click="emit('inspect', front.item)" @pointerenter="pointing = true"
          >
            <i v-if="formPulse && !reducedMotion" :key="formPulse" class="form-ring" aria-hidden="true"></i>
            <Transition name="show" mode="out-in" :css="!reducedMotion">
              <span v-if="front.skin" :key="front.item.id" class="show-floor">
                <PetView class="showcase-pet" :character="front.item.ref" :scale="showScale" :key-down="keyDown" :form="formShown" />
              </span>
              <span v-else :key="front.item.id" class="card-face frame-pearl"><img :src="front.art" alt="" draggable="false" /></span>
            </Transition>
          </button>
        </div>

        <div v-if="forms" class="forms" role="group" aria-label="形态" @keydown="arrowSelect($event, $event.currentTarget as HTMLElement)">
          <template v-for="(f, i) in forms" :key="i">
            <span v-if="i" class="form-bridge" aria-hidden="true">
              <Icon name="forward" :size="14" class="form-arrow" :class="{ on: formShown }" />
              <span class="form-timer" :class="{ run: playing && pinned === null && !typed, full: formShown }">
                <i :key="front?.item.id" :style="{ '--type-ms': `${TYPE_MS}ms` }"></i>
              </span>
            </span>
            <button type="button" class="form-key" :class="{ on: formShown === !!i }" :aria-pressed="formShown === !!i" :disabled="busy" @click="pin(!!i)">
              <span class="form-art"><img :src="f" alt="" draggable="false" /></span>
              <b>{{ i ? '二形态' : '一形态' }}</b>
            </button>
          </template>
        </div>

        <div class="meter">
          <div class="lead">
            <p class="l-head" :class="{ line: showcased }">
              <template v-if="showcased">
                <span v-if="feature" class="ui-tag up"><em>UP</em><span class="up-word">限定{{ feature.kind }}</span></span>
                <span v-if="left" class="time-left"><Icon name="clock" :size="11" /><span class="sr">剩余</span>{{ left }}</span>
              </template>
              <em>{{ featuredWord }}</em><b>{{ got }}</b><i>/{{ items.length }}</i>
              <span v-if="featuredOdds" class="odds">{{ featuredOdds }}</span>
              <span v-if="banner.pity" class="odds">{{ banner.pity }} 次保底</span>
            </p>
            <div v-if="!soleShow" class="stands" @keydown="onFeaturedKey" @pointerenter="pointing = true">
              <button
                v-for="(item, i) in items" :key="item.id" type="button" class="stand-key" :class="{ on: i === at, done: owns(item) }"
                :disabled="busy" :title="item.name" :aria-label="i === at ? `查看${item.name}` : `换到${item.name}`"
                :aria-pressed="i === at" @click="i === at ? emit('inspect', item) : go(i - at)"
              >
                <span class="stand" aria-hidden="true">
                  <PetBust v-if="item.kind === 'character'" class="stand-bust" :src="getCharacter(item.ref)!.bg" />
                  <span v-else class="stand-card frame-pearl"><img :src="assetUrl(item.art)" alt="" draggable="false" /></span>
                </span>
                <b class="stand-name"><Icon :name="owns(item) ? 'check' : 'lock'" :size="11" /><span>{{ item.name }}</span></b>
                <i v-if="i === at && !lined && items.length > 1 && !reducedMotion" class="tick" aria-hidden="true" @animationend="go(1)"></i>
              </button>
            </div>
          </div>
          <CollectionRows :closet="raised" :busy="busy" :hold="hold" @plate="emit('plate', $event)">
            <template #closet><span v-if="odds('limited')" class="odds">{{ odds("limited") }}</span></template>
          </CollectionRows>
        </div>
      </div>

      <div
        v-if="strip.length" class="closet-strip" :class="{ keyed: stripKeyed, covered: stripCovered }" role="region" aria-label="衣橱卡牌"
        :style="{ '--marquee': `${strip.length * 2.1}s` }"
        @pointerdown="stripKeyed = false" @keydown="onStripKey"
        @focusin="stripKeyed = ($event.target as HTMLElement).matches(':focus-visible')"
        @focusout="stripKeyed = false"
      >
        <div class="strip-track">
          <div v-for="copy in reducedMotion ? 1 : 2" :key="copy" class="strip-group" :aria-hidden="copy === 2 ? true : undefined">
            <button
              v-for="(c, i) in strip" :key="c.item.id" type="button" class="strip-card"
              :tabindex="copy === 1 && i === 0 ? undefined : -1"
              :disabled="busy" :title="c.item.name" :aria-label="`查看${c.item.name}`" @click="emit('inspect', c.item)"
            >
              <span class="card-face frame-pearl"><img :src="c.art" alt="" draggable="false" /></span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.banner-stage {
  /* The same hero as the standing pool's, so switching pools moves nothing but the content. */
  --hero-h: max(196px, min(0.66 * (100cqh - 46px), 100cqh - 296px, 42cqw));
  --card-w: calc(var(--hero-h) * 0.7);
  --stage-gap: 28px;
  position: relative;
  isolation: isolate;
  flex: 1 0 auto;
  display: flex;
  align-items: stretch;
  gap: var(--stage-gap);
  padding: 18px 26px 10px 34px;
  box-sizing: border-box;
}

/* Pearl-infused wash behind the hand, masked well clear of the sidebar tab seam and the paper sheet. */
.wash {
  position: absolute;
  left: 24px;
  top: 0;
  bottom: 0;
  width: calc(var(--card-w) * 1.3 + 90px);
  overflow: hidden;
  pointer-events: none;
  -webkit-mask: radial-gradient(closest-side, #000 25%, transparent 100%);
  mask: radial-gradient(closest-side, #000 25%, transparent 100%);
}
.wash::before {
  content: "";
  position: absolute;
  inset: 14% 8%;
  background: var(--grad-pearl);
  filter: blur(28px);
  opacity: 0.42;
}
.wash-blob {
  position: absolute;
  left: 50%;
  top: 46%;
  width: 72px;
  height: 72px;
  transform: translate(-50%, -50%) scale(7);
}
.wash-blob img {
  display: block;
  width: 72px;
  height: 72px;
  object-fit: cover;
  filter: blur(5px) saturate(1.4) brightness(1.1);
  opacity: 0.45;
}
.wash-enter-active,
.wash-leave-active {
  transition: opacity 900ms var(--ease-in-out);
}
.wash-enter-from,
.wash-leave-to {
  opacity: 0;
}

.feature-hand {
  position: relative;
  z-index: 1;
  flex: none;
  width: calc(var(--card-w) * 1.3);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 10px;
}
.hero {
  --lx: 0;
  --ly: 0;
  position: relative;
  flex: none;
  height: var(--hero-h);
}
/* Without a lineup the hero has its room: the cards stand clear over the item on show. */
.feature-hand:not(.lined) {
  justify-content: center;
}
.feature-hand:not(.lined) .hero {
  height: calc(var(--hero-h) + 54px);
}
/* No card: the poster spreads over the left of the panel. It comes in from the sidebar's seam, and goes out toward the
 * action bar and, before the pool keys, under the paper. The room keeps the hero's. In the stage it starts a little
 * above the stage; on the page's ground (`.grounded`, placed by placeGround) at the panel's top edge, under the window
 * keys. */
.feature-hand.spread {
  min-height: calc(var(--hero-h) + 54px);
}
.poster-spread {
  position: absolute;
  top: -18px;
  bottom: -10px;
  left: -34px;
  right: -140px;
  pointer-events: none;
}
.poster-spread.grounded {
  right: auto;
  bottom: auto;
}
.poster-art {
  position: absolute;
  inset: 0;
  -webkit-mask-image: linear-gradient(90deg, transparent, #000 32px, #000 50%, transparent 80%);
  mask-image: linear-gradient(90deg, transparent, #000 32px, #000 50%, transparent 80%);
}
.poster-art img,
.poster-art video {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: 50% 18%;
  -webkit-mask-image: linear-gradient(180deg, transparent, #000 6%, #000 80%, transparent);
  mask-image: linear-gradient(180deg, transparent, #000 6%, #000 80%, transparent);
}
.grounded .poster-art img,
.grounded .poster-art video {
  -webkit-mask-image: linear-gradient(180deg, #000 80%, transparent);
  mask-image: linear-gradient(180deg, #000 80%, transparent);
}
/* The clip has the poster's shape with 心宜 left of its middle: a narrower stage gives up its right first. */
.poster-art video {
  object-position: 30% 50%;
}
/* The poster waits under the PV and comes in as the clip goes. */
.poster-art img {
  transition: opacity 900ms var(--ease-in-out);
}
.poster-art img.veiled {
  opacity: 0;
}
/* On the ground it comes and goes with the stage. */
.ground-enter-active {
  transition: opacity 320ms var(--ease-out);
}
.ground-leave-active {
  transition: opacity 120ms var(--ease-in);
}
.ground-enter-from,
.ground-leave-to {
  opacity: 0;
}
/* The poster's title as printed, on its lower left, clear of the action bar. Its pale lines are drawn for the poster's
 * dark cloth: a mist of the cloth's red under it, and a dark edge on its lines as the cloth's shadow, carry them off
 * whatever the poster has there and off the paper the poster fades into. It goes with the PV and comes in after it, a
 * little after the poster. */
.poster-title {
  --mist: 108 20 34;
  --edge: 70 8 20;
  position: absolute;
  left: 34px;
  bottom: 36px;
  width: min(340px, 62%);
  transition: opacity 900ms var(--ease-in-out) 300ms, translate 900ms var(--ease-out) 300ms;
}
.poster-title::before {
  content: "";
  position: absolute;
  inset: -46% -30% -44% -26%;
  background: radial-gradient(closest-side, rgb(var(--mist) / 0.88), rgb(var(--mist) / 0.66) 46%, rgb(var(--mist) / 0.28) 74%,
    rgb(var(--mist) / 0) 100%);
}
.poster-title img {
  position: relative;
  display: block;
  width: 100%;
  height: auto;
  filter: drop-shadow(0 0 1px rgb(var(--edge) / 0.9)) drop-shadow(0 2px 6px rgb(var(--edge) / 0.45));
}
.poster-title.veiled {
  opacity: 0;
  translate: 0 8px;
  transition-duration: 300ms;
  transition-delay: 0ms;
}
.calm .poster-title {
  transition: none;
}
.pv-enter-active {
  transition: opacity 600ms var(--ease-out);
}
.pv-leave-active {
  transition: opacity 900ms var(--ease-in-out);
}
.pv-enter-from,
.pv-leave-to {
  opacity: 0;
}
.feature-hand.spread .lineup {
  position: relative;
  margin-top: auto;
}
/* The pearl card the stickers are piled on: leans toward the pointer with sliding pearl metal and specular glare. */
.plate {
  position: absolute;
  left: 0;
  bottom: 0;
  width: var(--card-w);
  height: var(--hero-h);
  padding: calc(var(--card-w) * 0.015);
  box-sizing: border-box;
  border-radius: var(--radius-m);
  background: var(--frame-fill) var(--frame-at) / var(--frame-size);
  box-shadow: 0 0 0 3px #fff, 0 16px 28px -16px rgba(var(--shadow-rgb), 0.6);
  transform: rotate(-3deg) perspective(900px) rotateX(calc(var(--ly) * -1 * var(--lean))) rotateY(calc(var(--lx) * var(--lean)));
  transform-origin: 50% 100%;
  transition: transform 180ms var(--ease-out), box-shadow var(--dur-base);
}
.hero:hover .plate {
  transform: translateY(-5px) rotate(0deg) perspective(900px) rotateX(calc(var(--ly) * -1 * var(--lean))) rotateY(calc(var(--lx) * var(--lean)));
  box-shadow:
    0 0 0 3px #fff,
    0 0 26px 4px color-mix(in srgb, var(--holo-lilac) 52%, transparent),
    0 24px 32px -16px rgba(var(--shadow-rgb), 0.6);
}
.calm .plate,
.calm .hero:hover .plate {
  --lean: 0deg;
}
.plate-face {
  position: relative;
  display: block;
  width: 100%;
  height: 100%;
  border-radius: calc(var(--radius-m) - 2px);
  overflow: hidden;
  background: linear-gradient(160deg, #fff 10%, color-mix(in srgb, var(--holo-lilac) 26%, #fff) 52%,
    color-mix(in srgb, var(--holo-pink) 30%, #fff) 82%, color-mix(in srgb, var(--holo-mint) 22%, #fff));
}
.rays {
  position: absolute;
  left: 50%;
  top: 58%;
  width: 190%;
  aspect-ratio: 1;
  translate: -50% -50%;
  border-radius: 50%;
  overflow: hidden;
  -webkit-mask: radial-gradient(circle, #000 12%, transparent 62%);
  mask: radial-gradient(circle, #000 12%, transparent 62%);
  opacity: 0.82;
}
.rays i {
  position: absolute;
  inset: -20%;
  background: repeating-conic-gradient(#fff 0 5deg, transparent 5deg 20deg);
  animation: rays-turn 96s linear infinite;
}
.hold .rays i,
.calm .rays i {
  animation-play-state: paused;
}
@keyframes rays-turn {
  to { rotate: 360deg; }
}
.glare {
  position: absolute;
  left: -50%;
  top: -50%;
  width: 200%;
  height: 200%;
  background: radial-gradient(circle at 50% 50%, rgba(255, 255, 255, 0.56), transparent 34%);
  opacity: 0;
  pointer-events: none;
  transform: translate(calc(var(--lx) * 22%), calc(var(--ly) * 22%));
  transition: opacity var(--dur-base), transform 160ms var(--ease-out);
}
.hero:hover .glare {
  opacity: 1;
}
.calm .glare {
  display: none;
}
.crest {
  position: absolute;
  top: 2px;
  left: 50%;
  translate: -50% 0;
  padding: 3px 18px 4px;
  border-radius: 0 0 var(--radius-l) var(--radius-l);
  background: var(--night);
  box-shadow: 0 0 0 1px var(--pearl);
  color: var(--holo-cream);
  font: 800 var(--fs-caption)/1 var(--font-latin);
  letter-spacing: 0.18em;
  white-space: nowrap;
}
/* The figure occupies space below the cards, with only its head overlapping the fan. */
.card-hand {
  --pet-overlap: calc(var(--card-w) * 0.16);
  --pill-bottom: calc(var(--pet-overlap) + 8px);
  align-self: flex-start;
  gap: 0;
}
.hand-foreground {
  position: relative;
  z-index: 5;
  display: grid;
  justify-items: start;
  width: calc(var(--card-w) * 1.09);
  max-width: calc((100% - 20px) / var(--pet-reach));
  margin-top: calc(0px - var(--pet-overlap));
}
.hand-foreground .form-ring {
  left: 50%;
  top: 50%;
  width: 80%;
}
/* Pearl shockwave behind the active skin when it transforms into its second form. */
.form-ring {
  position: absolute;
  z-index: 2;
  left: calc(var(--card-w) * 0.5);
  top: 66%;
  width: calc(var(--card-w) * 0.82);
  aspect-ratio: 1;
  translate: -50% -50%;
  border-radius: 50%;
  box-shadow:
    0 0 0 3px #fff,
    0 0 24px 5px color-mix(in srgb, var(--holo-lilac) 80%, transparent),
    inset 0 0 20px 4px color-mix(in srgb, var(--holo-pink) 65%, transparent);
  pointer-events: none;
  animation: form-ring 560ms var(--ease-out) both;
}
@keyframes form-ring {
  from { opacity: 0.95; scale: 0.45; }
  to { opacity: 0; scale: 1.35; }
}

/* A sticker of the pile. The one on show sits low and large; the next ones lean out behind it, at the top. */
.figure {
  position: absolute;
  padding: 0;
  border: 0;
  background: none;
  cursor: pointer;
  transform-origin: 50% 100%;
  transition: left var(--dur-stage) var(--ease-out), top var(--dur-stage) var(--ease-out), rotate var(--dur-stage) var(--ease-out),
    translate var(--dur-base) var(--ease-out), opacity var(--dur-base);
}
.figure :deep(.still) {
  filter: var(--sticker-lg);
}
/* Opaque dimming on back stickers so overlapping silhouettes never bleed through one another. */
.figure:not(.s0) :deep(.still) {
  filter: var(--sticker) brightness(0.93);
  transition: filter var(--dur-base);
}
.figure:not(.s0):hover:not(:disabled) :deep(.still) {
  filter: var(--sticker);
}
.pet-sticker {
  display: block;
  pointer-events: none;
}
.s0 {
  z-index: 3;
  left: 1.5%;
  top: 53%;
}
.s1 {
  z-index: 2;
  left: -2%;
  top: 9%;
  rotate: -7deg;
}
.s2 {
  z-index: 1;
  left: 33%;
  top: 16%;
  rotate: 6deg;
}
.hero:hover .s1:not(:disabled) {
  translate: -4px -3px;
  rotate: -9deg;
}
.hero:hover .s2:not(:disabled) {
  translate: 4px -2px;
  rotate: 8deg;
}
.figure:not(.s0):hover:not(:disabled) {
  rotate: 0deg;
  translate: 0 -5px;
}
.s0:hover:not(:disabled) {
  translate: 0 -3px;
}
/* A card among the featured items stands in the pile inside its pearl metal frame. */
.figure.card.s0 { left: 10%; top: 21%; width: 56%; }
.figure.card:not(.s0) { width: 30%; }
.hand-foreground .figure.s0 {
  position: relative;
  inset: auto;
  grid-area: 1 / 1;
}
.hand-foreground .figure.card.s0 {
  width: 40%;
  justify-self: center;
}
.hand-foreground .figure.pile-leave-active {
  position: absolute;
  bottom: 0;
  pointer-events: none;
}
.card-face {
  display: block;
  aspect-ratio: 2 / 3;
  padding: 3%;
  box-sizing: border-box;
  border-radius: var(--radius-m);
  background: var(--frame-fill) var(--frame-at) / var(--frame-size);
  box-shadow: 0 0 0 3px #fff, 0 12px 20px -14px rgba(var(--shadow-rgb), 0.6);
  transition: filter var(--dur-base);
}
.figure.card:not(.s0) .card-face {
  filter: brightness(0.92);
}
.figure.card:not(.s0):hover:not(:disabled) .card-face {
  filter: none;
}
.card-face img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: calc(var(--radius-m) - 3px);
}
.pile-enter-active,
.pile-leave-active {
  transition: opacity 320ms, translate 420ms var(--ease-out);
}
.pile-leave-active {
  z-index: 4;
}
.pile-enter-from {
  opacity: 0;
  translate: 12% -6%;
}
.pile-leave-to {
  opacity: 0;
  translate: -30% 6%;
}
.inspect-pill {
  position: absolute;
  z-index: 4;
  left: calc(var(--card-w) * 0.5);
  bottom: 10px;
  translate: -50% 4px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px 3px 8px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 0 0 1.5px var(--pearl), 0 6px 14px -6px rgba(var(--shadow-rgb), 0.35);
  color: var(--night);
  font: 800 var(--fs-caption)/1.2 var(--font);
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--dur-base), translate var(--dur-base) var(--ease-out);
}
.hero:hover .inspect-pill,
.hero:has(.s0:focus-visible) .inspect-pill {
  opacity: 1;
  translate: -50% 0;
}
.twinkle {
  position: absolute;
  z-index: 4;
  color: var(--pearl-deep);
  fill: var(--surface);
  stroke-width: 1.2;
  pointer-events: none;
}
.twinkle.top { top: -14px; left: -16px; }
.twinkle.side { top: 12px; left: 14px; }

/* As wide as the card: the sheet lies over the rest of the hand. */
.lineup {
  width: var(--card-w);
  display: flex;
  align-items: center;
  gap: 2px;
  padding-bottom: 8px;
}
.flip {
  flex: none;
  width: 28px;
  height: 28px;
  padding: 0;
}
.flip.next svg {
  rotate: 180deg;
}
.row {
  flex: 1;
  min-width: 0;
  display: flex;
  justify-content: center;
  gap: clamp(4px, 1.2cqw, 10px);
}
.mini {
  position: relative;
  flex: 0 1 46px;
  min-width: 0;
  width: auto;
  height: auto;
  aspect-ratio: 1;
  padding: 2px;
  box-sizing: border-box;
  border: 0;
  border-radius: var(--radius-s);
  background: var(--surface);
  box-shadow: var(--shadow-paper);
  cursor: pointer;
  transition: transform var(--dur-base) var(--ease-out), box-shadow var(--dur-base);
}
.mini:hover:not(:disabled):not(.on) {
  transform: translateY(-2px);
}
.mini-art {
  display: block;
  width: 100%;
  height: 100%;
  border-radius: calc(var(--radius-s) - 2px);
  background: var(--c-50);
  overflow: hidden;
}
.mini-art > * {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.mini:not(.got) .mini-art {
  filter: var(--dim);
}
.mini.on {
  transform: translateY(-3px);
  box-shadow: 0 0 0 2px var(--pearl-deep), 0 6px 12px -6px rgba(var(--shadow-rgb), 0.5);
}
.mini.on .mini-art {
  filter: none;
  background: color-mix(in srgb, var(--holo-lilac) 18%, var(--surface));
}
/* The turn of the item on show: when the bar is full the next one comes forward. */
.tick {
  position: absolute;
  left: 4px;
  right: 4px;
  bottom: -7px;
  height: 3px;
  border-radius: 2px;
  background: linear-gradient(90deg, var(--pearl-deep), var(--holo-lilac));
  transform-origin: 0 50%;
  animation: tick 7s linear both;
}
.hold .tick,
.pv .tick,
.lineup:has(:focus-visible) .tick {
  animation-play-state: paused;
}
@keyframes tick {
  from { transform: scaleX(0); }
}

.info {
  position: relative;
  z-index: 2;
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-top: 0;
}
.title .ui-eyebrow {
  margin-bottom: 8px;
  font-size: 13px;
  letter-spacing: 0.22em;
}
h3 {
  margin: 0;
  font: 800 clamp(36px, 5.2cqw, 48px)/1.04 var(--font);
  letter-spacing: 0.03em;
}
/* Read out, not shown: the pool's name where its title lies on the poster, and the word before the time left. */
.sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
.sheet {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 10px;
  margin-left: calc(var(--stage-gap) * -1 - 18px);
  padding: 13px 18px 12px;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: var(--shadow-paper);
}
.meter :deep(.c-row:last-child) {
  padding-bottom: 2px;
}
/* Under the sheet, on the page itself: the limited cards this pool rates pass by as small pearl cards. */
.closet-strip {
  flex: none;
  min-width: 0;
  margin-left: calc(var(--stage-gap) * -1 - 18px);
  padding: 5px 0;
  overflow: hidden;
  scrollbar-width: none;
  /* The row dissolves at the two ends it passes off. */
  -webkit-mask-image: linear-gradient(90deg, transparent, #000 28px, #000 calc(100% - 28px), transparent);
  mask-image: linear-gradient(90deg, transparent, #000 28px, #000 calc(100% - 28px), transparent);
}
.closet-strip::-webkit-scrollbar { display: none; }
.closet-strip.keyed,
.calm .closet-strip {
  overflow-x: auto;
}
.strip-track {
  display: flex;
  width: max-content;
  animation: strip-pass var(--marquee, 80s) linear infinite;
}
/* It keeps passing under the pointer and while the stage holds; only the keyboard walking it stops it. */
.keyed .strip-track,
.calm .strip-track {
  animation: none;
}
/* Covered or off screen it waits where it is, and goes on from there. */
.covered .strip-track {
  animation-play-state: paused;
}
.strip-group {
  flex: none;
  display: flex;
  gap: 9px;
  padding-right: 9px;
}
.strip-card {
  flex: none;
  width: 36px;
  padding: 0;
  border: 0;
  background: none;
  cursor: pointer;
  rotate: -2deg;
  transition: translate var(--dur-base) var(--ease-out), rotate var(--dur-base) var(--ease-out);
}
.strip-card:nth-child(even) {
  rotate: 2deg;
}
.strip-card .card-face {
  width: 100%;
  padding: 2px;
  border-radius: 7px;
  box-shadow: 0 0 0 2px #fff, 0 6px 10px -7px rgba(var(--shadow-rgb), 0.6);
}
.strip-card .card-face img {
  border-radius: 5px;
}
.strip-card:hover:not(:disabled),
.strip-card:focus-visible {
  translate: 0 -3px;
  rotate: 0deg;
}
.strip-card:focus-visible {
  outline: none;
}
.strip-card:focus-visible .card-face {
  box-shadow: 0 0 0 2px #fff, 0 0 0 4px var(--pearl-deep);
}
@keyframes strip-pass {
  to { transform: translateX(-50%); }
}
/* Behind the sheet, so only what rises over its top edge shows. */
.peek {
  --peek-w: clamp(64px, 11cqw, 92px);
  position: absolute;
  z-index: -1;
  right: 10px;
  bottom: calc(100% - var(--peek-w) * 0.08);
  width: var(--peek-w);
  height: calc(var(--peek-w) * 1.04);
  pointer-events: none;
}
.peek-bust {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  rotate: 7deg;
  filter: var(--contour) drop-shadow(0 2px 3px rgba(var(--shadow-rgb), 0.18));
}
.peek-enter-active {
  transition: translate 520ms var(--ease-pop);
}
.peek-leave-active {
  transition: translate 200ms var(--ease-in);
}
.peek-enter-from,
.peek-leave-to {
  translate: 0 100%;
}
.feature-slot {
  min-height: 70px;
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.feature {
  flex: 1;
  min-width: 0;
}
/* What is left of the pool's time, at the right end of the tags row, in the limited pools' pearl; it stays while the
 * featured items take turns. */
.time-left {
  flex: none;
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  height: 20px;
  padding: 0 7px 0 5px;
  box-sizing: border-box;
  border-radius: 5px;
  background: color-mix(in srgb, var(--holo-lilac) 24%, var(--c-50));
  color: var(--night);
  font: 800 var(--fs-caption)/1 var(--font);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.time-left svg {
  color: var(--pearl-deep);
}
.tags {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  min-width: 0;
  white-space: nowrap;
}
.up {
  --tag-bg: var(--grad-pearl);
  --tag-fg: var(--night);
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px 2px 3px;
  line-height: 16px;
  font-size: var(--fs-label);
}
.up em {
  padding: 0 5px;
  border-radius: 4px;
  background: var(--night);
  color: var(--holo-cream);
  font: 800 var(--fs-caption)/16px var(--font-latin);
  font-style: normal;
  letter-spacing: 0.08em;
}
.who {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: var(--fs-label);
  font-weight: 800;
}
.who i {
  width: 4px;
  height: 12px;
}
.series {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: var(--fs-label);
  font-weight: 500;
  color: var(--ink-3);
}
.feature h4 {
  margin: 4px 0 3px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: 800 clamp(20px, 2.8cqw, 26px)/1.22 var(--font);
  letter-spacing: 0.02em;
}
.owned {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin: 0;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--ink-3);
}
.owned.yes {
  color: var(--c-700);
}
.feature-enter-active {
  transition: opacity 260ms, transform 360ms var(--ease-out);
}
.feature-leave-active {
  transition: opacity 140ms var(--ease-in), transform 140ms var(--ease-in);
}
.feature-enter-from {
  opacity: 0;
  transform: translateX(14px);
}
.feature-leave-to {
  opacity: 0;
  transform: translateX(-8px);
}

/* A showcased pool has no sheet: its scrapbook lies on the page with the item on show in front of it, and one line of
 * the pool under them. */
.sheet.has-show {
  padding: 0 0 0 18px;
  background: none;
  box-shadow: none;
}
.show-stage {
  position: relative;
  flex: 1 1 0;
  min-height: 110px;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}
/* The item on show, at the scrapbook's foot, as large as the room holds, its desk on a soft shadow. */
.showcase {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding: 0 0 8px;
  box-sizing: border-box;
  border: 0;
  background: none;
  cursor: pointer;
}
.showcase.card {
  align-self: stretch;
}
/* The scrapbook: the member's cards as prints in a white border and her emotes as die-cut stickers. As the pool comes
 * on screen they come in one by one, each with a flash, while the PV plays; then now and then one catches the light. */
.memories {
  position: absolute;
  inset: 0;
  container-type: size;
  pointer-events: none;
}
.memory {
  position: absolute;
  rotate: var(--rot);
  opacity: 0;
}
.memory img {
  display: block;
  width: 100%;
}
.photo {
  width: min(25cqw, 31cqh);
  aspect-ratio: 2 / 3;
  padding: 4px;
  box-sizing: border-box;
  border-radius: 3px;
  background: #fff;
  box-shadow: 0 7px 14px -9px rgba(var(--shadow-rgb), 0.5), 0 0 0 0.5px rgba(var(--shadow-rgb), 0.08);
}
.photo img {
  height: 100%;
  object-fit: cover;
  border-radius: 1.5px;
}
/* The flash: white over the print as it comes, going off it. A sticker flashes by its own light (memory-in). */
.photo::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: #fff;
  opacity: 0;
}
.sticker {
  width: min(14.5cqw, 18cqh);
}
.sticker img {
  height: auto;
  filter: var(--sticker);
}
.memories .memory {
  animation:
    memory-in 520ms var(--ease-out) var(--at) both,
    memory-glint var(--round) linear calc(var(--at) + 2.4s + var(--glint)) infinite;
}
.memories .photo::after {
  animation: memory-flash 560ms var(--ease-out) var(--at) both;
}
/* The light waits while the pointer is on the stage; all of it waits while the stage stops. */
.memories.hold .memory {
  animation-play-state: running, paused;
}
.memories.halt .memory,
.memories.halt .photo::after {
  animation-play-state: paused;
}
.calm .memories .memory {
  opacity: 1;
  animation: none;
}
.calm .memories .photo::after {
  animation: none;
}
@keyframes memory-in {
  from { opacity: 0; scale: 1.12; translate: 0 -6px; filter: brightness(1.8); }
  40% { opacity: 1; }
  to { opacity: 1; scale: 1; translate: 0 0; filter: brightness(1); }
}
@keyframes memory-flash {
  from { opacity: 0.92; }
  to { opacity: 0; }
}
@keyframes memory-glint {
  0%, 2.6%, 100% { filter: brightness(1); }
  1.1% { filter: brightness(1.28); }
}
.show-floor {
  position: relative;
  z-index: 1;
  flex: none;
  display: block;
}
.show-floor::before {
  content: "";
  position: absolute;
  left: 16%;
  right: 16%;
  bottom: -8px;
  height: 16px;
  border-radius: 50%;
  background: radial-gradient(closest-side, rgba(var(--shadow-rgb), 0.2), transparent);
}
.showcase:focus-visible {
  outline: 2px solid var(--c-500);
  outline-offset: 2px;
  border-radius: var(--radius-m);
}
.showcase-pet,
.showcase .card-face {
  z-index: 1;
  flex: none;
  transition: translate var(--dur-base) var(--ease-out);
}
.showcase-pet {
  pointer-events: none;
}
.showcase-pet :deep(.still) {
  filter: var(--sticker-lg);
}
.showcase .card-face {
  position: relative;
  height: 100%;
}
.showcase:hover:not(:disabled) .showcase-pet,
.showcase:hover:not(:disabled) .card-face {
  translate: 0 -3px;
}
.showcase .form-ring {
  z-index: 0;
  left: 50%;
  top: 55%;
  width: min(64%, 220px);
}
.show-enter-active {
  transition: opacity 260ms, translate 360ms var(--ease-out);
}
.show-leave-active {
  transition: opacity 140ms var(--ease-in);
}
.show-enter-from {
  opacity: 0;
  translate: 0 8px;
}
.show-leave-to {
  opacity: 0;
}

/* The two forms of the skin on show, as tactile rounded keys: the lit one is latched in pearl, a press holds the other. */
.forms {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
}
.form-key {
  --face: linear-gradient(180deg, #fff, var(--key-white-shade));
  --lip: var(--c-200);
  --key-lip-h: 3px;
  --key-y: 0px;
  --lip-shadow: 0 4px 8px -3px rgba(var(--c-900-rgb), 0.22);
  position: relative;
  isolation: isolate;
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-bottom: 3px;
  padding: 6px 6px 5px;
  box-sizing: border-box;
  border: 0;
  border-radius: var(--radius-key);
  background: none;
  color: var(--ink-2);
  font: 800 var(--fs-label)/1.1 var(--font);
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transform: translateY(var(--key-y));
  transition:
    transform var(--dur-release) var(--ease-spring),
    color var(--dur-base);
}
.form-key::before,
.form-key::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  pointer-events: none;
}
.form-key::before {
  z-index: -2;
  background: var(--lip);
  box-shadow: var(--lip-shadow);
  transform: translateY(var(--key-lip-h));
  transition:
    transform var(--dur-release) var(--ease-spring),
    box-shadow var(--dur-release) var(--ease-spring);
}
.form-key::after {
  z-index: -1;
  background: var(--face);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
}
.form-key:hover:not(:disabled):not(.on) {
  --face: #fff;
  --key-y: -1px;
  color: var(--ink);
}
.form-key.on {
  --face: linear-gradient(180deg, #fff 35%, color-mix(in srgb, var(--holo-lilac) 16%, #fff));
  --lip: var(--pearl-deep);
  --key-y: 2px;
  --key-lip-h: 1px;
  --lip-shadow: 0 2px 5px -2px rgba(var(--c-900-rgb), 0.2);
  color: var(--night);
}
.form-key:active:not(:disabled) {
  --key-y: 3px;
  --key-lip-h: 0px;
  --lip-shadow: 0 1px 2px -1px rgba(var(--c-900-rgb), 0.2);
  transition-duration: var(--dur-press);
  transition-timing-function: ease-out;
}
.form-key:active:not(:disabled)::before {
  transition-duration: var(--dur-press);
  transition-timing-function: ease-out;
}
.form-key:disabled {
  --face: var(--c-100);
  --lip: transparent;
  --key-y: 0px;
  --key-lip-h: 0px;
  --lip-shadow: none;
  color: var(--ink-3);
  cursor: default;
}
/* Fitted by height with bottom alignment so taller headwear and dragon horns are never cropped. */
.form-art {
  display: flex;
  align-items: flex-end;
  justify-content: center;
  height: clamp(36px, 5.6cqh, 48px);
  padding: 4px 6px 0;
  box-sizing: border-box;
  border-radius: var(--radius-s);
  background: var(--c-50);
  overflow: hidden;
  transition: background var(--dur-base);
}
.form-art img {
  display: block;
  width: auto;
  height: 100%;
  max-width: 100%;
  object-fit: contain;
  object-position: 50% 100%;
  filter: var(--contour);
  transition: transform var(--dur-base) var(--ease-out);
}
.form-key:hover:not(:disabled) .form-art img {
  transform: translateY(-2px);
}
.form-key.on .form-art {
  background: linear-gradient(115deg, color-mix(in srgb, var(--holo-pink) 48%, #fff), color-mix(in srgb, var(--holo-lilac) 56%, #fff) 45%,
    color-mix(in srgb, var(--holo-mint) 48%, #fff) 80%, color-mix(in srgb, var(--holo-cream) 54%, #fff));
}
.form-bridge {
  flex: none;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.form-arrow {
  color: var(--ink-3);
  transition: color var(--dur-base), transform var(--dur-base) var(--ease-out);
}
.form-arrow.on {
  color: var(--pearl-deep);
  transform: translateX(2px);
}
.form-timer {
  display: block;
  width: 20px;
  height: 3px;
  border-radius: 2px;
  background: var(--c-100);
  overflow: hidden;
}
.form-timer i {
  display: block;
  width: 100%;
  height: 100%;
  border-radius: inherit;
  background: var(--grad-pearl);
  transform: scaleX(0);
  transform-origin: 0 50%;
}
.form-timer.run i {
  animation: form-type var(--type-ms, 1900ms) linear forwards;
}
.hold .form-timer.run i,
.calm .form-timer.run i {
  animation-play-state: paused;
}
.form-timer.full i {
  transform: scaleX(1);
}
@keyframes form-type {
  to { transform: scaleX(1); }
}

.meter {
  flex: 0 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.sheet:not(.has-forms):not(.has-show) .meter {
  flex: 1;
  justify-content: flex-end;
}
/* The featured items: how many are found, the pool's odds for them, and each one a standee on the paper. */
.lead {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-bottom: 8px;
}
.l-head {
  display: flex;
  align-items: baseline;
  gap: 3px;
  margin: 0;
  min-width: 0;
  white-space: nowrap;
}
.l-head > em {
  margin-right: 5px;
  font: 800 var(--fs-body)/1 var(--font);
  font-style: normal;
  color: var(--ink);
}
.l-head > b {
  font: 800 18px/1 var(--font-latin);
  color: var(--ink);
}
.l-head > i {
  font: 800 var(--fs-label)/1 var(--font-latin);
  font-style: normal;
  color: var(--ink-3);
}
/* A showcased pool's one line: its UP tag and the time left, how many of its items are found, and its odds. Short of
 * room the odds go first (the odds sheet has them), then the words of the UP tag, then the word before the count. */
.sheet.has-show .lead {
  container: line / inline-size;
}
.l-head.line {
  align-items: center;
}
.l-head.line .up,
.l-head.line .time-left {
  margin: 0 8px 0 0;
}
@container line (max-width: 360px) {
  .l-head.line .odds {
    display: none;
  }
}
@container line (max-width: 290px) {
  .l-head.line .up {
    padding-right: 3px;
  }
  .l-head.line .up-word {
    display: none;
  }
}
@container line (max-width: 235px) {
  .l-head.line > em {
    display: none;
  }
}
/* The pool's own odds for a row, a quiet tag at its right end. */
.odds {
  align-self: center;
  margin-left: auto;
  padding: 3px 7px;
  border-radius: var(--radius-s);
  background: var(--c-50);
  color: var(--c-700);
  font: 800 var(--fs-caption)/1 var(--font);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.odds + .odds {
  margin-left: 4px;
}
.stands {
  display: flex;
  justify-content: space-between;
  gap: 6px;
}
.stand-key {
  position: relative;
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  padding: 0 0 6px;
  border: 0;
  background: none;
  color: var(--ink-2);
  font: inherit;
  cursor: pointer;
}
.stand-key:focus-visible {
  outline: 2px solid var(--c-500);
  outline-offset: 2px;
  border-radius: var(--radius-s);
}
.stand {
  position: relative;
  display: block;
  width: 62px;
  height: 62px;
}
.stand::before {
  content: "";
  position: absolute;
  left: 4%;
  right: 4%;
  bottom: 0;
  height: 12px;
  border-radius: 50%;
  background: var(--c-100);
  box-shadow: 0 2px 0 var(--c-200), 0 3px 6px -2px rgba(var(--shadow-rgb), 0.22);
  transition: background var(--dur-base), box-shadow var(--dur-base);
}
.stand-bust,
.stand-card {
  position: relative;
  z-index: 1;
  display: block;
  width: 100%;
  height: calc(100% - 3px);
  transition: transform var(--dur-base) var(--ease-out);
}
.stand-bust {
  filter: var(--contour) drop-shadow(0 2px 2px rgba(var(--shadow-rgb), 0.18));
}
.stand-card {
  width: 36px;
  margin: 0 auto;
  padding: 2px;
  box-sizing: border-box;
  border-radius: 5px;
  overflow: hidden;
}
.stand-card img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 3px;
}
.stand-key:hover:not(:disabled) .stand-bust,
.stand-key:hover:not(:disabled) .stand-card,
.stand-key.on .stand-bust,
.stand-key.on .stand-card {
  transform: translateY(-4px);
}
.stand-key.on .stand::before {
  background: var(--c-400);
  box-shadow: 0 2px 0 var(--c-500), 0 5px 10px -2px rgba(var(--c-500-rgb), 0.45);
}
.stand-name {
  max-width: 100%;
  display: flex;
  align-items: center;
  gap: 3px;
  font: 700 var(--fs-label)/1.3 var(--font);
  white-space: nowrap;
}
.stand-name > span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
.stand-name svg {
  flex: none;
  color: var(--ink-3);
}
.stand-key.done .stand-name svg {
  color: var(--c-600, var(--c-700));
}
.stand-key.on .stand-name {
  color: var(--ink);
  font-weight: 800;
}
/* The turn of the standee on show, under its name. */
.stand-key .tick {
  left: 22%;
  right: 22%;
  bottom: 0;
  background: var(--c-500);
}
.stands:has(:focus-visible) .tick {
  animation-play-state: paused;
}

@container panel (max-width: 820px) {
  .series {
    display: none;
  }
  .banner-stage {
    --stage-gap: 18px;
    padding-right: 18px;
  }
  .feature-hand {
    width: calc(var(--card-w) * 1.22);
  }
  .stand {
    width: 50px;
    height: 50px;
  }
  .peek {
    display: none;
  }
}
@container panel (max-width: 660px) {
  .banner-stage {
    flex-direction: column;
    align-items: center;
    gap: 18px;
    padding: 18px 16px 12px;
  }
  .feature-hand,
  .card-hand {
    --hero-h: 214px;
    --card-w: 150px;
  }
  .card-hand {
    align-self: center;
  }
  /* Over the full width, above the name: only its sides and its foot fade. */
  .feature-hand.spread {
    align-self: stretch;
    width: auto;
    min-height: 0;
    height: 250px;
  }
  .poster-spread {
    top: -18px;
    bottom: 0;
    left: -16px;
    right: -16px;
  }
  .poster-art {
    -webkit-mask-image: linear-gradient(90deg, transparent, #000 24px, #000 calc(100% - 24px), transparent);
    mask-image: linear-gradient(90deg, transparent, #000 24px, #000 calc(100% - 24px), transparent);
  }
  .poster-art img,
  .poster-art video {
    object-position: 50% 22%;
    -webkit-mask-image: linear-gradient(180deg, #000 70%, transparent);
    mask-image: linear-gradient(180deg, #000 70%, transparent);
  }
  .poster-art video {
    object-position: 50% 30%;
  }
  /* A smaller title, in the middle of the band's foot. */
  .poster-title {
    left: 50%;
    bottom: 8px;
    width: min(230px, 64%);
    translate: -50% 0;
  }
  .poster-title.veiled {
    translate: -50% 8px;
  }
  .wash {
    left: 50%;
    transform: translateX(-50%);
    height: 300px;
    bottom: auto;
  }
  .info {
    width: 100%;
  }
  .sheet {
    margin-left: 0;
  }
  .show-stage {
    flex: none;
    height: 150px;
  }
  .memories {
    display: none;
  }
}
/* A shorter panel: the forms and the standees give way before the last row slips under the action bar. */
@container panel (max-height: 700px) {
  .form-art {
    height: 36px;
  }
  .stand {
    width: 48px;
    height: 48px;
  }
  .feature-slot {
    min-height: 64px;
  }
}
@container panel (max-height: 600px) {
  .form-art {
    height: 38px;
  }
  .stand {
    width: 38px;
    height: 38px;
  }
  .lead {
    padding-bottom: 8px;
  }
}
</style>
