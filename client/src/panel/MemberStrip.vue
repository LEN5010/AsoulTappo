<script setup lang="ts">
// Backpack filter: a member card narrows the shelves to her, the ALL card lifts the filter.
import { characters } from "../characters";
import { manifest } from "../manifest";
import Icon from "../ui/Icon.vue";
import PetBust from "./PetBust.vue";

defineProps<{ modelValue: string }>();
const emit = defineEmits<{ "update:modelValue": [name: string] }>();

const pick = (name: string) => emit("update:modelValue", name);
</script>

<template>
  <div class="members" role="group" aria-label="筛选成员">
    <button
      type="button" class="member all" :class="{ on: modelValue === 'all' }"
      :aria-pressed="modelValue === 'all'" title="显示全部成员" @click="pick('all')"
    >
      <Icon name="users" :size="18" class="everyone" />
      <b>全部</b>
    </button>
    <button
      v-for="m in manifest.characters" :key="m.id" type="button"
      class="member" :class="{ on: modelValue === m.name }"
      :aria-pressed="modelValue === m.name" :title="`使用${m.name}原皮`" @click="pick(m.name)"
    >
      <PetBust v-if="characters[m.name]" class="bust" :src="characters[m.name]!.bg" />
      <b><i :style="{ background: m.color }" aria-hidden="true"></i>{{ m.name }}</b>
    </button>
  </div>
</template>

<style scoped>
.members {
  display: flex;
  align-items: center;
  gap: 4px;
}
/* A round portrait at rest; the picked member opens up to show the name. */
.member {
  position: relative;
  flex: none;
  height: 40px;
  min-width: 40px;
  padding: 0;
  box-sizing: border-box;
  border: 0;
  border-radius: 20px;
  display: flex;
  align-items: center;
  background: var(--surface);
  box-shadow: inset 0 0 0 1.5px var(--line-2);
  color: var(--ink-2);
  cursor: pointer;
  overflow: hidden;
  transition: transform var(--dur-base) var(--ease-out), box-shadow var(--dur-fast);
}
.member:hover {
  transform: translateY(-1px);
}
.member:hover:not(.on) {
  box-shadow: inset 0 0 0 1.5px var(--accent-mid), 0 6px 12px -8px rgba(var(--accent-rgb), 0.7);
}
.member:focus-visible {
  outline-offset: 1px;
}
.member.on {
  background: var(--grad-main);
  box-shadow: var(--glow-s);
  color: var(--on-accent-surface);
}
.bust {
  flex: none;
  width: 40px;
  height: 37px;
  margin-top: 3px;
  filter: var(--contour);
}
.everyone {
  width: 40px;
  color: var(--accent-deep);
}
.on .everyone {
  color: var(--on-accent-surface);
}
b {
  display: none;
  align-items: center;
  gap: 4px;
  padding: 0 13px 0 3px;
  font: 800 var(--fs-body)/1 var(--font);
  white-space: nowrap;
  color: var(--ink);
}
.on b {
  display: flex;
  animation: name-in var(--dur-slow) var(--ease-out);
}
@keyframes name-in {
  from {
    opacity: 0;
    transform: translateX(-8px);
  }
}
b i {
  flex: none;
  width: 4px;
  height: 11px;
  border-radius: 1px;
}
</style>
