<script setup lang="ts">
import type { Drop } from "../net/api";
import type { ManifestCard } from "../manifest";
import RevealSpotlight from "./RevealSpotlight.vue";
defineProps<{ drop: Drop; card: ManifestCard; art: string; settled: boolean }>();
defineEmits<{ done: [] }>();
</script>

<template>
  <RevealSpotlight :drop="drop" :settled="settled" :card="card" :art="art" @done="$emit('done')" />
</template>
