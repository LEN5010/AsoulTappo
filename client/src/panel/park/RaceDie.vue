<script setup lang="ts">
// A die face of the race: a small white key with coral pips, 1 to 3 on the diagonal. The size is --s (22px by
// default).
defineProps<{ face: number }>();
</script>

<template>
  <span class="race-die" :class="`f${face}`" aria-hidden="true"><i v-for="k in face" :key="k"></i></span>
</template>

<style scoped>
.race-die {
  --s: 22px;
  display: inline-grid;
  flex: none;
  grid-template: repeat(3, 1fr) / repeat(3, 1fr);
  width: var(--s);
  height: var(--s);
  padding: calc(var(--s) * 0.14);
  box-sizing: border-box;
  border-radius: 24%;
  background: linear-gradient(180deg, #fff, var(--key-white-shade));
  box-shadow: 0 2px 0 var(--c-300), 0 5px 8px -4px rgba(var(--c-900-rgb), 0.35);
}
.race-die i {
  width: 72%;
  aspect-ratio: 1;
  place-self: center;
  border-radius: 50%;
  background: var(--c-700);
}
.f1 i { grid-area: 2 / 2; }
.f2 i:nth-child(1) { grid-area: 1 / 1; }
.f2 i:nth-child(2) { grid-area: 3 / 3; }
.f3 i:nth-child(1) { grid-area: 1 / 1; }
.f3 i:nth-child(2) { grid-area: 2 / 2; }
.f3 i:nth-child(3) { grid-area: 3 / 3; }
</style>
