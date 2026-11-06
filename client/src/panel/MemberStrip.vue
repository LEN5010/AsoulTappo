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
      <Icon name="people" :size="16" class="everyone" />
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
  gap: 6px;
  padding-bottom: 3px;
}
/* Round keycaps, like a typewriter's. The picked member is latched in coral and opens up to show the name. */
.member {
  --key-top: #fff;
  --key-bottom: var(--key-white-shade);
  --key-lip: var(--c-200);
  --key-lip-h: 3px;
  --key-y: 0px;
  position: relative;
  flex: none;
  height: 32px;
  min-width: 32px;
  padding: 0;
  box-sizing: border-box;
  border: 0;
  border-radius: 16px;
  display: flex;
  align-items: center;
  background: linear-gradient(180deg, var(--key-top), var(--key-bottom));
  box-shadow: 0 var(--key-lip-h) 0 var(--key-lip), 0 calc(var(--key-lip-h) + 1px) calc(var(--key-lip-h) * 2 + 2px) -3px rgba(var(--c-900-rgb), 0.25);
  transform: translateY(var(--key-y));
  color: var(--ink-2);
  cursor: pointer;
  overflow: hidden;
  transition:
    transform var(--dur-release) var(--ease-spring),
    box-shadow var(--dur-release) var(--ease-spring);
}
.member:hover {
  --key-bottom: #fff;
  --key-y: -1px;
}
.member.on {
  --key-top: var(--c-500);
  --key-bottom: var(--c-500);
  --key-lip: var(--c-600);
  --key-lip-h: 1px;
  --key-y: 2px;
  color: var(--ink);
}
.member:active {
  --key-lip-h: 0px;
  --key-y: 3px;
  transition-duration: var(--dur-press);
  transition-timing-function: ease-out;
}
.member:focus-visible {
  outline-offset: 2px;
}
.bust {
  flex: none;
  width: 32px;
  height: 30px;
  margin-top: 2px;
  filter: var(--contour);
}
.everyone {
  width: 32px;
  color: var(--c-700);
}
.on .everyone {
  color: var(--ink);
}
b {
  display: none;
  align-items: center;
  gap: 4px;
  padding: 0 12px 0 2px;
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
