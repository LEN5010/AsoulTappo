<script setup lang="ts">
// Over the pet while its inputs sit out a cooldown for going faster than a hand: how long is left.
import { computed, onBeforeUnmount, ref, watch } from "vue";

const props = defineProps<{ until: number }>();
const now = ref(Date.now());
let timer: ReturnType<typeof setInterval> | undefined;

watch(() => props.until, (until) => {
  clearInterval(timer);
  now.value = Date.now();
  if (until <= now.value) return;
  timer = setInterval(() => {
    now.value = Date.now();
    if (now.value >= props.until) clearInterval(timer);
  }, 1000);
}, { immediate: true });
onBeforeUnmount(() => clearInterval(timer));

const left = computed(() => Math.ceil((props.until - now.value) / 1000));
</script>

<template>
  <div class="anchor" role="status">
    <Transition name="cool">
      <p v-if="left > 0" class="cool">太快啦，歇 {{ left }} 秒</p>
    </Transition>
  </div>
</template>

<style scoped>
.anchor { position: absolute; left: 50%; top: 0; width: 0; height: 0; pointer-events: none; z-index: 5; }
.cool {
  position: absolute; left: 0; bottom: 8px; margin: 0; padding: 6px 12px; transform: translateX(-50%);
  border-radius: 14px; background: var(--surface); box-shadow: 0 6px 16px -6px rgba(var(--shadow-rgb), 0.4);
  font: 800 var(--fs-strong)/1.3 var(--font); color: var(--ink); white-space: nowrap;
}
.cool::after {
  content: ""; position: absolute; left: 50%; top: 100%; translate: -50% 0;
  border: 7px solid transparent; border-top-color: var(--surface); border-bottom: 0;
}
.cool-enter-active { transition: opacity var(--dur-fast), transform var(--dur-fast) var(--ease-pop); }
.cool-enter-from { opacity: 0; transform: translate(-50%, 8px) scale(0.8); }
.cool-leave-active { transition: opacity var(--dur-base) var(--ease-in); }
.cool-leave-to { opacity: 0; }
</style>
