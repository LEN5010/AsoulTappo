<script setup lang="ts">
// The layered desk pet from ASoul-Little-Bun (background, keyboard paw, mouse paw, click
// images) plus accessories on the head / monitor, the emote bubble and the tap combo.
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { getCharacter, headAnchor, PET_BASE } from "../characters";
import { getAccessory } from "../manifest";
import { assetUrl } from "../asset";
import { reducedMotion, skin } from "../stores/theme";
import EmoteBubble from "./EmoteBubble.vue";
import LikeBurst from "./LikeBurst.vue";
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
    head?: string | null;
    desk?: string | null;
    emote?: EmoteFrame | null;
    combo?: ComboFrame | null;
    /** smallest emote picture height in px (keeps remote bubbles readable) */
    minEmote?: number;
    /** emote bubble grows to the left (pet near the right screen edge) */
    flipBubble?: boolean;
  }>(),
  {
    scale: 1, keyDown: false, pulse: 0, mouseDx: 0, mouseDy: 0, leftDown: false, rightDown: false,
    head: null, desk: null, emote: null, combo: null, minEmote: 44, flipBubble: false,
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

// ---- accessories
const head = computed(() => headAnchor(props.character));
const headAcc = computed(() => getAccessory(props.head));
const deskAcc = computed(() => getAccessory(props.desk));
const headImg = computed(() => {
  const a = headAcc.value;
  if (!a) return "";
  if (a.kind === "rider" && props.mouseDx < -3 && a.left) return assetUrl(a.left);
  if (a.kind === "rider" && props.mouseDx > 3 && a.right) return assetUrl(a.right);
  return assetUrl(a.img);
});
const headStyle = computed(() => {
  const h = headAcc.value?.kind === "rider" ? 40 : 46;
  return {
    left: u(head.value.x - h / 2), top: u(head.value.y + 12 - h), width: u(h), height: u(h),
    transform: `translateY(${pressed.value ? 1.5 * s.value : 0}px)`,
  };
});
const deskStyle = computed(() => {
  const h = 54;
  const m = PET_BASE.monitor;
  return { left: u(m.x - h / 2), top: u(m.y + 3 - h), width: u(h), height: u(h) };
});

// ---- emote bubble / like / combo
const emoteSize = computed(() => Math.max(props.minEmote, 72 * s.value));
const bubbleAnchor = computed(() => ({
  x: (head.value.x + (props.flipBubble ? -20 : 20)) * s.value,
  y: (head.value.y + 16) * s.value,
}));
const likeOn = computed(() => !!skin.value.thumbup && !reducedMotion.value);
const bubbleFrame = computed(() => (props.emote?.key === "thumbup" && likeOn.value ? null : props.emote));
const likeBeat = computed(() => (props.emote?.key === "thumbup" && likeOn.value ? props.emote.beat : null));
</script>

<template>
  <div class="pet" :style="box">
    <template v-if="assets">
      <img class="layer bg" :src="assets.bg" :style="box" draggable="false" alt="" />
      <img v-if="deskAcc" class="layer acc" :src="assetUrl(deskAcc.img)" :style="deskStyle" draggable="false" alt="" />
      <img class="layer kb" :class="{ down: pressed }" :src="assets.keyboard" :style="kbStyle" draggable="false" alt="" />
      <img class="layer" :src="assets.mouse" :style="mouseStyle" draggable="false" alt="" />
      <img v-if="leftDown" class="layer" :src="assets.leftClick" :style="mouseStyle" draggable="false" alt="" />
      <img v-if="rightDown" class="layer" :src="assets.rightClick" :style="mouseStyle" draggable="false" alt="" />
      <img v-if="headAcc" class="layer acc head" :src="headImg" :style="headStyle" draggable="false" alt="" />
    </template>
    <div v-else class="missing">?</div>

    <ComboBubble :frame="combo" :x="(PET_BASE.keyboard.x + 12) * s" :y="(PET_BASE.keyboard.y - 6) * s" :size="Math.max(14, 18 * s)" />
    <EmoteBubble :frame="bubbleFrame" :anchor="bubbleAnchor" :size="emoteSize" :flip="flipBubble" />
    <LikeBurst :src="skin.thumbup" :beat="likeBeat" :size="PET_BASE.height * 1.15 * s" :x="head.x * s" :y="PET_BASE.height * 0.45 * s" />
  </div>
</template>

<style scoped>
.pet { position: relative; user-select: none; }
.layer { position: absolute; pointer-events: none; }
.bg { left: 0; top: 0; }
.acc { object-fit: contain; filter: drop-shadow(0 2px 2px rgba(0, 0, 0, 0.18)); }
.acc.head { transition: transform 120ms cubic-bezier(0.34, 1.8, 0.64, 1); }
.kb { transition: transform 140ms cubic-bezier(0.34, 1.8, 0.64, 1); }
.kb.down { transition: transform 50ms ease-out; }
.missing { color: #fff; opacity: 0.5; }
</style>
