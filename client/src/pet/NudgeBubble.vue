<script setup lang="ts">
// Over the own pet: a reminder (the player's own list, lunch, hello, bedtime), a bubble of the tomato timer or a todo that
// came due (src/stores/nudge.ts, src/stores/pomodoro.ts, src/stores/todo.ts).
import { NUDGE_WIDTH, answerLunch, closeNudge, drankWater, nudge } from "../stores/nudge";
import { nextPomodoro } from "../stores/pomodoro";
import { finishTodo, laterTodo } from "../stores/todo";
import PetBubble from "./PetBubble.vue";

defineProps<{ shift: number; below: boolean }>();
/** `todos`: the key of a bubble for several todos opens the todos' window. */
const emit = defineEmits<{ todos: [] }>();
function openTodos() {
  closeNudge();
  emit("todos");
}

/** The single key of the kinds that have one. */
const OK: Partial<Record<string, string>> = { greet: "嗨", night: "晚安", rest: "好", back: "好" };
</script>

<template>
  <PetBubble :open="!!nudge" :width="NUDGE_WIDTH" :shift="shift" :below="below">
    <div v-if="nudge" class="nudge" role="status">
      <p :class="{ title: nudge.kind === 'todo' && !nudge.reply }">{{ nudge.text }}</p>
      <div v-if="!nudge.reply" class="acts">
        <template v-if="nudge.kind === 'lunch'">
          <button type="button" class="ui-btn small" @click="answerLunch(false)">还没</button>
          <button type="button" class="ui-btn small primary" @click="answerLunch(true)">吃了</button>
        </template>
        <template v-else-if="nudge.kind === 'todo' && nudge.todo">
          <button type="button" class="ui-btn small" @click="laterTodo(nudge.todo)">稍后</button>
          <button type="button" class="ui-btn small primary" @click="finishTodo(nudge.todo)">完成</button>
        </template>
        <button v-else-if="nudge.kind === 'todos'" type="button" class="ui-btn small primary" @click="openTodos">看看</button>
        <button v-else-if="nudge.kind === 'tip' && nudge.tip === 'water'" type="button" class="ui-btn small primary" @click="drankWater">喝了</button>
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
/* A todo's own title can be long: two lines at most. */
.nudge p.title { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; overflow-wrap: anywhere; }
</style>
