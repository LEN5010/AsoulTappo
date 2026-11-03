<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { getCharacter, PET_BASE } from "../characters";
import { emoteView } from "../emotes";
import { characterColor } from "../manifest";
import { toHttpBase } from "../net/protocol";
import { settings } from "../stores/settings";
import { reducedMotion, skin } from "../stores/theme";

export interface Burst {
  key: number;
  text: string;
}

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
    emote?: { key: number; name: string } | null;
    bursts?: Burst[];
    label?: string;
    draggable?: boolean;
  }>(),
  { scale: 1, keyDown: false, pulse: 0, mouseDx: 0, mouseDy: 0, leftDown: false, rightDown: false, emote: null, bursts: () => [], label: "", draggable: false },
);

const assets = computed(() => getCharacter(props.character));
const s = computed(() => props.scale);
const accent = computed(() => characterColor(props.character));
const emoteShown = computed(() =>
  props.emote
    ? emoteView(props.emote.name, {
        serverBase: toHttpBase(settings.serverUrl),
        thumbup: skin.value.thumbup,
        reducedMotion: reducedMotion.value,
        appBase: import.meta.env.BASE_URL,
      })
    : null,
);

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

const box = computed(() => ({ width: `${PET_BASE.width * s.value}px`, height: `${PET_BASE.height * s.value}px` }));
const kbStyle = computed(() => {
  const k = PET_BASE.keyboard;
  return {
    left: `${k.x * s.value}px`,
    top: `${k.y * s.value}px`,
    transform: `translateY(${(pressed.value ? k.pressOffset : 0) * s.value}px)`,
    width: `${k.size * s.value}px`,
    height: `${k.size * s.value}px`,
  };
});
const mouseStyle = computed(() => {
  const m = PET_BASE.mouse;
  return {
    left: `${m.x * s.value}px`,
    top: `${m.y * s.value}px`,
    transform: `translate(${props.mouseDx * s.value}px, ${props.mouseDy * s.value}px)`,
    width: `${m.size * s.value}px`,
    height: `${m.size * s.value}px`,
  };
});
</script>

<template>
  <div class="pet" :data-tauri-drag-region="draggable ? '' : undefined">
    <div class="canvas" :style="box" :data-tauri-drag-region="draggable ? '' : undefined">
      <template v-if="assets">
        <img class="layer" :src="assets.bg" :style="box" draggable="false" />
        <img class="layer kb" :class="{ down: pressed }" :src="assets.keyboard" :style="kbStyle" draggable="false" />
        <img class="layer" :src="assets.mouse" :style="mouseStyle" draggable="false" />
        <img v-if="leftDown" class="layer" :src="assets.leftClick" :style="mouseStyle" draggable="false" />
        <img v-if="rightDown" class="layer" :src="assets.rightClick" :style="mouseStyle" draggable="false" />
      </template>
      <div v-else class="missing">?</div>

      <transition-group name="burst" tag="div" class="bursts">
        <span v-for="b in bursts" :key="b.key" class="burst" :style="{ fontSize: `${14 * Math.max(0.8, s * 1.4)}px` }">{{ b.text }}</span>
      </transition-group>
      <transition name="emote">
        <span v-if="emote && emoteShown" :key="emote.key" class="emote" :style="{ fontSize: `${28 * Math.max(0.7, s * 1.5)}px` }">
          <img v-if="emoteShown.img" :src="emoteShown.img" :style="{ height: `${40 * Math.max(0.7, s * 1.5)}px` }" alt="" draggable="false" />
          <template v-else>{{ emoteShown.text }}</template>
        </span>
      </transition>
    </div>
    <div v-if="label" class="label" :style="{ maxWidth: `${PET_BASE.width * s}px`, borderColor: accent, boxShadow: `0 0 0 1px ${accent}55` }">{{ label }}</div>
  </div>
</template>

<style scoped>
.pet { display: inline-flex; flex-direction: column; align-items: center; user-select: none; }
.canvas { position: relative; }
.layer { position: absolute; pointer-events: none; image-rendering: auto; }
/* bg is the first layer and fills the canvas */
.layer:first-child { left: 0; top: 0; }
.kb { transition: transform 140ms cubic-bezier(0.34, 1.8, 0.64, 1); }
.kb.down { transition: transform 50ms ease-out; }
.missing { color: #fff; opacity: 0.5; }
.label {
  margin-top: 2px; padding: 1px 6px; border-radius: 8px; font-size: 11px; line-height: 14px;
  color: #fff; background: rgba(20, 16, 24, 0.6); border: 1px solid transparent; backdrop-filter: blur(4px); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  pointer-events: none;
}
.bursts { position: absolute; left: 0; right: 0; top: 0; height: 100%; pointer-events: none; }
.burst {
  position: absolute; left: 50%; top: 30%; transform: translateX(-50%); font-weight: 800; color: var(--accent, #ff6b9d);
  text-shadow: 0 0 3px #fff, 0 0 3px #fff, 0 1px 4px rgba(0, 0, 0, 0.5);
}
.burst-enter-from { opacity: 0; transform: translate(-50%, 10px) scale(0.6); }
.burst-enter-active { transition: all 150ms ease-out; }
.burst-leave-active { transition: all 700ms ease-out; }
.burst-leave-to { opacity: 0; transform: translate(-50%, -34px) scale(1.1); }
.emote img { display: block; width: auto; max-width: 120px; }
.emote { position: absolute; left: 50%; top: -6%; transform: translateX(-50%); pointer-events: none; filter: drop-shadow(0 2px 3px rgba(0,0,0,.4)); }
.emote-enter-from { opacity: 0; transform: translate(-50%, 14px) scale(0.4); }
.emote-enter-active { transition: all 220ms cubic-bezier(0.34, 1.8, 0.64, 1); }
.emote-leave-active { transition: all 400ms ease-in; }
.emote-leave-to { opacity: 0; transform: translate(-50%, -20px); }
</style>
