<script setup lang="ts">
// The guide's cards in the desk window (src/guide.ts), inside the own pet's actor: the card beside the pet (or over
// its head), the loop and the arrow around a key on the strip. Covers the actor without taking the mouse; only the card
// does.
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { agreed } from "../legal/consent";
import { GUIDE_TARGET, GUIDE_TEXT, deskCard, type Card } from "../guide";
import { settings } from "../stores/settings";
import { deskCardShown, finishCard, guideLink, guideRun, watchPlaceClicks } from "../stores/guide";
import GuideCard from "../ui/GuideCard.vue";
import GuideMark from "../ui/GuideMark.vue";
import { variantOf } from "../guideShape";

const props = defineProps<{
  /** Something with a better claim is over the pet. */
  held: boolean;
  /** The end of a tap cooldown (ms), whose bubble holds the spot too. */
  cooldown: number;
  /** Where the card goes so it stays on screen (pet/duelPick.ts bubblePlacement). */
  shift: number;
  below: boolean;
  /** The desk page, where the places are looked for. */
  scope: HTMLElement | null;
  tick: number;
}>();

const root = ref<HTMLElement>();
const card = ref<InstanceType<typeof GuideCard>>();
const cardEl = computed(() => (card.value?.$el as HTMLElement | undefined) ?? null);

// The places drawn in this window now (not the panel's, which the browser preview draws in the same page).
const targets = ref<ReadonlySet<string>>(new Set());
function look() {
  const found = new Set<string>();
  props.scope?.querySelectorAll<HTMLElement>("[data-guide]").forEach((el) => {
    if (!el.closest(".panel")) found.add(el.dataset.guide!);
  });
  const same = found.size === targets.value.size && [...found].every((t) => targets.value.has(t));
  if (!same) targets.value = found;
}
let watcher: MutationObserver | undefined;

// The clock the cooldown is read against, moved on when it ends.
const now = ref(Date.now());
let cooldownTimer: ReturnType<typeof setTimeout> | undefined;
function tickAt(at: number) {
  clearTimeout(cooldownTimer);
  const left = at - Date.now();
  if (left > 0) cooldownTimer = setTimeout(() => { now.value = Date.now(); }, left + 50);
}

const shown = computed<Card | null>(() => deskCard(settings.guide, {
  agreed: agreed.value,
  busy: props.held || props.cooldown > now.value,
  panelBusy: guideLink.panelBusy,
  panelVisible: guideLink.panelVisible,
  tapped: guideRun.tapped,
  targets: targets.value,
}));
watch(shown, (c) => { deskCardShown.value = c; }, { immediate: true });
const target = computed(() => (shown.value ? GUIDE_TARGET[shown.value] : null));

// A card stands a little above its key, beside the pet on the key's side; where the screen ends on that side, next to
// the key towards the pet's middle, over the desk under the pet's face for a moment. Either way the arrow to it stays
// short. Over the head (the anchor) only until the key is measured.
/** The card's size before it is drawn (ui/GuideCard.vue at its widest). */
const CARD_GUESS = { w: 250, h: 72 };
const EDGE = 8;
/** The card's top left from the anchor over the head, when it stands beside the pet; null over the head. */
const side = ref<{ x: number; y: number } | null>(null);
/** The card stands over the pet's lower part (no room beside it): the arrow crosses the pet and stays calm. */
const overPet = ref(false);
function placeCard() {
  const t = target.value;
  const box = root.value?.getBoundingClientRect();
  const place = t ? props.scope?.querySelector<HTMLElement>(`[data-guide="${t}"]`) : null;
  const at = place?.getBoundingClientRect();
  if (!box || !at || at.width < 1) {
    side.value = null;
    return;
  }
  const w = cardEl.value?.offsetWidth || CARD_GUESS.w;
  const h = cardEl.value?.offsetHeight || CARD_GUESS.h;
  const keyLeft = at.left + at.width / 2 < box.left + box.width / 2;
  let x: number;
  let y: number;
  // Room for the arrow, its own for each card (guideShape.ts variantOf).
  const { room, rise } = variantOf(shown.value ?? "");
  const besideX = keyLeft ? Math.min(box.left, at.left) - room - w : Math.max(box.right, at.right) + room;
  overPet.value = !(besideX >= EDGE && besideX + w <= window.innerWidth - EDGE);
  if (!overPet.value) {
    x = besideX;
  } else {
    x = keyLeft ? at.right + room - 12 : at.left - room + 12 - w;
  }
  // Over the pet the card sits low, close over the strip, so the arrow runs along the desk rather than the face.
  y = at.top - h - (overPet.value ? 16 : rise);
  x = Math.max(EDGE, Math.min(window.innerWidth - EDGE - w, x));
  y = Math.max(EDGE, Math.min(window.innerHeight - EDGE - h, y));
  const next = { x: Math.round(x - (box.left + box.width / 2)), y: Math.round(y - box.top) };
  if (next.x !== side.value?.x || next.y !== side.value?.y) side.value = next;
}
/** Placed again for a moment after each change: the strip slides out, the pet glides. */
let placeUntil = 0;
let placeFrame: number | null = null;
function followCard() {
  placeCard();
  placeUntil = performance.now() + 600;
  if (placeFrame !== null) return;
  const step = () => {
    placeCard();
    placeFrame = performance.now() < placeUntil ? requestAnimationFrame(step) : null;
  };
  placeFrame = requestAnimationFrame(step);
}
watch(target, placeCard);
watch(() => [props.tick, cardEl.value], followCard, { flush: "post" });

function ok() {
  if (shown.value) finishCard(shown.value);
}

/** Using the circled place answers its card. */
let stopClicks: (() => void) | undefined;

watch(() => props.scope, (scope) => {
  watcher?.disconnect();
  if (!scope) return;
  watcher ??= new MutationObserver(look);
  watcher.observe(scope, { subtree: true, childList: true, attributes: true, attributeFilter: ["data-guide"] });
  look();
}, { flush: "post" });

onMounted(() => {
  look();
  stopClicks = watchPlaceClicks((place) => {
    if (shown.value && GUIDE_TARGET[shown.value] === place) finishCard(shown.value);
  });
  window.addEventListener("resize", followCard);
});
onBeforeUnmount(() => {
  watcher?.disconnect();
  clearTimeout(cooldownTimer);
  stopClicks?.();
  window.removeEventListener("resize", followCard);
  if (placeFrame !== null) cancelAnimationFrame(placeFrame);
  deskCardShown.value = null;
});
watch(() => props.cooldown, tickAt, { immediate: true });
</script>

<template>
  <div ref="root" class="desk-guide">
    <GuideMark
      v-if="shown && target" :key="shown" :target="target" :scope="scope" :card="cardEl" :seed="shown" :calm="overPet" :tick="tick"
    />
    <div class="anchor" :class="{ below: below && !side }">
      <Transition name="pop">
        <GuideCard
          v-if="shown" ref="card" :key="shown" :text="GUIDE_TEXT[shown]" :class="{ side: !!side }"
          :style="side ? { left: `${side.x}px`, top: `${side.y}px` } : { '--shift': `${shift}px` }"
          @ok="ok"
        />
      </Transition>
    </div>
  </div>
</template>

<style scoped>
.desk-guide {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 8;
}
/* Over the marks: the arrow starts under the card. */
.anchor { position: absolute; left: 50%; top: 0; width: 0; height: 0; z-index: 8; }
.anchor.below { top: 100%; }
.guide-card {
  position: absolute;
  left: 0;
  bottom: 8px;
  transform: translateX(calc(-50% + var(--shift)));
  pointer-events: auto;
}
.below .guide-card { bottom: auto; top: 8px; }
.guide-card.side { bottom: auto; transform: none; }
.pop-enter-active { transition: opacity var(--dur-fast), scale var(--dur-fast) var(--ease-pop); }
.pop-enter-from { opacity: 0; scale: 0.9; }
.pop-leave-active { transition: opacity var(--dur-base) var(--ease-in); }
.pop-leave-to { opacity: 0; }
</style>
