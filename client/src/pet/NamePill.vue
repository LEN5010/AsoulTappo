<script setup lang="ts">
// A paper name tag under a pet, led by the member's room status (a segment tinted in the member's colour, if
// any) and a tick in the member's colour.
// `height` and `font` (px) override the default size, for partners drawn small.
import { computed } from "vue";
import { roomStatus } from "../roomStatus";
import Icon from "../ui/Icon.vue";

const props = defineProps<{ nick: string; width: number; color?: string; height?: number; font?: number; status?: string | null }>();
const shown = computed(() => roomStatus(props.status));
</script>

<template>
  <div
    class="pill"
    :style="{ maxWidth: `${width}px`, height: height ? `${height}px` : undefined, fontSize: font ? `${font}px` : undefined }"
    :title="shown?.label"
  >
    <span v-if="shown" class="status" :style="color ? { '--cheer': color } : undefined"><Icon :name="shown.icon" :size="Math.round((font ?? 12) * 1.25)" />{{ shown.label }}</span>
    <i v-if="color" :style="{ background: color }" aria-hidden="true"></i>
    <span class="nick">{{ nick }}</span>
  </div>
</template>

<style scoped>
.pill {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-width: 56px;
  height: 22px;
  margin-top: 1px;
  padding: 0 10px;
  box-sizing: border-box;
  border-radius: 11px;
  background: var(--surface);
  box-shadow: 0 1px 2px rgba(var(--shadow-rgb), 0.12), 0 4px 10px -4px rgba(var(--shadow-rgb), 0.3);
  font-family: var(--font);
  font-size: var(--fs-label);
  font-weight: 800;
  color: var(--ink);
}
.pill i {
  flex: none;
  width: 4px;
  height: 11px;
  border-radius: 1px;
}
/* Flush with the tag's left end, as tall as the tag. */
.pill .status {
  flex: none;
  align-self: stretch;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-left: -10px;
  padding: 0 7px 0 8px;
  border-radius: inherit;
  border-top-right-radius: 0;
  border-bottom-right-radius: 0;
  background: color-mix(in oklab, var(--cheer, var(--c-500)) 22%, var(--surface));
  color: color-mix(in oklab, var(--cheer, var(--c-500)) 62%, var(--ink));
  white-space: nowrap;
}
.pill .nick {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
