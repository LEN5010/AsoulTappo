<script setup lang="ts">
// Cute rounded icon set (24x24, stroke = currentColor).
const PATHS: Record<string, string[]> = {
  box: ["M4 11h16v9a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z", "M3 8h18v3H3z", "M12 8v13", "M12 8c-2-3.5-5.5-3.5-5.5-1S9 8 12 8", "M12 8c2-3.5 5.5-3.5 5.5-1S15 8 12 8"],
  bag: ["M6 9a6 6 0 0 1 12 0v9a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2z", "M9 9V7a3 3 0 0 1 6 0v2", "M9.5 14a2.5 2.5 0 0 0 5 0"],
  book: ["M6 4h10a2 2 0 0 1 2 2v14H8a2 2 0 0 1-2-2z", "M6 18a2 2 0 0 1 2-2h10", "M12 8l1 2.2 2.2 1-2.2 1-1 2.2-1-2.2-2.2-1 2.2-1z"],
  craft: ["M12 3l1.8 4.7 4.7 1.8-4.7 1.8L12 16l-1.8-4.7-4.7-1.8 4.7-1.8z", "M18.5 15l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z", "M5.5 16l.5 1.2 1.2.5-1.2.5-.5 1.2-.5-1.2-1.2-.5 1.2-.5z"],
  home: ["M3 11l9-7 9 7", "M5 9.5V19a1 1 0 0 0 1 1h4v-5h4v5h4a1 1 0 0 0 1-1V9.5"],
  users: ["M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6z", "M3.5 19a5.5 5.5 0 0 1 11 0", "M15.5 5.3a3 3 0 0 1 0 5.4", "M17.5 14.2A5.5 5.5 0 0 1 20.5 19"],
  nut: ["M12 3l7.8 4.5v9L12 21l-7.8-4.5v-9z", "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"],
  sliders: ["M12 3l7.8 4.5v9L12 21l-7.8-4.5v-9z", "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"],
  fold: ["M4 6h16", "M10 12h10", "M4 18h16", "M7 9l-3 3 3 3"],
  unfold: ["M4 6h16", "M4 12h10", "M4 18h16", "M17 9l3 3-3 3"],
  close: ["M6 6l12 12", "M18 6L6 18"],
  star: ["M12 3l2.2 6.8L21 12l-6.8 2.2L12 21l-2.2-6.8L3 12l6.8-2.2z"],
  plus: ["M12 5v14", "M5 12h14"],
  copy: ["M9 9h10v10H9z", "M5 15V5h10"],
  menu: ["M5 7h14", "M5 12h14", "M5 17h14"],
  check: ["M5 12.5l4.5 4.5L19 7.5"],
  lock: ["M7.5 11V8.5a4.5 4.5 0 0 1 9 0V11", "M6 11h12v9H6z"],
  shard: ["M12 3l6 7-6 11-6-11z", "M6 10h12", "M12 3l-2 7 2 11 2-11z"],
  search: ["M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14z", "M16 16l4 4"],
  play: ["M8 5.5v13l10.5-6.5z"],
  down: ["M6 9l6 6 6-6"],
  refresh: ["M19 8a8 8 0 1 0 .9 6", "M19 3v5h-5"],
  trash: ["M5 7h14", "M10 7V5h4v2", "M7 7l1 13h8l1-13"],
  person: ["M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8z", "M5 20a7 7 0 0 1 14 0"],
  bow: ["M12 12L5 7v10z", "M12 12l7-5v10z", "M12 12v.01"],
  smile: ["M12 20a8 8 0 1 0 0-16 8 8 0 0 0 0 16z", "M9 10v.5", "M15 10v.5", "M8.5 14a4 4 0 0 0 7 0"],
  card: ["M7 3h10a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z", "M9 15l2-3 2 2 2-3"],
  palette: ["M12 20a8 8 0 1 1 8-8c0 2-1.5 3-3 3h-2a2 2 0 0 0-1.5 3.3A1 1 0 0 1 12 20z", "M8 11v.01", "M11 8v.01", "M15 9v.01"],
  ring: ["M12 20a8 8 0 1 0 0-16 8 8 0 0 0 0 16z", "M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8z"],
  medal: ["M12 21a5 5 0 1 0 0-10 5 5 0 0 0 0 10z", "M9 11L6 3h4l2 5", "M15 11l3-8h-4l-2 5"],
  link: ["M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1", "M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"],
  logout: ["M15 4h4v16h-4", "M10 8l-4 4 4 4", "M6 12h10"],
  grid: ["M5 5h6v6H5z", "M13 5h6v6h-6z", "M5 13h6v6H5z", "M13 13h6v6h-6z"],
  thumb: ["M7 11H4v9h3z", "M7 11l3.6-6.3a1.8 1.8 0 0 1 3.3 1.3L13 10h5.2a2 2 0 0 1 2 2.4l-1.3 6A2 2 0 0 1 17 20H7"],
};
defineProps<{ name: string; size?: number }>();
</script>

<template>
  <svg
    :width="size ?? 20" :height="size ?? 20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="icon"
  >
    <path v-for="(d, i) in PATHS[name] ?? []" :key="i" :d="d" />
  </svg>
</template>

<style scoped>
.icon { flex: none; display: block; }
</style>
