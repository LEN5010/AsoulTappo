<script setup lang="ts">
import ChestIcon from "./ChestIcon.vue";

defineProps<{ count: number; busy: boolean }>();
defineEmits<{ open: [] }>();
</script>

<template>
  <button type="button" class="chest" :class="{ busy }" :title="`打开宝箱（${count}）`" aria-label="打开宝箱" @click="$emit('open')">
    <ChestIcon :size="30" :open="busy" />
    <span v-if="count > 1" class="n">{{ count }}</span>
  </button>
</template>

<style scoped>
.chest {
  position: absolute;
  right: -6px;
  bottom: calc(100% + 10px);
  width: 46px;
  height: 42px;
  padding: 0;
  border: 0;
  cursor: pointer;
  background: var(--surface);
  box-sizing: border-box;
  box-shadow: 4px 4px 0 var(--accent), 0 6px 14px rgba(43, 37, 48, 0.2);
  display: grid;
  place-items: center;
  animation: bob 1.8s ease-in-out infinite;
}
.chest:hover {
  animation-play-state: paused;
}
.chest.busy {
  animation: shake 320ms linear infinite;
}
.n {
  position: absolute;
  right: -8px;
  top: -8px;
  min-width: 20px;
  height: 18px;
  padding: 0 5px;
  box-sizing: border-box;
  background: var(--ink);
  color: #fff;
  font: italic 800 14px/18px var(--font-latin);
  text-align: center;
  transform: skewX(var(--skew));
}
@keyframes bob {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-4px); }
}
@keyframes shake {
  0%, 100% { transform: rotate(0); }
  25% { transform: rotate(-6deg); }
  75% { transform: rotate(6deg); }
}
</style>
