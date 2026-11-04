<script setup lang="ts">
// Treasure chest drawn for this project.
defineProps<{ size?: number; open?: boolean }>();
</script>

<template>
  <svg :width="size ?? 32" :height="size ?? 32" viewBox="0 0 64 64" aria-hidden="true">
    <rect x="9" y="28" width="46" height="26" rx="6" fill="var(--accent)" />
    <rect x="9" y="28" width="46" height="8" fill="var(--accent-deep)" />
    <path :d="open ? 'M11 26 L18 10 h28 l7 16 z' : 'M9 30 a23 16 0 0 1 46 0 z'" fill="var(--accent-mid)" />
    <path :d="open ? 'M11 26 L18 10 h28 l7 16' : 'M9 30 a23 16 0 0 1 46 0'" fill="none" stroke="#2B2530" stroke-width="3" />
    <rect x="9" y="28" width="46" height="26" rx="6" fill="none" stroke="#2B2530" stroke-width="3" />
    <rect x="26" y="24" width="12" height="16" rx="3" fill="#FFFFFF" stroke="#2B2530" stroke-width="3" />
    <circle cx="32" cy="32" r="2.4" fill="#2B2530" />
    <path d="M16 40v10M48 40v10" stroke="var(--accent-deep)" stroke-width="3" stroke-linecap="round" />
  </svg>
</template>
