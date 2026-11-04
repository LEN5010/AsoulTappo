<script setup lang="ts">
// Icon set (24x24, stroke = currentColor). Square ends match the chamfers; soft shapes stay round.
const PATHS: Record<string, string[]> = {
  box: ["M4 11h16v9a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z", "M3 8h18v3H3z", "M12 8v13", "M12 8c-2-3.5-5.5-3.5-5.5-1S9 8 12 8", "M12 8c2-3.5 5.5-3.5 5.5-1S15 8 12 8"],
  bag: ["M6 9a6 6 0 0 1 12 0v9a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2z", "M9 9V7a3 3 0 0 1 6 0v2", "M9.5 14a2.5 2.5 0 0 0 5 0"],
  book: ["M6 4h10a2 2 0 0 1 2 2v14H8a2 2 0 0 1-2-2z", "M6 18a2 2 0 0 1 2-2h10", "M12 8l1 2.2 2.2 1-2.2 1-1 2.2-1-2.2-2.2-1 2.2-1z"],
  users: ["M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6z", "M3.5 19a5.5 5.5 0 0 1 11 0", "M15.5 5.3a3 3 0 0 1 0 5.4", "M17.5 14.2A5.5 5.5 0 0 1 20.5 19"],
  nut: ["M12 3l7.8 4.5v9L12 21l-7.8-4.5v-9z", "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"],
  fold: ["M4 6h16", "M10 12h10", "M4 18h16", "M7 9l-3 3 3 3"],
  unfold: ["M4 6h16", "M4 12h10", "M4 18h16", "M17 9l3 3-3 3"],
  close: ["M6 6l12 12", "M18 6L6 18"],
  minus: ["M5 12h14"],
  star5: ["M12 3l2.7 6 6.3.7-4.7 4.3 1.3 6.5-5.6-3.3-5.6 3.3 1.3-6.5L3 9.7l6.3-.7z"],
  heart: ["M12 20s-7.5-4.7-7.5-10.2A4.3 4.3 0 0 1 12 7.2a4.3 4.3 0 0 1 7.5 2.6C19.5 15.3 12 20 12 20z"],
  spark: ["M12 3l2.2 6.8L21 12l-6.8 2.2L12 21l-2.2-6.8L3 12l6.8-2.2z"],
  plus: ["M12 5v14", "M5 12h14"],
  copy: ["M9 9h10v10H9z", "M5 15V5h10"],
  menu: ["M5 7h14", "M5 12h14", "M5 17h14"],
  shard: ["M12 3l6 7-6 11-6-11z", "M6 10h12", "M12 3l-2 7 2 11 2-11z"],
  play: ["M8 5.5v13l10.5-6.5z"],
  down: ["M6 9l6 6 6-6"],
  refresh: ["M19 8a8 8 0 1 0 .9 6", "M19 3v5h-5"],
  card: ["M7 3h10a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z", "M9 15l2-3 2 2 2-3"],
  logout: ["M15 4h4v16h-4", "M10 8l-4 4 4 4", "M6 12h10"],
  grid: ["M5 5h6v6H5z", "M13 5h6v6h-6z", "M5 13h6v6H5z", "M13 13h6v6h-6z"],
  thumb: ["M7 11H4v9h3z", "M7 11l3.6-6.3a1.8 1.8 0 0 1 3.3 1.3L13 10h5.2a2 2 0 0 1 2 2.4l-1.3 6A2 2 0 0 1 17 20H7"],
  check: ["M5 13l4.5 4.5L19 7"],
  search: ["M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14z", "M16 16l5 5"],
  back: ["M14.5 5.5L8 12l6.5 6.5"],
  pause: ["M8.5 5v14", "M15.5 5v14"],
  sound: ["M4 9.5h3.5L13 5v14l-5.5-4.5H4z", "M16.5 9a4 4 0 0 1 0 6", "M19 6.5a8 8 0 0 1 0 11"],
  mute: ["M4 9.5h3.5L13 5v14l-5.5-4.5H4z", "M16.5 9.5l5 5", "M21.5 9.5l-5 5"],
};
const ROUND = new Set(["heart"]);
defineProps<{ name: string; size?: number }>();
</script>

<template>
  <svg
    :width="size ?? 20" :height="size ?? 20" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    stroke-width="2.2" :stroke-linecap="ROUND.has(name) ? 'round' : 'butt'" :stroke-linejoin="ROUND.has(name) ? 'round' : 'miter'"
    aria-hidden="true" class="icon"
  >
    <path v-for="(d, i) in PATHS[name] ?? []" :key="i" :d="d" />
  </svg>
</template>

<style scoped>
.icon { flex: none; display: block; }
</style>
