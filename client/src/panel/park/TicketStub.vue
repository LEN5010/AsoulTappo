<script setup lang="ts">
// A paper ticket stub: a coral row of perforations down one side, with a half-round bite out of the top and the
// bottom edge where it runs, and the number (the default slot) in Barlow. The bites are cut out of the paper, so
// whatever the stub lies on shows through them.
withDefaults(defineProps<{ side?: "left" | "right"; size?: "s" | "m" | "l" }>(), { side: "left", size: "m" });
</script>

<template>
  <!-- The shadow is on the outer box: a mask on the paper would cut its own shadow off. -->
  <span class="ticket-stub" :class="[side, size]">
    <span class="paper">
      <i class="perf" aria-hidden="true"></i>
      <span class="num"><slot /></span>
    </span>
  </span>
</template>

<style scoped>
.ticket-stub {
  --h: 56px;
  --font-size: 28px;
  --tab: 14px;
  --bite: 6px;
  display: inline-flex;
  flex: none;
  filter: drop-shadow(0 1px 1px rgba(var(--c-900-rgb), 0.18)) drop-shadow(0 3px 4px rgba(var(--c-900-rgb), 0.12));
}
.s {
  --h: 40px;
  --font-size: 20px;
  --tab: 10px;
  --bite: 4.5px;
}
.l {
  --h: 72px;
  --font-size: 36px;
  --tab: 18px;
  --bite: 7px;
}
.paper {
  --x: var(--tab);
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: var(--h);
  min-width: calc(var(--h) * 1.3);
  padding: 0 14px 0 calc(var(--tab) + 10px);
  box-sizing: border-box;
  border-radius: var(--radius-s);
  background: var(--surface);
  /* The two bites, top and bottom, on the perforation's line. */
  mask:
    radial-gradient(circle at var(--x) 0, transparent var(--bite), #000 calc(var(--bite) + 0.5px)),
    radial-gradient(circle at var(--x) 100%, transparent var(--bite), #000 calc(var(--bite) + 0.5px));
  mask-composite: intersect;
}
.right .paper {
  --x: calc(100% - var(--tab));
  padding: 0 calc(var(--tab) + 10px) 0 14px;
}
/* The perforation: a column of small coral dots between the two bites. */
.perf {
  position: absolute;
  top: calc(var(--bite) + 3px);
  bottom: calc(var(--bite) + 3px);
  left: var(--x);
  width: 3px;
  margin-left: -1.5px;
  background: radial-gradient(circle, var(--c-500) 1.2px, transparent 1.6px) 50% 0 / 3px 6px repeat-y;
}
.num {
  font: 800 var(--font-size)/1 var(--font-latin);
  letter-spacing: 0.04em;
  color: var(--ink);
  white-space: nowrap;
}
</style>
