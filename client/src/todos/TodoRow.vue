<script setup lang="ts">
// One todo of the todos' window: the round tick, the title (a click edits it in place: Enter or a click elsewhere
// keeps it, Esc drops it, an empty one is not kept), and its time under it, which opens the time picker. The delete
// key and, for an untimed todo, the time key show on hover.
import { computed, nextTick, ref } from "vue";
import { TITLE_MAX, isOverdue, whenText, type Todo } from "../todo";
import { editTitle } from "../stores/todo";
import Icon from "../ui/Icon.vue";

const props = defineProps<{ todo: Todo; now: number; ticking?: boolean; picking?: boolean }>();
const emit = defineEmits<{ tick: []; remove: []; when: []; clearWhen: [] }>();

const done = computed(() => props.todo.doneAt != null);
const late = computed(() => isOverdue(props.todo, props.now));

const editing = ref(false);
const draft = ref("");
const box = ref<HTMLInputElement>();
async function edit() {
  if (done.value) return;
  draft.value = props.todo.title;
  editing.value = true;
  await nextTick();
  const input = box.value;
  if (!input) return;
  input.focus();
  input.setSelectionRange(input.value.length, input.value.length);
}
function save() {
  if (!editing.value) return;
  editing.value = false;
  if (draft.value.trim() && draft.value !== props.todo.title) editTitle(props.todo.id, draft.value);
}
function cancel() {
  editing.value = false;
}
function onEnter(e: KeyboardEvent) {
  // Enter that confirms an input method's word is not the save.
  if (e.isComposing || e.keyCode === 229) return;
  save();
}
</script>

<template>
  <li class="row" :class="{ ticking, done, picking }">
    <button
      type="button" class="tick" :aria-pressed="done || ticking" :aria-label="`完成 ${todo.title}`" @click="emit('tick')"
    >
      <Icon name="check" :size="11" />
    </button>
    <span class="text">
      <input
        v-if="editing" ref="box" v-model="draft" class="name-box" type="text" :maxlength="TITLE_MAX" aria-label="待办"
        @keydown.enter="onEnter" @keydown.esc.stop="cancel" @blur="save"
      />
      <button v-else type="button" class="name" :title="todo.title.length > 16 ? todo.title : undefined" @click="edit">
        {{ todo.title }}
      </button>
      <span v-if="todo.at != null && !done" class="when-line">
        <button type="button" class="when" :class="{ late }" data-pop @click="emit('when')">
          {{ whenText(todo.at, todo.allDay, now) }}
          <Icon v-if="todo.repeat !== 'none'" name="refresh" :size="10" />
        </button>
        <button v-if="picking" type="button" class="when-x" data-pop aria-label="清除时间" @click="emit('clearWhen')">
          <Icon name="close" :size="10" />
        </button>
      </span>
    </span>
    <button
      v-if="todo.at == null && !done" type="button" class="side" :class="{ shown: picking }" title="时间" aria-label="时间" data-pop @click="emit('when')"
    >
      <Icon name="calendar" :size="13" />
    </button>
    <button type="button" class="side del" title="删除" :aria-label="`删除 ${todo.title}`" @click="emit('remove')">
      <Icon name="close" :size="12" />
    </button>
  </li>
</template>

<style scoped>
.row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 40px;
  padding: 4px 6px 4px 10px;
  box-sizing: border-box;
  border-radius: 10px;
  transition: background var(--dur-fast);
}
.row:hover, .row.picking {
  background: var(--c-50);
}
.tick {
  flex: none;
  display: grid;
  place-items: center;
  width: 18px;
  height: 18px;
  padding: 0;
  border: 2px solid var(--c-300);
  border-radius: 50%;
  background: transparent;
  color: transparent;
  cursor: pointer;
  transition: background var(--dur-fast), border-color var(--dur-fast), color var(--dur-fast);
}
.tick:hover {
  border-color: var(--c-500);
  color: var(--c-300);
}
.tick[aria-pressed="true"] {
  border-color: var(--c-500);
  background: var(--c-500);
  color: var(--surface);
}
.text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 3px;
}
.name, .name-box {
  width: 100%;
  min-width: 0;
  height: 18px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--ink);
  font: 700 13px/18px var(--font);
  text-align: left;
}
.name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: text;
  transition: color var(--dur-fast);
}
.name-box {
  outline: none;
  box-shadow: 0 1.5px 0 var(--c-500);
  user-select: text;
  -webkit-user-select: text;
}
.row.ticking .name, .row.done .name {
  color: var(--ink-3);
  text-decoration: line-through;
  text-decoration-color: var(--c-300);
}
.row.done .name {
  cursor: default;
}
.when-line {
  display: flex;
  align-items: center;
  gap: 2px;
}
.when {
  display: flex;
  align-items: center;
  gap: 3px;
  height: 16px;
  margin-left: -4px;
  padding: 0 4px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--ink-3);
  font: 700 11px/1 var(--font);
  font-variant-numeric: tabular-nums;
  cursor: pointer;
  transition: background var(--dur-fast), color var(--dur-fast);
}
.when:hover, .row.picking .when {
  background: var(--c-100);
  color: var(--ink-2);
}
.when.late {
  color: var(--c-600);
}
.when-x {
  display: grid;
  place-items: center;
  width: 16px;
  height: 16px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--ink-3);
  cursor: pointer;
}
.when-x:hover {
  background: var(--c-100);
  color: var(--ink);
}
.side {
  flex: none;
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--ink-3);
  opacity: 0;
  cursor: pointer;
  transition: opacity var(--dur-fast), background var(--dur-fast), color var(--dur-fast);
}
.row:hover .side, .side:focus-visible, .side.shown {
  opacity: 1;
}
.side:hover {
  background: var(--surface);
  color: var(--ink);
}
</style>
