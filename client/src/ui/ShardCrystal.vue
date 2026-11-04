<script setup lang="ts">
// Crystal cluster beside the shard balance. Facets are theme tokens, so it follows the member colors.
defineProps<{ size?: number }>();
</script>

<template>
  <svg :width="size ?? 64" :height="size ?? 64" viewBox="0 0 96 96" aria-hidden="true" class="crystal">
    <ellipse class="ground" cx="48" cy="89" rx="38" ry="4" />
    <path class="mid" d="M22 36L9 56l13 32h8z" />
    <path class="soft" d="M22 36l14 20v32h-6z" />
    <path class="soft" d="M76 32L64 54l2 34h10z" />
    <path class="mid" d="M76 32l14 22-6 34h-8z" />
    <path class="deep" d="M50 6L33 30l7 58h10z" />
    <path class="mid" d="M50 6l17 24-7 58H50z" />
    <path class="light" d="M50 6l-9 24 9 14z" />
    <path class="light" d="M22 36l-6 19 7 7z" />
    <path class="light" d="M76 32l-5 21 6 6z" />
  </svg>
</template>

<style scoped>
.crystal {
  flex: none;
  display: block;
}
.ground {
  fill: var(--accent-soft);
}
.deep {
  fill: var(--accent);
}
.mid {
  fill: var(--accent-mid);
}
.soft {
  fill: var(--accent-soft);
}
.light {
  fill: var(--surface);
  opacity: 0.72;
}
</style>
