<script setup lang="ts">
// Over the pet once the server counts this save's input as automatic (an auto-clicker, a macro). Stays until closed.
const emit = defineEmits<{ close: [] }>();
</script>

<template>
  <div class="anchor">
    <div class="auto" data-hit data-no-drag role="alert">
      <p>识别到自动点击</p>
      <button type="button" class="ui-btn small primary" @click="emit('close')">知道了</button>
    </div>
  </div>
</template>

<style scoped>
.anchor { position: absolute; left: 50%; top: 0; width: 0; height: 0; z-index: 6; }
.auto {
  position: absolute; left: 0; bottom: 8px; display: flex; align-items: center; gap: 10px; width: max-content;
  padding: 8px 10px 8px 12px; transform: translateX(-50%); border-radius: 14px; background: var(--surface);
  box-shadow: 0 6px 16px -6px rgba(var(--shadow-rgb), 0.4); color: var(--ink);
}
.auto::after {
  content: ""; position: absolute; left: 50%; top: 100%; translate: -50% 0;
  border: 7px solid transparent; border-top-color: var(--surface); border-bottom: 0;
}
.auto p { margin: 0; font: 800 var(--fs-label)/1.35 var(--font); white-space: nowrap; }
</style>
