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
    <div class="sheet ui-scroll" :class="{ wide }" role="dialog" aria-modal="true" :aria-label="title">
      <button type="button" class="x" aria-label="关闭" @click="emit('close')"><Icon name="close" :size="18" /></button>
      <slot />
    </div>
  </div>
</template>

<style scoped>
.backdrop { position: absolute; inset: 0; z-index: 20; display: flex; align-items: center; justify-content: center; padding: 20px; box-sizing: border-box; background: rgba(59, 45, 51, 0.28); backdrop-filter: blur(3px); animation: fade 160ms ease-out; }
.sheet { position: relative; width: min(380px, 100%); max-height: 100%; overflow: auto; box-sizing: border-box; padding: 22px; border-radius: var(--r-xl); background: var(--paper); box-shadow: var(--shadow-2); animation: pop 220ms cubic-bezier(0.34, 1.5, 0.64, 1); }
.sheet.wide { width: min(560px, 100%); }
.x { position: absolute; right: 12px; top: 12px; width: 32px; height: 32px; border-radius: 50%; border: none; background: var(--paper-2); color: var(--ink-2); cursor: pointer; display: grid; place-items: center; z-index: 1; }
.x:hover { color: var(--ink); }
@keyframes fade { from { opacity: 0; } }
@keyframes pop { from { opacity: 0; transform: scale(0.9) translateY(8px); } }
</style>
