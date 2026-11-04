<script setup lang="ts" generic="T extends string">
import { ref } from "vue";
import { arrowSelect } from "./focus";

defineProps<{ options: readonly { id: T; label: string }[]; modelValue: T; label?: string }>();
defineEmits<{ "update:modelValue": [id: T] }>();
const root = ref<HTMLElement>();
</script>

<template>
  <div ref="root" class="chips" role="radiogroup" :aria-label="label" @keydown="arrowSelect($event, root)">
    <button
      v-for="o in options" :key="o.id" type="button" class="ui-chip" role="radio"
      :aria-checked="o.id === modelValue" :class="{ on: o.id === modelValue }" @click="$emit('update:modelValue', o.id)"
    >
      {{ o.label }}
    </button>
  </div>
</template>

<style scoped>
.chips {
  display: flex;
  gap: 5px;
  padding-left: 3px;
  flex: none;
}
</style>
