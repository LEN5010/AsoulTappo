<script setup lang="ts">
// The layered desk pet (background, keyboard paw, mouse paw, click images) plus the emote bubble and the tap
// combo. A two-form skin lays its second picture over the first and shows it while the player keeps typing; a part of
// the second picture may move there, in frames stepped through over it.
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { usePageActive } from "../composables/usePageActive";
import { remoteMotion } from "../net/MotionFrames";
import { getCharacter, headAnchor, PET_BASE } from "../characters";
import { characterColor } from "../manifest";
import EmoteBubble from "./EmoteBubble.vue";
import ComboBubble from "./ComboBubble.vue";
import Icon from "../ui/Icon.vue";
import type { EmoteFrame } from "./EmotePlayer";
import type { ComboFrame } from "./TapCombo";
import { SkinForm } from "./SkinForm";

const props = withDefaults(
  defineProps<{
    character: string;
    motionId?: string;
    scale?: number;
    /** Local pet: keyboard layer pressed state (driven by global key hook). */
    keyDown?: boolean;
    /** Press edges on this device, including keys pressed while another key stays held. */
    formPress?: number;
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
    /** Increments when the player drank water after a reminder: a cup beside the head for a moment. */
    sip?: number;
    /** How much of the figure shows (settings.petOpacity on the desk); the bubbles beside it stay solid. */
    opacity?: number;
    /** smallest emote picture height in px (keeps remote bubbles readable) */
    minEmote?: number;
    /** largest emote picture height in px, for frames too short for a scaled-up bubble */
    maxEmote?: number;
    /** moves the bubble off the top of the head, px */
    bubbleShift?: { x: number; y: number };
    /** emote bubble grows to the left (pet near the right screen edge) */
    flipBubble?: boolean;
    /** A showcase holds a two-form skin in one of its forms; left out, presses decide (SkinForm.ts). */
    form?: boolean | null;
  }>(),
  {
    scale: 1, keyDown: false, pulse: 0, sip: 0, mouseDx: 0, mouseDy: 0, leftDown: false, rightDown: false,
    emote: null, combo: null, win: null, minEmote: 44, maxEmote: Infinity, bubbleShift: () => ({ x: 0, y: 0 }), flipBubble: false,
    form: null,
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

// ---- the second form of a two-form skin: the own pet times its presses, another member's pet its tap batches
const typedForm = ref(false);
const formOn = computed(() => (props.form ?? typedForm.value) && !!assets.value?.form);
let form: SkinForm | undefined;
watch(() => assets.value?.form, (has) => {
  form?.reset();
  form = has ? new SkinForm((on) => (typedForm.value = on)) : undefined;
}, { immediate: true });
onBeforeUnmount(() => form?.reset());
watch(() => props.formPress, (press) => {
  if (press !== undefined) form?.press(Date.now());
});
watch(() => props.pulse, () => {
  if (props.formPress === undefined) form?.press(Date.now());
});
const sized = (p: { bg: string; bgSmall: string; bgMedium: string }) =>
  (s.value <= 1 ? p.bgSmall : s.value <= 2 ? p.bgMedium : p.bg);
// The frames sit on the second picture, which is drawn at the canvas width from the bottom up.
const loop = computed(() => assets.value?.form?.loop);
const loopStyle = computed(() => {
  const l = loop.value;
  if (!l) return {};
  const k = (PET_BASE.width * s.value) / l.width;
  return {
    left: `${l.x * k}px`, bottom: `${(l.height - l.y - l.h) * k}px`, width: `${l.w * k}px`, height: `${l.h * k}px`,
    "--loop-steps": l.frames, "--loop-dur": `${l.frames * l.ms}ms`,
  };
});

// ---- the cup after a drink of water
const SIP_MS = 3200;
const sipShown = ref(0);
let sipTimer: ReturnType<typeof setTimeout> | undefined;
onBeforeUnmount(() => clearTimeout(sipTimer));
watch(() => props.sip, (n) => {
  sipShown.value = n;
  clearTimeout(sipTimer);
  sipTimer = setTimeout(() => (sipShown.value = 0), SIP_MS);
});

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
    <div v-if="assets" class="art" :style="opacity !== undefined && opacity < 1 ? { opacity } : undefined">
      <div class="still">
        <img class="layer bg" :class="{ under: formOn }" :src="sized(assets)" :style="{ width: box.width }" draggable="false" alt="" />
        <Transition :name="loop?.entrance === 'summon' ? 'loop-summon' : 'loop'">
          <span v-if="loop?.behind && formOn && active" class="layer loop" :style="loopStyle"><img :src="loop.src" draggable="false" alt="" /></span>
        </Transition>
        <img v-if="assets.form" class="layer bg form" :class="{ shown: formOn }" :src="sized(assets.form)" :style="{ width: box.width }" draggable="false" alt="" />
        <Transition :name="loop?.entrance === 'summon' ? 'loop-summon' : 'loop'">
          <span v-if="loop && !loop.behind && formOn && active" class="layer loop" :style="loopStyle"><img :src="loop.src" draggable="false" alt="" /></span>
        </Transition>
      </div>
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
    <span
      v-if="sipShown" :key="sipShown" class="sip"
      :style="{ left: `${(head.x + (flipBubble ? 30 : -30)) * s}px`, top: `${(head.y - 14) * s}px`, '--sip': `${Math.max(26, 34 * s)}px` }"
    >
      <Icon name="cup" :size="Math.round(Math.max(26, 34 * s) * 0.58)" />
    </span>
  </div>
</template>

<style scoped>
.pet { position: relative; user-select: none; }
.art { position: absolute; inset: 0; }
.layer { position: absolute; pointer-events: none; }
/* The pictures and the second form's moving part, without the paws: an outline put on the pet goes round this, so it
   runs round body and wings as one, and the paws moving never redraw it. */
.still { position: absolute; inset: 0; pointer-events: none; }
/* Width only, bottom-aligned: a picture taller than the canvas holds headwear above it and draws past the top. */
.bg { left: 0; bottom: 0; height: auto; }
/* The second form fades in over the first, which then hides; going back, the first shows before the fade out. */
.bg.under { visibility: hidden; transition: visibility 0s linear var(--dur-slow); }
.bg.form { opacity: 0; transition: opacity var(--dur-slow) var(--ease-out); }
.bg.form.shown { opacity: 1; }
/* The frames of the loop side by side in one picture, moved a frame at a time behind a window one frame wide.
   Only there while the second form shows, so nothing runs otherwise; it comes and goes with the same fade. */
.loop { overflow: hidden; }
.loop img { position: absolute; left: 0; top: 0; height: 100%; will-change: transform; animation: loop-steps var(--loop-dur) steps(var(--loop-steps)) infinite; }
@keyframes loop-steps {
  to { transform: translateX(-100%); }
}
.loop-enter-active, .loop-leave-active { transition: opacity var(--dur-slow) var(--ease-out); }
.loop-enter-from, .loop-leave-to { opacity: 0; }
/* A summoned loop spins up from a point, overbright, out of a flash of light, and folds back into one. */
.loop-summon-enter-active { animation: loop-summon 680ms var(--ease-out) both; }
.loop-summon-leave-active { animation: loop-dismiss 460ms var(--ease-in) both; }
.loop-summon-enter-active::after, .loop-summon-leave-active::after {
  content: ""; position: absolute; inset: 0; border-radius: 50%;
  background: radial-gradient(closest-side, rgb(255 248 226 / 0.95), rgb(255 208 120 / 0.6) 42%, transparent 74%);
}
.loop-summon-enter-active::after { animation: loop-flash-in 680ms ease-out both; }
.loop-summon-leave-active::after { animation: loop-flash-out 460ms ease-in both; }
@keyframes loop-summon {
  0% { opacity: 0; transform: scale(0.15) rotate(-150deg); filter: brightness(2.6); }
  50% { opacity: 1; transform: scale(1.1) rotate(8deg); filter: brightness(1.6); }
  100% { opacity: 1; transform: scale(1) rotate(0deg); filter: brightness(1); }
}
@keyframes loop-dismiss {
  0% { opacity: 1; transform: scale(1) rotate(0deg); filter: brightness(1); }
  30% { opacity: 1; transform: scale(1.08) rotate(-10deg); filter: brightness(1.7); }
  100% { opacity: 0; transform: scale(0.12) rotate(140deg); filter: brightness(2.8); }
}
@keyframes loop-flash-in {
  0% { opacity: 0; transform: scale(0.3); }
  25% { opacity: 1; transform: scale(0.9); }
  100% { opacity: 0; transform: scale(1.15); }
}
@keyframes loop-flash-out {
  0%, 25% { opacity: 0; transform: scale(1); }
  70% { opacity: 1; transform: scale(0.9); }
  100% { opacity: 0; transform: scale(0.6); }
}
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
/* A paper disc with the cup, popping up beside the head and drifting off. */
.sip {
  position: absolute;
  width: var(--sip);
  height: var(--sip);
  translate: -50% -50%;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--surface);
  color: var(--c-600);
  box-shadow: 0 2px 6px rgba(var(--shadow-rgb), 0.35);
  pointer-events: none;
  animation: sip-pop 3.2s var(--ease-out) both;
}
@keyframes sip-pop {
  0% { opacity: 0; scale: 0.4; }
  10% { opacity: 1; scale: 1.12; }
  18% { scale: 1; }
  80% { opacity: 1; translate: -50% -50%; }
  100% { opacity: 0; translate: -50% -110%; }
}
</style>
