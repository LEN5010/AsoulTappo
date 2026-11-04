<script setup lang="ts">
import { nextTick, onBeforeUnmount, onDeactivated, onMounted, ref } from "vue";
import { takeFocus, trapTab } from "./focus";
import Icon from "./Icon.vue";

// `still` drops the sheet's slide for content that animates into place on its own.
defineProps<{ title?: string; wide?: boolean; still?: boolean }>();
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
        <div class="sheet-band" aria-hidden="true"></div>
        <button type="button" class="x ui-slant" aria-label="关闭" @click="emit('close')"><Icon name="close" :size="15" /></button>
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
  background: rgba(var(--ink-rgb), 0.46);
  animation: fade var(--dur-fast) var(--ease-out);
}
.sheet {
  position: relative;
  outline: none;
  width: min(400px, 100%);
  max-height: 100%;
  overflow: auto;
  box-sizing: border-box;
  background: var(--surface);
  box-shadow: var(--drop-l) var(--accent);
  animation: slide var(--dur-slow) var(--ease-out);
}
.sheet.wide {
  width: min(600px, 100%);
}
.sheet.still {
  animation: fade var(--dur-base) var(--ease-out);
}
.sheet-band {
  position: relative;
  height: 22px;
  overflow: hidden;
  background: var(--accent);
}
.sheet-band::after {
  content: "";
  position: absolute;
  inset: 0;
  background: repeating-linear-gradient(82deg, rgba(255, 255, 255, 0.28) 0 10px, transparent 10px 22px);
}
.sheet-body {
  padding: 18px 24px 24px;
}
.x {
  --slant-bg: var(--ink);
  position: absolute;
  right: 10px;
  top: 0;
  width: 42px;
  height: 22px;
  padding: 0;
  border: 0;
  background: none;
  color: var(--on-ink);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  z-index: 2;
}
.x:hover {
  --slant-bg: var(--accent-deep);
}
@keyframes fade { from { opacity: 0; } }
@keyframes slide { from { opacity: 0; transform: translate(-22px, 16px); } }
</style>
