<script setup lang="ts">
import { computed } from "vue";
import { getDecor } from "../manifest";
import { assetUrl } from "../asset";

const props = defineProps<{ nick: string; badge?: string | null; width: number }>();
const badgeImg = computed(() => assetUrl(getDecor(props.badge)?.img));
</script>

<template>
  <div class="pill" :style="{ maxWidth: `${width}px` }">
    <img v-if="badgeImg" :src="badgeImg" alt="" draggable="false" />
    <span>{{ nick }}</span>
  </div>
</template>

<style scoped>
.pill {
  display: flex; align-items: center; justify-content: center; gap: 4px; min-width: 64px; height: 26px; margin-top: -4px; padding: 0 12px; box-sizing: border-box;
  border-radius: 999px; background: rgba(255, 252, 249, 0.95); box-shadow: 0 3px 10px rgba(50, 20, 30, 0.2);
  font-family: var(--font); font-size: 12px; font-weight: 700; color: var(--ink);
}
.pill span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pill img { height: 18px; width: auto; }
</style>
