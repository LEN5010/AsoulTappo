<script setup lang="ts">
import { EMOTES } from "../emotes";
defineProps<{ disabledHint?: string }>();
const emit = defineEmits<{ pick: [key: string] }>();
</script>

<template>
  <div class="emotes" :title="disabledHint">
    <button v-for="e in EMOTES" :key="e.key" type="button" :title="e.label" @click="emit('pick', e.key)">{{ e.glyph }}</button>
  </div>
</template>

<style scoped>
.emotes { display: flex; flex-wrap: wrap; gap: 4px; }
button { font-size: 20px; width: 34px; height: 34px; border-radius: 8px; border: 1px solid #ddd; background: #fff; cursor: pointer; padding: 0; }
button:hover { background: #fff0f5; border-color: #ff9ec0; }
button:active { transform: scale(0.92); }
</style>
