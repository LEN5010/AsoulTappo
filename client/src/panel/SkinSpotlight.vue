<script setup lang="ts">
import type { Drop } from "../net/api";
import RevealSpotlight from "./RevealSpotlight.vue";
defineProps<{ drop: Drop; settled: boolean }>();
defineEmits<{ done: [] }>();
</script>

<template>
  <RevealSpotlight :drop="drop" :settled="settled" @done="$emit('done')" />
</template>
