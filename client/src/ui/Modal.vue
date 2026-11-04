<script setup lang="ts">
import { onBeforeUnmount, onMounted } from "vue";
import Icon from "./Icon.vue";

defineProps<{ title?: string; wide?: boolean }>();
const emit = defineEmits<{ close: [] }>();
const onKey = (e: KeyboardEvent) => e.key === "Escape" && emit("close");
onMounted(() => window.addEventListener("keydown", onKey));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey));
</script>

<template>
  <div class="backdrop" @click.self="emit('close')">
    <slot name="behind" />
    <div class="sheet ui-scroll" :class="{ wide }" role="dialog" aria-modal="true" :aria-label="title">
      <div class="sheet-band" aria-hidden="true"></div>
      <button type="button" class="x" aria-label="关闭" @click="emit('close')"><Icon name="close" :size="15" /></button>
      <div class="sheet-body">
        <slot />
      </div>
    </div>
    <slot name="front" />
  </div>
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
  background: rgba(43, 37, 48, 0.46);
  animation: fade 160ms ease-out;
}
.sheet {
  position: relative;
  width: min(400px, 100%);
  max-height: 100%;
  overflow: auto;
  box-sizing: border-box;
  background: var(--surface);
  box-shadow: 8px 8px 0 var(--accent);
  animation: slide 320ms var(--ease-out);
}
.sheet.wide {
  width: min(600px, 100%);
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
  position: absolute;
  right: 10px;
  top: 0;
  width: 42px;
  height: 22px;
  padding: 0;
  border: 0;
  background: none;
  color: #fff;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  z-index: 2;
  isolation: isolate;
}
.x::before {
  content: "";
  position: absolute;
  inset: 0;
  z-index: -1;
  background: var(--ink);
  transform: skewX(var(--skew));
  transition: background 140ms;
}
.x:hover::before {
  background: var(--accent-deep);
}
@keyframes fade { from { opacity: 0; } }
@keyframes slide { from { opacity: 0; transform: translate(-22px, 16px); } }
</style>
