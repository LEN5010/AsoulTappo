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
    <CharacterAvatar v-if="item.kind === 'character'" :character="item.ref" :size="size * 0.92" />
    <img
      v-else :src="src" :alt="item.name" loading="lazy" draggable="false"
      :style="{ objectFit: fit }"
    />
  </span>
</template>

<style scoped>
.art {
  display: grid;
  place-items: center;
  overflow: hidden;
  flex: none;
}
.art img {
  width: 100%;
  height: 100%;
  display: block;
  box-sizing: border-box;
}
.art.card img {
  object-position: 50% 18%;
}
.art.emote img {
  filter: var(--contour);
}
.art.locked img,
.art.locked :deep(.face) {
  filter: grayscale(1) opacity(0.6);
}
.art.locked:hover img,
.art.locked:hover :deep(.face) {
  filter: none;
}
.art.emote.locked:hover img {
  filter: var(--contour);
}
</style>
