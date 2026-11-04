<script setup lang="ts">
import { computed } from "vue";
import { getCharacter } from "../characters";
import type { Drop } from "../net/api";
import { reducedMotion } from "../stores/theme";
const props = defineProps<{ drop: Drop; settled: boolean }>();
defineEmits<{ done: [] }>();
const name = computed(() => props.drop.item.slice(5));
</script>
<template>
  <div class="skin-spot" :class="{ calm: reducedMotion, settled }" @animationend.self="$emit('done')">
    <img :src="getCharacter(name)?.bg" :alt="name" />
    <div class="facts"><span class="ui-tag gold">新皮肤</span><h3>{{ name }}</h3><p>已解锁 · 可在背包中使用</p></div>
  </div>
</template>
<style scoped>
.skin-spot {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 24px;
  background: var(--grad-sky);
  color: var(--ink);
  animation: arrive 700ms var(--ease-out);
}
.skin-spot img {
  width: 65%;
  height: 85%;
  object-fit: contain;
}
.facts {
  max-width: 30%;
}
h3 {
  font-size: var(--fs-title);
}
p {
  font-size: var(--fs-body);
}
@keyframes arrive { from { opacity: 0; transform: scale(0.94); } }
.calm, .settled {
  animation: none;
}
</style>
