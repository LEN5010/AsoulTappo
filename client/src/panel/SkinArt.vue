<script setup lang="ts">
import { getCharacter, skinSeries } from "../characters";
import { characterColor, memberOf } from "../manifest";
import PetBust from "./PetBust.vue";
defineProps<{ name: string; owned?: boolean; detail?: boolean }>();
</script>

<template>
  <span class="skin-art" :class="{ locked: !owned }" :style="{ '--member': characterColor(memberOf(name)) }">
    <span class="serial" aria-hidden="true">A-SOUL · SKIN COLLECTION</span>
    <span class="orbit" aria-hidden="true"></span>
    <span class="edition" aria-hidden="true">{{ skinSeries(name) }}</span>
    <PetBust class="figure" :src="getCharacter(name)!.bg" :detail="detail" />
    <span class="skin-seal" aria-hidden="true">{{ memberOf(name) }}</span>
  </span>
</template>

<style scoped>
.skin-art { position: relative; display: block; aspect-ratio: 4 / 5; overflow: hidden; border-radius: var(--radius-m); background: color-mix(in oklab, var(--member) 9%, var(--surface)); isolation: isolate; }
.serial { position: absolute; left: 16px; top: 16px; color: var(--ink-3); font: 800 9px/1 var(--font-latin); letter-spacing: .12em; }
.edition { position: absolute; left: 16px; top: 34px; font: 800 clamp(17px, 2.4cqw, 23px)/1.3 var(--font); color: var(--ink); }
.orbit { position: absolute; width: 80%; aspect-ratio: 1; left: 10%; bottom: 14%; border-radius: 50%; background: color-mix(in oklab, var(--member) 10%, var(--surface)); }
.figure { position: absolute; width: 88%; height: 58%; left: 6%; bottom: 16%; filter: drop-shadow(0 4px 3px rgba(var(--ink-rgb), .12)); transition: transform var(--dur-base) var(--ease-out); }
.skin-seal { position: absolute; inset: auto 16px 14px; padding-top: 9px; border-top: 1px solid color-mix(in oklab, var(--member) 24%, transparent); color: var(--ink-2); font-size: var(--fs-label); font-weight: 700; letter-spacing: .12em; }
</style>
