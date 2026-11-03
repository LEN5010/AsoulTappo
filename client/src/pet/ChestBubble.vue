<script setup lang="ts">
import ChestIcon from "./ChestIcon.vue";

defineProps<{ count: number; busy: boolean }>();
defineEmits<{ open: [] }>();
</script>

<template>
  <button type="button" class="chest" :class="{ busy }" :title="`打开宝箱（${count}）`" aria-label="打开宝箱" @click="$emit('open')">
    <span class="rays" aria-hidden="true"><i></i><i></i><i></i></span>
    <ChestIcon :size="30" :open="busy" />
    <span v-if="count > 1" class="n">{{ count }}</span>
  </button>
</template>

<style scoped>
.chest {
  position: absolute; right: -10px; bottom: calc(100% + 4px); width: 46px; height: 42px; border: none; padding: 0; cursor: pointer;
  border-radius: var(--r-l, 8px) var(--r-l, 8px) var(--r-l, 8px) 3px; background: #fffaf0; border: 1px solid #ecc98a; box-sizing: border-box; box-shadow: 0 4px 10px rgba(120, 70, 20, 0.2);
  display: grid; place-items: center; animation: bob 1.8s ease-in-out infinite;
}
.chest:hover { animation-play-state: paused; transform: scale(1.06); }
.chest.busy { animation: shake 320ms linear infinite; }
.n { position: absolute; right: -6px; top: -6px; min-width: 18px; height: 18px; padding: 0 5px; box-sizing: border-box; border-radius: var(--r-s, 4px); background: var(--accent); color: var(--on-accent); font-size: 11px; font-weight: 700; display: grid; place-items: center; font-family: var(--font); }
.rays { position: absolute; right: -9px; top: -8px; width: 14px; height: 14px; }
.rays i { position: absolute; left: 6px; top: 0; width: 2.5px; height: 6px; border-radius: 2px; background: #f2b45a; transform-origin: 1px 13px; }
.rays i:nth-child(1) { transform: rotate(-45deg); } .rays i:nth-child(2) { transform: rotate(0deg); } .rays i:nth-child(3) { transform: rotate(45deg); }
@keyframes bob { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-4px); } }
@keyframes shake { 0%, 100% { transform: rotate(0); } 25% { transform: rotate(-6deg); } 75% { transform: rotate(6deg); } }
</style>
