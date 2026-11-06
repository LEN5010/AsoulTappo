<script setup lang="ts">
import { nextTick, onBeforeUnmount, onDeactivated, onMounted, ref } from "vue";
import { takeFocus, trapTab } from "./focus";
import Icon from "./Icon.vue";

// `still` drops the sheet's slide for content that animates into place on its own.
// `title` names the dialog; `heading` also draws it in the header row, for callers without a heading of their own.
defineProps<{ title?: string; wide?: boolean; still?: boolean; heading?: boolean }>();
const emit = defineEmits<{ close: [] }>();

const sheet = ref<HTMLElement>();
let release: (() => void) | undefined;
function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") emit("close");
  else if (e.key === "Tab" && sheet.value) trapTab(sheet.value, e);
}
onMounted(async () => {
  window.addEventListener("keydown", onKey);
  await nextTick();
  release = takeFocus(sheet.value);
});
onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey);
  release?.();
});
// Teleported content stays behind when its page turns away (a desk shortcut can do that).
onDeactivated(() => emit("close"));
</script>

<template>
  <Teleport defer to=".panel-overlay">
    <div class="backdrop" data-overlay @click.self="emit('close')">
      <slot name="behind" />
      <div ref="sheet" class="sheet ui-scroll" :class="{ wide, still }" role="dialog" aria-modal="true" :aria-label="title" tabindex="-1">
        <div class="sheet-head">
          <h3 v-if="heading && title" class="sheet-title">{{ title }}</h3>
          <button type="button" class="x ui-btn ghost" aria-label="关闭" @click="emit('close')"><Icon name="close" :size="16" /></button>
        </div>
        <div class="sheet-body">
          <slot />
        </div>
      </div>
      <slot name="front" />
    </div>
  </Teleport>
</template>

<style scoped>
.backdrop {
  position: absolute;
  inset: 0;
  z-index: 30;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  box-sizing: border-box;
  overflow: hidden;
  background: rgba(var(--c-900-rgb), 0.42);
  animation: fade var(--dur-fast) var(--ease-out);
}
/* White paper with a quiet close key in its corner. */
.sheet {
  position: relative;
  outline: none;
  width: min(400px, 100%);
  max-height: 100%;
  overflow: auto;
  box-sizing: border-box;
  background: var(--surface);
  border-radius: 20px;
  box-shadow: 0 2px 4px rgba(var(--c-900-rgb), 0.08), 0 24px 48px -20px rgba(var(--c-900-rgb), 0.45);
  animation: slide var(--dur-slow) var(--ease-out);
}
.sheet.wide {
  width: min(600px, 100%);
}
.sheet.still {
  animation: fade var(--dur-base) var(--ease-out);
}
/* The close key owns its own row, so no content can slide under it. */
.sheet-head {
  height: 48px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 10px 0 24px;
  box-sizing: border-box;
}
.sheet-title {
  margin: 0;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: 800 18px/1.2 var(--font);
  color: var(--ink);
}
.x {
  flex: none;
  width: 32px;
  height: 32px;
  margin-left: auto;
  padding: 0;
}
.sheet-body {
  padding: 0 24px 24px;
}
@keyframes fade { from { opacity: 0; } }
@keyframes slide { from { opacity: 0; transform: translate(-22px, 16px); } }
</style>
