<script setup lang="ts">
// The browser preview's todos' window: the same page (`?window=todo`) in a frame of the window's size floating over the
// desk page. Its title bar moves the frame and its close key hides it, told over postMessage (TodoApp.vue). Both pages
// share the local storage, so the list stays in step as it does between the app's windows. The app opens a window of
// its own instead (stores/ui.ts, openTodoWindow).
import { onBeforeUnmount, onMounted, ref } from "vue";
import { todoFrame } from "../stores/ui";
import { settings, todoSize } from "../stores/settings";

const MARGIN = 24;
const frame = ref<HTMLIFrameElement>();
const src = `${import.meta.env.BASE_URL || "/"}?window=todo`;

/** Kept inside the page, so the title bar can always be reached. */
function place(x: number, y: number) {
  todoFrame.x = Math.round(Math.min(Math.max(0, x), Math.max(0, innerWidth - todoFrame.w)));
  todoFrame.y = Math.round(Math.min(Math.max(0, y), Math.max(0, innerHeight - todoFrame.h)));
}
function onMessage(e: MessageEvent) {
  if (e.origin !== location.origin || e.source !== frame.value?.contentWindow) return;
  const m = e.data as { type?: string; dx?: number; dy?: number; w?: number; h?: number };
  if (m.type === "todo:hide") todoFrame.open = false;
  else if (m.type === "todo:move") place(todoFrame.x + (m.dx ?? 0), todoFrame.y + (m.dy ?? 0));
  else if (m.type === "todo:size") {
    todoFrame.w = todoSize(m.w ?? todoFrame.w, "w");
    todoFrame.h = todoSize(m.h ?? todoFrame.h, "h");
    place(todoFrame.x, todoFrame.y);
  }
}
const onResize = () => place(todoFrame.x, todoFrame.y);

onMounted(() => {
  if (!todoFrame.w) {
    todoFrame.w = settings.todoW;
    todoFrame.h = settings.todoH;
  }
  // The first time at the bottom right, as the app's window opens on the pet's monitor.
  if (todoFrame.x < 0 || todoFrame.y < 0) place(innerWidth - todoFrame.w - MARGIN, innerHeight - todoFrame.h - MARGIN);
  else onResize();
  window.addEventListener("message", onMessage);
  window.addEventListener("resize", onResize);
});
onBeforeUnmount(() => {
  window.removeEventListener("message", onMessage);
  window.removeEventListener("resize", onResize);
});
</script>

<template>
  <iframe
    ref="frame" class="todo-frame" :src="src" title="待办" :width="todoFrame.w" :height="todoFrame.h"
    :style="{ left: `${todoFrame.x}px`, top: `${todoFrame.y}px` }"
  ></iframe>
</template>

<style scoped>
.todo-frame {
  position: fixed;
  z-index: 3000;
  border: 0;
  background: transparent;
  color-scheme: normal;
  pointer-events: auto;
}
</style>
