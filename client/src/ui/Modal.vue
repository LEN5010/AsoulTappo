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
      <div class="sheet-awning" aria-hidden="true"></div>
      <button type="button" class="x" aria-label="关闭" @click="emit('close')">
        <span class="x-inner"><Icon name="close" :size="15" /></span>
      </button>
      <div class="sheet-body">
        <slot />
      </div>
    </div>
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
  background: rgba(68, 36, 18, 0.36);
  backdrop-filter: blur(2px);
  animation: fade 140ms ease-out;
}
.sheet {
  position: relative;
  width: min(400px, 100%);
  max-height: 100%;
  overflow: auto;
  box-sizing: border-box;
  border-radius: 28px;
  background: var(--paper);
  border: 3px solid var(--tile-border);
  box-shadow: 0 6px 0 var(--tile-lip), var(--shadow-2);
  animation: pop 180ms cubic-bezier(0.34, 1.56, 0.64, 1);
}
.sheet.wide {
  width: min(600px, 100%);
}
.sheet-awning {
  height: 20px;
  background:
    repeating-linear-gradient(
      -45deg,
      rgba(252, 150, 110, 0.14) 0 10px,
      rgba(255, 245, 232, 0.5) 10px 20px
    ),
    #F5E4D0;
  border-bottom: 2px dashed var(--tile-border);
}
.sheet-body {
  padding: 18px 24px 24px;
}
.x {
  position: absolute;
  right: 12px;
  top: 10px;
  width: 30px;
  height: 30px;
  padding: 0;
  margin: 0;
  box-sizing: border-box;
  border-radius: 9px;
  transform: rotate(45deg);
  border: 2px solid #7E4529;
  background: linear-gradient(135deg, #FFB08E, var(--accent));
  color: #562915;
  box-shadow: 0 2px 0 #7E4529;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  z-index: 2;
  transition: transform 140ms, filter 140ms;
}
.x:hover {
  filter: brightness(1.06);
  transform: rotate(45deg) scale(1.06);
}
.x-inner {
  transform: rotate(-45deg);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
@keyframes fade { from { opacity: 0; } }
@keyframes pop { from { opacity: 0; transform: scale(0.92) translateY(8px); } }
</style>
