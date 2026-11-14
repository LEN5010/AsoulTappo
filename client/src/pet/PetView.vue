<script setup lang="ts">
// The layered desk pet (background, keyboard paw, mouse paw, click images) plus the emote bubble and the tap
// combo.
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { usePageActive } from "../composables/usePageActive";
import { remoteMotion } from "../net/MotionFrames";
import { getCharacter, headAnchor, PET_BASE } from "../characters";
import { characterColor } from "../manifest";
import EmoteBubble from "./EmoteBubble.vue";
import ComboBubble from "./ComboBubble.vue";
import type { EmoteFrame } from "./EmotePlayer";
import type { ComboFrame } from "./TapCombo";

const props = withDefaults(
  defineProps<{
    character: string;
    motionId?: string;
    scale?: number;
    /** Local pet: keyboard layer pressed state (driven by global key hook). */
    keyDown?: boolean;
    /** Remote pet: increments on every tap batch -> short keyboard bounce. */
    pulse?: number;
    mouseDx?: number;
    mouseDy?: number;
    leftDown?: boolean;
    rightDown?: boolean;
    smoothMouse?: boolean;
    emote?: EmoteFrame | null;
    combo?: ComboFrame | null;
    /** Icon before the combo's number: a partner's combo counts taps, the own pet's counts shards. */
    comboIcon?: string;
    /** Shards a scratch card or a duel just paid, shown large beside the head. */
    win?: ComboFrame | null;
    /** smallest emote picture height in px (keeps remote bubbles readable) */
    minEmote?: number;
    /** largest emote picture height in px, for frames too short for a scaled-up bubble */
    maxEmote?: number;
    /** moves the bubble off the top of the head, px */
    bubbleShift?: { x: number; y: number };
    /** emote bubble grows to the left (pet near the right screen edge) */
    flipBubble?: boolean;
  }>(),
  {
    scale: 1, keyDown: false, pulse: 0, mouseDx: 0, mouseDy: 0, leftDown: false, rightDown: false,
    emote: null, combo: null, win: null, minEmote: 44, maxEmote: Infinity, bubbleShift: () => ({ x: 0, y: 0 }), flipBubble: false,
  },
);

const assets = computed(() => getCharacter(props.character));
const active = usePageActive();
const root = ref<HTMLElement>();
const inView = ref(false);
let visibility: IntersectionObserver | undefined;
let stopMotion: (() => void) | undefined;
onMounted(() => {
  visibility = new IntersectionObserver(([entry]) => { inView.value = !!entry?.isIntersecting; });
  if (root.value) visibility.observe(root.value);
});
// Another member's pet is drawn from the room's updates, straight onto its layers: each update sets where
// the mouse layer goes and the stylesheet glides it there, so nothing renders or runs between updates.
// Subscribed only while it can be seen, which is also what the room is asked to send (net/MotionFrames.ts).
watch([() => props.motionId, () => props.scale, assets, active, inView, root], () => {
  stopMotion?.(); stopMotion = undefined;
  const el = root.value;
  if (!props.motionId || !el || !active.value || !inView.value) return;
  const mouse = [...el.querySelectorAll<HTMLElement>(".mouse")];
  const keyboard = el.querySelector<HTMLElement>(".kb");
  const [left, right] = [el.querySelector<HTMLElement>(".click-left"), el.querySelector<HTMLElement>(".click-right")];
  const scale = props.scale;
  stopMotion = remoteMotion.subscribe(props.motionId, (pose) => {
    const at = `translate(${pose.dx * scale}px, ${pose.dy * scale}px)`;
    for (const layer of mouse) layer.style.transform = at;
    if (keyboard) {
      keyboard.style.transform = `translateY(${(pose.keyDown ? PET_BASE.keyboard.pressOffset : 0) * scale}px)`;
      // The quick way down, the springy way back up, as for the own pet (.kb.down below).
      keyboard.classList.toggle("down", pose.keyDown);
    }
    // Not drawn at all while the button is up: a masked layer that travels with the mouse costs a frame each step.
    if (left) left.style.display = pose.left ? "block" : "none";
    if (right) right.style.display = pose.right ? "block" : "none";
  });
}, { flush: "post" });
onBeforeUnmount(() => { stopMotion?.(); visibility?.disconnect(); });
const s = computed(() => props.scale);
const u = (v: number) => `${v * s.value}px`;

const pulseDown = ref(false);
let pulseTimer: ReturnType<typeof setTimeout> | undefined;
onBeforeUnmount(() => clearTimeout(pulseTimer));
watch(
  () => props.pulse,
  () => {
    if (!active.value) return;
    if (props.motionId) { remoteMotion.pulse(props.motionId); return; }
    pulseDown.value = true;
    clearTimeout(pulseTimer);
    pulseTimer = setTimeout(() => (pulseDown.value = false), 70);
  },
);
const pressed = computed(() => props.keyDown || pulseDown.value);

const box = computed(() => ({ width: u(PET_BASE.width), height: u(PET_BASE.height) }));
const kbStyle = computed(() => {
  const k = PET_BASE.keyboard;
  const box = { left: u(k.x), top: u(k.y), width: u(k.size), height: u(k.size) };
  // Another member's layers are moved by the motion painter above, never by a render.
  return props.motionId ? box : { ...box, transform: `translateY(${(pressed.value ? k.pressOffset : 0) * s.value}px)` };
});
const mouseStyle = computed(() => {
  const m = PET_BASE.mouse;
  const box = { left: u(m.x), top: u(m.y), width: u(m.size), height: u(m.size) };
  return props.motionId ? box : { ...box, transform: `translate(${props.mouseDx * s.value}px, ${props.mouseDy * s.value}px)` };
});
const clickColor = computed(() => characterColor(assets.value?.name ?? props.character));
const clickMask = (src: string) => ({ maskImage: `url("${src}")`, WebkitMaskImage: `url("${src}")` });

const head = computed(() => headAnchor(props.character));

// ---- emote bubble / combo
const emoteSize = computed(() => Math.min(props.maxEmote, Math.max(props.minEmote, 72 * s.value)));
const bubbleAnchor = computed(() => ({
  x: (head.value.x + (props.flipBubble ? -20 : 20)) * s.value + props.bubbleShift.x,
  y: (head.value.y + 16) * s.value + props.bubbleShift.y,
}));
</script>

<template>
  <div ref="root" class="pet" :class="{ 'smooth-mouse': smoothMouse, 'remote-motion': !!motionId }" :style="box">
    <div v-if="assets" class="art">
      <img class="layer bg" :src="scale <= 1 ? assets.bgSmall : scale <= 2 ? assets.bgMedium : assets.bg" :style="{ width: box.width }" draggable="false" alt="" />
      <img class="layer kb" :class="{ down: pressed }" :src="assets.keyboard" :style="kbStyle" draggable="false" alt="" />
      <img class="layer mouse" :src="assets.mouse" :style="mouseStyle" draggable="false" alt="" />
      <span v-if="motionId || leftDown" class="layer mouse click" :class="{ 'click-left': motionId }" :style="[mouseStyle, clickMask(assets.leftClick), { backgroundColor: clickColor }]" />
      <span v-if="motionId || rightDown" class="layer mouse click" :class="{ 'click-right': motionId }" :style="[mouseStyle, clickMask(assets.rightClick), { backgroundColor: clickColor }]" />
    </div>
    <div v-else class="missing">?</div>

    <ComboBubble :frame="combo" :icon="comboIcon" :x="(PET_BASE.keyboard.x + 12) * s" :y="(PET_BASE.keyboard.y - 6) * s" :size="Math.max(14, 18 * s)" />
    <ComboBubble
      :frame="win" :icon="win?.icon ?? 'shard'" :x="(head.x + (flipBubble ? 34 : -34)) * s" :y="(head.y + 8) * s" :size="Math.max(20, 26 * s)"
    />
    <EmoteBubble :frame="emote" :anchor="bubbleAnchor" :size="emoteSize" :flip="flipBubble" />
  </div>
</template>

<style scoped>
.pet { position: relative; user-select: none; }
.art { position: absolute; inset: 0; }
.layer { position: absolute; pointer-events: none; }
/* Width only, bottom-aligned: a picture taller than the canvas holds headwear above it and draws past the top. */
.bg { left: 0; bottom: 0; height: auto; }
/* The two paws are layers of their own: moving one changes where its layer is put, and nothing is painted
   again. Without this every step of a paw repaints the tiles under the pet. */
.kb, .mouse { will-change: transform; }
.kb { transition: transform var(--dur-fast) var(--ease-pop); }
.kb.down { transition: transform 50ms var(--ease-out); }
.smooth-mouse .mouse { transition: transform 60ms linear; }
/* Updates come every 100ms (net/MotionSender.ts): the layer takes that long to reach each one. */
.remote-motion .mouse { transition: transform 100ms linear; }
.remote-motion .click-left, .remote-motion .click-right { display: none; }
.click { mask-size: 100% 100%; mask-repeat: no-repeat; -webkit-mask-size: 100% 100%; -webkit-mask-repeat: no-repeat; }
.missing { color: var(--surface); opacity: 0.5; }
</style>
