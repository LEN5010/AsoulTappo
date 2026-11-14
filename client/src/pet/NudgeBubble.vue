<script setup lang="ts">
// Over the own pet: a reminder to drink water or get up, or the lunch question (src/stores/nudge.ts).
import { NUDGE_WIDTH, answerLunch, closeNudge, nudge } from "../stores/nudge";
import PetBubble from "./PetBubble.vue";

defineProps<{ shift: number; below: boolean }>();
</script>

<template>
  <PetBubble :open="!!nudge" :width="NUDGE_WIDTH" :shift="shift" :below="below">
    <div v-if="nudge" class="nudge" role="status">
      <p>{{ nudge.text }}</p>
      <div v-if="!nudge.reply" class="acts">
        <template v-if="nudge.kind === 'lunch'">
          <button type="button" class="ui-btn small" @click="answerLunch(false)">还没</button>
          <button type="button" class="ui-btn small primary" @click="answerLunch(true)">吃了</button>
        </template>
        <button v-else type="button" class="ui-btn small primary" @click="closeNudge">好</button>
      </div>
    </div>
  </PetBubble>
</template>

<style scoped>
/* One row: the line, then its keys on the right. */
.nudge { display: flex; align-items: center; gap: 8px; min-height: 28px; }
.nudge p { flex: 1; min-width: 0; margin: 0; font: 700 var(--fs-label)/1.4 var(--font); }
.acts { flex: none; display: flex; gap: 6px; }
</style>
