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
.backdrop { position: absolute; inset: 0; z-index: 20; display: flex; align-items: center; justify-content: center; padding: 20px; box-sizing: border-box; background: rgba(43, 35, 38, 0.32); animation: fade 140ms ease-out; }
.sheet { position: relative; width: min(380px, 100%); max-height: 100%; overflow: auto; box-sizing: border-box; padding: 20px; border-radius: var(--r-xl); background: var(--paper); border: 1px solid var(--line-2); box-shadow: var(--shadow-2); animation: pop 160ms ease-out; }
.sheet.wide { width: min(560px, 100%); }
.x { position: absolute; right: 10px; top: 10px; width: 28px; height: 28px; border-radius: var(--r-m); border: none; background: none; color: var(--ink-2); cursor: pointer; display: grid; place-items: center; z-index: 1; }
.x:hover { color: var(--ink); background: var(--paper-2); }
@keyframes fade { from { opacity: 0; } }
@keyframes pop { from { opacity: 0; transform: translateY(6px); } }
</style>
