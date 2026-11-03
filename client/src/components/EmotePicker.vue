<script setup lang="ts">
import { computed, ref } from "vue";
import { EMOTES, emoteGroups, emoteView, THUMBUP } from "../emotes";
import { manifest, resolveAsset } from "../manifest";
import { toHttpBase } from "../net/protocol";
import { settings } from "../stores/settings";
import { reducedMotion, skin } from "../stores/theme";

defineProps<{ disabledHint?: string }>();
const emit = defineEmits<{ pick: [key: string] }>();

const groups = emoteGroups();
const charIdx = ref(Math.max(0, groups.findIndex((g) => g.character.name === settings.character)));
const group = computed(() => groups[charIdx.value]);
const setIdx = ref(0);
const set = computed(() => group.value.sets[Math.min(setIdx.value, group.value.sets.length - 1)]);
const base = computed(() => toHttpBase(settings.serverUrl));
const img = (ref_: string) => resolveAsset(ref_, base.value, import.meta.env.BASE_URL);
const like = computed(() =>
  emoteView(THUMBUP, { serverBase: base.value, thumbup: skin.value.thumbup, reducedMotion: reducedMotion.value, appBase: import.meta.env.BASE_URL }),
);
const total = manifest.emoteSets.reduce((n, s) => n + s.emotes.length, 0);

function pickChar(i: number) {
  charIdx.value = i;
  setIdx.value = 0;
}
</script>

<template>
  <div class="picker" :title="disabledHint">
    <div class="quick">
      <button type="button" class="like" title="点赞" @click="emit('pick', THUMBUP)">
        <img v-if="like.img" :src="like.img" alt="点赞" draggable="false" /><span v-else>{{ like.text }}</span>
      </button>
      <button v-for="e in EMOTES" :key="e.key" type="button" class="glyph" :title="e.label" @click="emit('pick', e.key)">{{ e.glyph }}</button>
    </div>
    <div class="chars" role="tablist" aria-label="角色表情">
      <button
        v-for="(g, i) in groups" :key="g.character.id" type="button" role="tab" :aria-selected="i === charIdx"
        class="chip" :class="{ on: i === charIdx }" :style="{ '--c': g.character.color }" @click="pickChar(i)"
      >{{ g.character.name }}</button>
    </div>
    <div v-if="group.sets.length > 1" class="sets">
      <button
        v-for="(s, i) in group.sets" :key="s.id" type="button" class="set" :class="{ on: s.id === set.id }" :title="s.name" @click="setIdx = i"
      >{{ s.name }}</button>
    </div>
    <div class="grid" role="group" :aria-label="set.name">
      <button v-for="e in set.emotes" :key="e.key" type="button" class="em" :title="e.name" @click="emit('pick', e.key)">
        <img :src="img(e.img)" :alt="e.name" loading="lazy" draggable="false" />
      </button>
    </div>
    <small class="count">共 {{ total }} 个表情</small>
  </div>
</template>

<style scoped>
.picker { display: flex; flex-direction: column; gap: 6px; }
.quick { display: flex; flex-wrap: wrap; gap: 3px; }
button { font-family: inherit; cursor: pointer; }
.glyph, .like { width: 28px; height: 28px; padding: 0; font-size: 16px; border-radius: 8px; border: 1px solid rgba(0, 0, 0, 0.08); background: rgba(255, 255, 255, 0.7); display: grid; place-items: center; }
.like img { width: 24px; height: 24px; object-fit: contain; }
.like { border-color: rgba(var(--accent-rgb), 0.5); }
.chars { display: flex; gap: 3px; }
.chip { flex: 1; padding: 3px 0; font-size: 11px; border-radius: 999px; border: 1px solid var(--c); color: var(--c); background: rgba(255, 255, 255, 0.55); }
.chip.on { background: var(--c); color: #fff; }
.sets { display: flex; gap: 3px; overflow-x: auto; padding-bottom: 2px; scrollbar-width: thin; }
.set { flex: none; padding: 2px 8px; font-size: 11px; border-radius: 6px; border: 1px solid transparent; background: rgba(0, 0, 0, 0.05); color: inherit; white-space: nowrap; }
.set.on { background: rgba(var(--accent-rgb), 0.16); border-color: rgba(var(--accent-rgb), 0.6); }
.grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px; max-height: 150px; overflow-y: auto; padding: 2px; scrollbar-width: thin; }
.em { padding: 2px; border-radius: 8px; border: 1px solid transparent; background: rgba(255, 255, 255, 0.5); aspect-ratio: 1; display: grid; place-items: center; }
.em img { width: 100%; height: 100%; object-fit: contain; }
.em:hover { background: rgba(255, 255, 255, 0.95); border-color: rgba(var(--accent-rgb), 0.5); }
.em:active { transform: scale(0.92); }
.count { color: rgba(0, 0, 0, 0.4); font-size: 10px; }
</style>
