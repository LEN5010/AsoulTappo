<script setup lang="ts">
// The note behind the automatic-input bubble: on paper over the pet, what was found, what it changes and when it ends.
// Closing it is what puts the bubble away for the day (src/stores/autoHint.ts).
import { AUTO_NOTE_WIDTH } from "../stores/autoHint";
import PetBubble from "./PetBubble.vue";

defineProps<{ open: boolean; shift: number; below: boolean }>();
const emit = defineEmits<{ close: [] }>();

const LINES = [
  "识别到这份存档的敲击由连点器、脚本等软件自动发出。",
  "在此期间，你的碎片收益和存档不受影响，但联机房间里不显示你的敲击和动作。",
  "停用相关软件后，联机动作将在一段时间内自动恢复。",
];
</script>

<template>
  <PetBubble :open="open" :width="AUTO_NOTE_WIDTH" :shift="shift" :below="below">
    <article class="note" role="alert">
      <h2><span class="mark" aria-hidden="true">!</span>自动点击检测说明</h2>
      <p v-for="line in LINES" :key="line">{{ line }}</p>
      <button type="button" class="ui-btn small primary" @click="emit('close')">知道了</button>
    </article>
  </PetBubble>
</template>

<style scoped>
.note { display: flex; flex-direction: column; gap: 6px; padding: 4px 4px 2px; }
h2 { display: flex; align-items: center; gap: 8px; margin: 0 0 2px; font: 800 var(--fs-strong)/1.2 var(--font); color: var(--ink); }
.mark {
  flex: none; display: grid; place-items: center; width: 22px; height: 22px; border-radius: 50%;
  background: var(--c-500); color: var(--surface); font: 800 var(--fs-number)/1 var(--font-latin);
}
p { margin: 0; font: 500 var(--fs-body)/1.6 var(--font); color: var(--ink); }
.ui-btn { align-self: flex-end; margin-top: 2px; }
</style>
