<script setup lang="ts">
// The layered desk pet from ASoul-Little-Bun (background, keyboard paw, mouse paw, click
// images) plus the emote bubble and the tap combo.
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { getCharacter, headAnchor, PET_BASE } from "../characters";
import { characterColor } from "../manifest";
import EmoteBubble from "./EmoteBubble.vue";
import ComboBubble from "./ComboBubble.vue";
import type { EmoteFrame } from "./EmotePlayer";
import type { ComboFrame } from "./TapCombo";

const props = withDefaults(
  defineProps<{
    character: string;
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
    emote: null, combo: null, minEmote: 44, maxEmote: Infinity, bubbleShift: () => ({ x: 0, y: 0 }), flipBubble: false,
  },
);

const assets = computed(() => getCharacter(props.character));
const s = computed(() => props.scale);
const u = (v: number) => `${v * s.value}px`;

const pulseDown = ref(false);
let pulseTimer: ReturnType<typeof setTimeout> | undefined;
onBeforeUnmount(() => clearTimeout(pulseTimer));
watch(
  () => props.pulse,
  () => {
    pulseDown.value = true;
    clearTimeout(pulseTimer);
    pulseTimer = setTimeout(() => (pulseDown.value = false), 70);
  },
);
const pressed = computed(() => props.keyDown || pulseDown.value);

const box = computed(() => ({ width: u(PET_BASE.width), height: u(PET_BASE.height) }));
const kbStyle = computed(() => {
  const k = PET_BASE.keyboard;
  return {
    left: u(k.x), top: u(k.y), width: u(k.size), height: u(k.size),
    transform: `translateY(${(pressed.value ? k.pressOffset : 0) * s.value}px)`,
  };
});
const mouseStyle = computed(() => {
  const m = PET_BASE.mouse;
  return {
    left: u(m.x), top: u(m.y), width: u(m.size), height: u(m.size),
    transform: `translate(${props.mouseDx * s.value}px, ${props.mouseDy * s.value}px)`,
  };
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
  <div class="pet" :class="{ 'smooth-mouse': smoothMouse }" :style="box">
    <div v-if="assets" class="art">
      <img class="layer bg" :src="scale <= 1 ? assets.bgSmall : scale <= 2 ? assets.bgMedium : assets.bg" :style="box" draggable="false" alt="" />
      <img class="layer kb" :class="{ down: pressed }" :src="assets.keyboard" :style="kbStyle" draggable="false" alt="" />
      <img class="layer mouse" :src="assets.mouse" :style="mouseStyle" draggable="false" alt="" />
      <span v-if="leftDown" class="layer mouse click" :style="[mouseStyle, clickMask(assets.leftClick), { backgroundColor: clickColor }]" />
      <span v-if="rightDown" class="layer mouse click" :style="[mouseStyle, clickMask(assets.rightClick), { backgroundColor: clickColor }]" />
    </div>
    <div v-else class="missing">?</div>

    <ComboBubble :frame="combo" :x="(PET_BASE.keyboard.x + 12) * s" :y="(PET_BASE.keyboard.y - 6) * s" :size="Math.max(14, 18 * s)" />
    <EmoteBubble :frame="emote" :anchor="bubbleAnchor" :size="emoteSize" :flip="flipBubble" />
  </div>
</template>

<style scoped>
.pet { position: relative; user-select: none; }
.art { position: absolute; inset: 0; }
.layer { position: absolute; pointer-events: none; }
.bg { left: 0; top: 0; }
.kb { transition: transform var(--dur-fast) var(--ease-pop); }
.kb.down { transition: transform 50ms var(--ease-out); }
.smooth-mouse .mouse { transition: transform 60ms linear; }
.click { mask-size: 100% 100%; mask-repeat: no-repeat; -webkit-mask-size: 100% 100%; -webkit-mask-repeat: no-repeat; }
.missing { color: var(--surface); opacity: 0.5; }
</style>
