<script setup lang="ts">
import { ref } from "vue";
import { characters } from "../characters";
import { manifest } from "../manifest";
import { useSlider } from "../ui/useSlider";
import PetBust from "./PetBust.vue";

const props = defineProps<{ modelValue: string }>();
defineEmits<{ "update:modelValue": [name: string] }>();

const EN_NAMES: Record<string, string> = { jiaran: "Diana", nailin: "Eileen", beila: "Bella", xinyi: "Fiona", sinuo: "Gladys" };

const track = ref<HTMLElement>();
const thumb = ref<HTMLElement>();
useSlider(track, thumb, () => props.modelValue);
</script>

<template>
  <div ref="track" class="strip" role="radiogroup" aria-label="按成员筛选">
    <i ref="thumb" class="thumb" aria-hidden="true"></i>
    <button
      type="button" class="all" role="radio" :aria-checked="modelValue === 'all'"
      :class="{ on: modelValue === 'all' }" @click="$emit('update:modelValue', 'all')"
    >
      <b>全部</b><small>ALL</small>
    </button>
    <button
      v-for="m in manifest.characters" :key="m.id" type="button" role="radio" :aria-checked="modelValue === m.name"
      :class="{ on: modelValue === m.name }" @click="$emit('update:modelValue', m.name)"
    >
      <PetBust v-if="characters[m.name]" class="bust" :src="characters[m.name]!.bg" />
      <span class="who">
        <b><i :style="{ background: m.color }" aria-hidden="true"></i>{{ m.name }}</b>
        <small>{{ EN_NAMES[m.id] }}</small>
      </span>
    </button>
  </div>
</template>

<style scoped>
.strip {
  position: relative;
  display: flex;
  height: 46px;
  padding: 0 8px;
  background: var(--surface);
  box-shadow: inset 0 -2px 0 var(--line-2);
}
.thumb {
  position: absolute;
  left: 0;
  top: 0;
  opacity: 0;
  background: var(--accent);
  transform-origin: 0 50%;
  will-change: transform;
}
button {
  position: relative;
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 0 6px 0 2px;
  border: 0;
  background: none;
  color: var(--ink-3);
  cursor: pointer;
  transition: color 180ms;
}
button + button::before {
  content: "";
  position: absolute;
  left: 0;
  top: 9px;
  bottom: 9px;
  width: 1.5px;
  background: var(--line-2);
  transform: skewX(var(--skew));
}
button.on {
  color: var(--on-accent);
}
.all {
  flex: 0 0 58px;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
  padding: 0;
}
.bust {
  flex: none;
  align-self: flex-end;
  width: 52px;
  height: 44px;
  transition: transform 240ms var(--ease-out);
}
button:hover .bust {
  transform: translateY(-2px);
}
.who {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
b {
  display: flex;
  align-items: center;
  gap: 4px;
  font: 800 14px/1 var(--font);
  color: var(--ink);
}
b i {
  flex: none;
  width: 4px;
  height: 11px;
  transform: skewX(var(--skew));
}
small {
  font: italic 800 12px/1 var(--font-latin);
  letter-spacing: 0.06em;
  text-align: left;
}
</style>
