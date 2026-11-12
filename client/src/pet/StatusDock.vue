<script setup lang="ts">
// A paper plate of status keys hung under the strip or the own name tag, like the quick emotes. Where the screen ends
// below it, it opens upwards instead, over the pet.
import { onMounted, ref } from "vue";
import StatusKeys from "../ui/StatusKeys.vue";

defineProps<{ modelValue: string }>();
defineEmits<{ "update:modelValue": [id: string] }>();

const root = ref<HTMLElement>();
const up = ref(false);
// Measured before the first paint, so the plate never shows cut off first.
onMounted(() => {
  const r = root.value?.getBoundingClientRect();
  if (r && r.bottom > window.innerHeight - 4) up.value = true;
});
</script>

<template>
  <div ref="root" class="status-dock" :class="{ up }" data-hit data-no-drag>
    <StatusKeys :model-value="modelValue" @update:model-value="(id) => $emit('update:modelValue', id)" />
  </div>
</template>

<style scoped>
.status-dock {
  position: absolute;
  left: 50%;
  top: calc(100% + 10px);
  transform: translateX(-50%);
  z-index: 20;
  padding: 6px;
  border-radius: 14px;
  background: var(--surface);
  box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.12), 0 8px 20px -6px rgba(var(--shadow-rgb), 0.35);
  font-family: var(--font);
  animation: drop-in var(--dur-base) var(--ease-out);
  cursor: default;
}
.status-dock.up {
  top: auto;
  bottom: calc(100% + 10px);
  animation-name: rise-in;
}
@keyframes drop-in {
  from {
    opacity: 0;
    transform: translate(-50%, -8px);
  }
}
@keyframes rise-in {
  from {
    opacity: 0;
    transform: translate(-50%, 8px);
  }
}
</style>
