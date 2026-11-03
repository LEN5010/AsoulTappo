<script setup lang="ts">
// Range slider whose track is filled up to the current value (see .ui-range in tokens.css).
import { computed } from "vue";

const props = defineProps<{ modelValue: number; min: number; max: number; step: number }>();
const emit = defineEmits<{ "update:modelValue": [value: number] }>();
const fill = computed(() => `${((props.modelValue - props.min) / (props.max - props.min)) * 100}%`);
</script>

<template>
  <input
    class="ui-range" type="range" :min="min" :max="max" :step="step" :value="modelValue" :style="{ '--fill': fill }"
    @input="emit('update:modelValue', Number(($event.target as HTMLInputElement).value))"
  />
</template>
