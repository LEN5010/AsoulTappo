<script setup lang="ts">
// The guide's marks (src/guideShape.ts): a dashed pencil loop around the place named `data-guide="[target]"`, and with
// a [card], a dashed arrow from it. Drawn stroke by stroke once, through masks, so the dashes themselves never move.
// Placed at the top left of what holds it and drawn in its coordinates; it takes no mouse anywhere, so in the desk
// window the desktop under it stays clickable and the place keeps its own clicks.
import { computed, onBeforeUnmount, onMounted, ref, useId, watch } from "vue";
import { PLAIN, arrowPath, ellipseAround, loopPath, variantOf, type Arrow, type Box } from "../guideShape";

const props = defineProps<{
  target: string;
  /** Where to look for the place; the whole page by default. */
  scope?: HTMLElement | null;
  card?: HTMLElement | null;
  /** The card's name: its marks are drawn its own way (guideShape.ts variantOf). */
  seed?: string;
  /** The arrow crosses busy ground (the card stands over the pet): a low bow upwards and a small curl near its tail. */
  calm?: boolean;
  /** Changed when what holds the place moved in a way nothing here observes (a drag, the hit reporter's kick). */
  tick?: number;
}>();

const id = `guide-${useId().replace(/[^a-zA-Z0-9-]/g, "-")}`;
const svg = ref<SVGSVGElement>();
const shape = ref<{ loop: string; arrow: Arrow | null } | null>(null);

const rel = (r: DOMRect, o: DOMRect): Box => ({ x: r.left - o.left, y: r.top - o.top, w: r.width, h: r.height });
let place: Element | null = null;
const resize = new ResizeObserver(() => follow());
function measure() {
  const el = svg.value;
  if (!el) return;
  const found = (props.scope ?? document).querySelector(`[data-guide="${props.target}"]`);
  if (found !== place) {
    if (place) resize.unobserve(place);
    place = found;
    if (place) resize.observe(place);
  }
  const at = place?.getBoundingClientRect();
  if (!at || at.width < 1) {
    shape.value = null;
    return;
  }
  const o = el.getBoundingClientRect();
  const e = ellipseAround(rel(at, o));
  const card = props.card?.getBoundingClientRect();
  const own = props.seed ? variantOf(props.seed) : PLAIN;
  const v = props.calm
    ? { ...own, flip: false, bow: Math.min(own.bow, 0.6), curlR: Math.min(own.curlR, 0.13), curlAt: Math.min(own.curlAt, 0.25) }
    : own;
  const next = { loop: loopPath(e, v), arrow: card ? arrowPath(rel(card, o), e, v) : null };
  if (next.loop !== shape.value?.loop || next.arrow?.line !== shape.value?.arrow?.line) shape.value = next;
}

/** Measures for a moment after each change: transitions (the strip coming out, the pet gliding) settle in that time. */
const FOLLOW_MS = 600;
let until = 0;
let frame: number | null = null;
function follow() {
  until = performance.now() + FOLLOW_MS;
  if (frame !== null) return;
  const step = () => {
    measure();
    frame = performance.now() < until ? requestAnimationFrame(step) : null;
  };
  frame = requestAnimationFrame(step);
}

// The place may come and go (the strip under the pet does): looked up again whenever the page changes around it.
const changes = new MutationObserver(() => follow());
onMounted(() => {
  measure();
  follow();
  window.addEventListener("resize", follow);
  changes.observe(props.scope ?? document.body, { subtree: true, childList: true });
});
onBeforeUnmount(() => {
  window.removeEventListener("resize", follow);
  resize.disconnect();
  changes.disconnect();
  if (frame !== null) cancelAnimationFrame(frame);
});
watch(() => [props.tick, props.card, props.target, props.calm], follow);
watch(() => props.card, (card, was) => {
  if (was) resize.unobserve(was);
  if (card) resize.observe(card);
}, { immediate: true });

const masks = computed(() => ({ loop: `${id}-loop`, line: `${id}-line`, head: `${id}-head` }));
</script>

<template>
  <svg ref="svg" class="guide-mark" style="pointer-events: none" width="1" height="1" aria-hidden="true">
    <template v-if="shape">
      <defs>
        <mask :id="masks.loop" maskUnits="userSpaceOnUse" x="-10000" y="-10000" width="20000" height="20000">
          <path class="reveal" :d="shape.loop" pathLength="1" />
        </mask>
        <mask v-if="shape.arrow" :id="masks.line" maskUnits="userSpaceOnUse" x="-10000" y="-10000" width="20000" height="20000">
          <path class="reveal line" :d="shape.arrow.line" pathLength="1" />
        </mask>
        <mask v-if="shape.arrow" :id="masks.head" maskUnits="userSpaceOnUse" x="-10000" y="-10000" width="20000" height="20000">
          <path class="reveal head" :d="shape.arrow.head" pathLength="1" />
        </mask>
      </defs>
      <g :mask="`url(#${masks.loop})`">
        <path class="halo" :d="shape.loop" />
        <path class="stroke" :d="shape.loop" />
      </g>
      <template v-if="shape.arrow">
        <g :mask="`url(#${masks.line})`">
          <path class="halo" :d="shape.arrow.line" />
          <path class="stroke" :d="shape.arrow.line" />
        </g>
        <g :mask="`url(#${masks.head})`">
          <path class="halo solid" :d="shape.arrow.head" />
          <path class="stroke solid" :d="shape.arrow.head" />
        </g>
      </template>
    </template>
  </svg>
</template>

<style scoped>
.guide-mark {
  position: absolute;
  left: 0;
  top: 0;
  overflow: visible;
  z-index: 7;
}
.guide-mark * {
  pointer-events: none;
}
.stroke {
  fill: none;
  stroke: var(--c-500);
  stroke-width: 2.5px;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 7 6;
}
/* A white edge under each dash, so the marks read on any wallpaper and on the coral sidebar. */
.halo {
  fill: none;
  stroke: #fff;
  stroke-opacity: 0.9;
  stroke-width: 5.5px;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-dasharray: 7 6;
}
.stroke.solid,
.halo.solid {
  stroke-dasharray: none;
}
/* The mask's own stroke is wide and solid; drawing it on (pathLength 1) uncovers the dashes in stroke order. */
.reveal {
  fill: none;
  stroke: #fff;
  stroke-width: 12px;
  stroke-linecap: round;
  stroke-dasharray: 1 1;
  stroke-dashoffset: 1;
  animation: guide-draw var(--dur-slow) var(--ease-out) forwards;
}
.reveal.line {
  animation-delay: 220ms;
}
.reveal.head {
  animation-duration: var(--dur-fast);
  animation-delay: 520ms;
}
@keyframes guide-draw {
  to {
    stroke-dashoffset: 0;
  }
}
</style>
