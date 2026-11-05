<script setup lang="ts">
import { getCharacter } from "../characters";
import { characterColor, memberOf } from "../manifest";
import PetBust from "./PetBust.vue";
defineProps<{ name: string; owned?: boolean }>();
</script>

<template>
  <span class="skin-art" :class="{ locked: !owned }" :style="{ '--member': characterColor(memberOf(name)) }">
    <span class="serial" aria-hidden="true">A-SOUL · SKIN COLLECTION</span>
    <span class="orbit" aria-hidden="true"></span>
    <span class="edition" aria-hidden="true">山<br />海<br />经</span>
    <PetBust class="figure" :src="getCharacter(name)!.bg" />
    <span class="skin-seal" aria-hidden="true">山海经系列</span>
  </span>
</template>

<style scoped>
.skin-art { position: relative; display: block; aspect-ratio: 2 / 3; overflow: hidden; border-radius: var(--radius-m); background: color-mix(in oklab, var(--member) 12%, var(--surface)); box-shadow: inset 0 0 0 1px color-mix(in oklab, var(--member) 30%, var(--surface)); isolation: isolate; }
.skin-art::after { content: ''; position: absolute; inset: 6px; border: 1px solid color-mix(in oklab, var(--member) 32%, transparent); border-radius: 2px; pointer-events: none; }
.serial { position: absolute; left: 14px; top: 15px; color: var(--ink-2); font: 800 9px/1 var(--font-latin); letter-spacing: .12em; }
.orbit { position: absolute; width: 110%; aspect-ratio: 1; left: -5%; top: 17%; border: 1px solid color-mix(in oklab, var(--member) 30%, transparent); border-radius: 50%; }
.orbit::after { content: ''; position: absolute; inset: 12px; border: 1px dashed color-mix(in oklab, var(--member) 25%, transparent); border-radius: 50%; }
.edition { position: absolute; right: 12%; top: 17%; font: 800 clamp(28px, 5cqw, 48px)/1.2 var(--font); color: color-mix(in oklab, var(--member) 25%, var(--surface)); }
.figure { position: absolute; width: 100%; height: 83%; left: -5%; bottom: 5%; filter: var(--sticker-lg); transition: transform var(--dur-base) var(--ease-out); }
.locked .figure { filter: brightness(.82) var(--sticker-lg); }
.skin-seal { position: absolute; inset: auto 16px 13px; padding-top: 8px; border-top: 1px solid color-mix(in oklab, var(--member) 32%, transparent); text-align: center; color: var(--ink-2); font-size: var(--fs-caption); font-weight: 700; letter-spacing: .22em; }
</style>
