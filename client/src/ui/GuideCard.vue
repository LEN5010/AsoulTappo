<script setup lang="ts">
// A guide card (src/guide.ts): one line and 知道了; the guide has no skip, every card is answered. Mouse only: the desk
// window never has the keyboard on Windows. Takes the mouse with click-through on too, and never starts a drag of the
// pet it stands over.
defineProps<{ text: string }>();
const emit = defineEmits<{ ok: [] }>();
</script>

<template>
  <div class="guide-card" data-hit="keep" data-no-drag data-guide-card role="note">
    <p>{{ text }}</p>
    <div class="acts">
      <button type="button" class="ui-btn small primary" @click="emit('ok')">知道了</button>
    </div>
  </div>
</template>

<style scoped>
/* The pet's bubble paper. */
.guide-card {
  box-sizing: border-box;
  width: max-content;
  max-width: 260px;
  padding: 10px 10px 8px 12px;
  border-radius: 14px;
  background: var(--surface);
  box-shadow: 0 6px 16px -6px rgba(var(--shadow-rgb), 0.4);
  color: var(--ink);
  font-family: var(--font);
}
p {
  margin: 0 2px 8px 0;
  font: 800 var(--fs-label)/1.4 var(--font);
  white-space: nowrap;
}
.acts {
  display: flex;
  justify-content: flex-end;
}
</style>
