<script setup lang="ts">
import { computed } from "vue";
import type { Item } from "../items";
import { assetUrl } from "../asset";
import CharacterAvatar from "./CharacterAvatar.vue";

const props = withDefaults(defineProps<{ item: Item; size?: number; locked?: boolean }>(), { size: 84, locked: false });
const src = computed(() => assetUrl(props.item.art));
const fit = computed(() => (props.item.kind === "card" || props.item.kind === "theme" ? "cover" : "contain"));
</script>

<template>
  <span class="art" :class="[item.kind, { locked }]" :style="{ width: `${size}px`, height: `${size}px` }">
    <CharacterAvatar v-if="item.kind === 'character'" :character="item.ref" :size="size * 0.92" :round="false" />
    <!-- rectangular art turns into a solid block when blacked out, so locked cards / themes show an outline -->
    <span v-else-if="locked && (item.kind === 'card' || item.kind === 'theme')" class="back" :class="item.kind">?</span>
    <img
      v-else :src="src" :alt="locked ? '' : item.name" loading="lazy" draggable="false"
      :style="{ objectFit: fit }"
    />
  </span>
</template>

<style scoped>
.art { display: grid; place-items: center; overflow: hidden; flex: none; }
.art img { width: 100%; height: 100%; display: block; box-sizing: border-box; }
.art.card img { object-position: 50% 18%; border-radius: var(--r-m); }
.art.theme img { border-radius: var(--r-m); }
.art.locked img, .art.locked :deep(.face) { filter: brightness(0) saturate(0); opacity: 0.16; }
.back { display: grid; place-items: center; box-sizing: border-box; border: 1.5px dashed var(--line-2); border-radius: var(--r-m); color: var(--ink-3); font-size: 18px; font-weight: 700; }
.back.card { width: 62%; height: 88%; }
.back.theme { width: 86%; height: 60%; }
</style>
