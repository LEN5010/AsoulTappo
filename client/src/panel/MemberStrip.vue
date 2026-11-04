<script setup lang="ts">
// Member cards equip the corresponding original skin.
import { characters } from "../characters";
import { manifest, memberOf } from "../manifest";
import Icon from "../ui/Icon.vue";
import PetBust from "./PetBust.vue";

defineProps<{ modelValue: string }>();
const emit = defineEmits<{ "update:modelValue": [name: string] }>();

const EN_NAMES: Record<string, string> = { jiaran: "Diana", nailin: "Eileen", beila: "Bella", xinyi: "Fiona", sinuo: "Gladys" };

const pick = (name: string) => emit("update:modelValue", name);
</script>

<template>
  <div class="members" role="group" aria-label="选择成员原皮">
    <button
      v-for="m in manifest.characters" :key="m.id" type="button"
      class="member ui-frame" :class="{ on: memberOf(modelValue) === m.name }"
      :aria-pressed="memberOf(modelValue) === m.name" :title="`使用${m.name}原皮`" @click="pick(m.name)"
    >
      <PetBust v-if="characters[m.name]" class="bust" :src="characters[m.name]!.bg" />
      <b><i :style="{ background: m.color }" aria-hidden="true"></i>{{ m.name }}</b>
      <small>{{ EN_NAMES[m.id] }}</small>
      <span v-if="memberOf(modelValue) === m.name" class="mark" aria-hidden="true"><Icon name="check" :size="11" /></span>
    </button>
  </div>
</template>

<style scoped>
.members {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 6px;
}
.member {
  --cut: var(--cut-s);
  height: 86px;
  padding: 3px 0 6px;
  box-sizing: border-box;
  border: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  background: var(--surface);
  box-shadow: inset 0 0 0 1.5px var(--line);
  color: var(--ink-2);
  cursor: pointer;
  transition: transform var(--dur-base) var(--ease-out);
}
.member:hover {
  transform: translateY(-2px);
}
.member:focus-visible {
  box-shadow: inset 0 0 0 2.5px var(--ink);
}
.member.on {
  background: var(--accent-surface);
  box-shadow: none;
  color: var(--on-accent-surface);
}
.bust {
  flex: none;
  width: 56px;
  height: 46px;
  filter: var(--contour);
}
b {
  margin-top: 2px;
  display: flex;
  align-items: center;
  gap: 4px;
  font: 800 var(--fs-strong)/1.1 var(--font);
  color: var(--ink);
}
.on b {
  color: inherit;
}
b i {
  flex: none;
  width: 4px;
  height: 11px;
  transform: skewX(var(--skew));
}
small {
  font: italic 800 var(--fs-caption)/1 var(--font-latin);
  letter-spacing: 0.06em;
}
.mark {
  position: absolute;
  right: 0;
  top: 0;
  width: 20px;
  height: 18px;
  background: var(--ink);
  color: var(--on-ink);
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
