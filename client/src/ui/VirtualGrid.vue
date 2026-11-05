<script setup lang="ts" generic="T">
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from "vue";

const props = withDefaults(defineProps<{
  items: T[]; itemKey: (item: T) => string; minWidth?: number; gap?: number; extra?: boolean;
}>(), { minWidth: 76, gap: 10, extra: false });
const root = ref<HTMLElement>();
const width = ref(0);
const top = ref(0);
const height = ref(0);
const textHeight = ref(23);
const columns = computed(() => Math.max(1, Math.floor((width.value + props.gap) / (props.minWidth + props.gap))));
const rowHeight = computed(() => (width.value - (columns.value - 1) * props.gap) / columns.value + textHeight.value + props.gap);
const total = computed(() => props.items.length + Number(props.extra));
const rows = computed(() => Math.ceil(total.value / columns.value));
const startRow = computed(() => Math.max(0, Math.min(rows.value, Math.floor(top.value / rowHeight.value) - 2)));
const endRow = computed(() => Math.min(rows.value, Math.max(startRow.value + 1,
  Math.ceil((top.value + height.value) / rowHeight.value) + 2)));
const start = computed(() => startRow.value * columns.value);
const end = computed(() => endRow.value * columns.value);
const visible = computed(() => props.items.slice(start.value, end.value));
let scroller: HTMLElement | null = null;
let resize: ResizeObserver | undefined;
let frame = 0;
function measure() {
  frame = 0;
  if (!root.value || !scroller) return;
  const style = getComputedStyle(root.value);
  width.value = root.value.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
  height.value = scroller.clientHeight;
  top.value = scroller.getBoundingClientRect().top - root.value.getBoundingClientRect().top;
  textHeight.value = parseFloat(getComputedStyle(root.value).lineHeight) + 5;
}
function schedule() { if (!frame) frame = requestAnimationFrame(measure); }
function connect() {
  scroller = root.value?.parentElement?.closest<HTMLElement>(".ui-scroll") ?? null;
  scroller?.addEventListener("scroll", schedule, { passive: true });
  if (scroller) resize?.observe(scroller);
  if (root.value) resize?.observe(root.value);
  schedule();
}
function disconnect() {
  scroller?.removeEventListener("scroll", schedule);
  resize?.disconnect();
  cancelAnimationFrame(frame);
  frame = 0;
}
onMounted(() => { resize = new ResizeObserver(schedule); connect(); });
onActivated(connect);
onDeactivated(disconnect);
onBeforeUnmount(disconnect);
watch(() => props.items, () => nextTick(schedule));
</script>

<template>
  <div ref="root" class="virtual-grid" :style="{
    gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))`, gap: `${gap}px`,
    gridAutoRows: `${rowHeight - gap}px`,
    paddingTop: `${startRow * rowHeight}px`, paddingBottom: `${Math.max(0, rows - endRow) * rowHeight}px`,
  }">
    <template v-for="item in visible" :key="itemKey(item)"><slot :item="item" /></template>
    <slot v-if="extra && start < total && end >= total" name="extra" />
  </div>
</template>

<style scoped>
.virtual-grid { display: grid; align-content: start; min-width: 0; box-sizing: border-box; line-height: 18px; }
</style>
