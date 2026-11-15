<script setup lang="ts">
// Over the own pet: a reminder (water, getting up, lunch, hello, bedtime) or a bubble of the tomato timer
// (src/stores/nudge.ts, src/stores/pomodoro.ts).
import { NUDGE_WIDTH, answerLunch, closeNudge, drankWater, nudge } from "../stores/nudge";
import { nextPomodoro } from "../stores/pomodoro";
import PetBubble from "./PetBubble.vue";

defineProps<{ shift: number; below: boolean }>();

/** The single key of the kinds that have one. */
const OK: Partial<Record<string, string>> = { move: "好", greet: "嗨", night: "晚安", rest: "好", back: "好" };
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
        <button v-else-if="nudge.kind === 'water'" type="button" class="ui-btn small primary" @click="drankWater">喝了</button>
        <template v-else-if="nudge.kind === 'again'">
          <button type="button" class="ui-btn small" @click="closeNudge">不了</button>
          <button type="button" class="ui-btn small primary" @click="nextPomodoro">再来一轮</button>
        </template>
        <button v-else type="button" class="ui-btn small primary" @click="closeNudge">{{ OK[nudge.kind] ?? "好" }}</button>
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
