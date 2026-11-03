<script setup lang="ts">
import { computed } from "vue";
import { getEmote } from "../manifest";
import { assetUrl } from "../asset";
import { skin } from "../stores/theme";
import Icon from "../ui/Icon.vue";

const props = defineProps<{ keys: string[]; side: "left" | "right" }>();
defineEmits<{ pick: [key: string]; more: [] }>();
const list = computed(() => props.keys.map((k) => ({ key: k, e: getEmote(k) })).filter((x) => x.e));
</script>

<template>
  <div class="pop" :class="side" data-hit data-no-drag role="menu" aria-label="快捷表情">
    <div class="grid">
      <button v-for="x in list" :key="x.key" type="button" class="emo" role="menuitem" :title="x.e!.name" @click="$emit('pick', x.key)">
        <img :src="assetUrl(x.e!.img)" :alt="x.e!.name" draggable="false" />
      </button>
    </div>
    <div class="foot">
      <button type="button" class="like" role="menuitem" title="点赞" @click="$emit('pick', 'thumbup')">
        <img v-if="skin.icons.dynamic" :src="skin.icons.dynamic.s || skin.icons.dynamic.n" alt="" draggable="false" />
        <span>点赞</span>
      </button>
      <button type="button" class="more" role="menuitem" @click="$emit('more')"><Icon name="grid" :size="14" />更多表情</button>
    </div>
  </div>
</template>

<style scoped>
/* beside the pet, so the bubble on its head stays visible while sending */
.pop {
  position: absolute; bottom: 0; z-index: 20; width: 228px; padding: 8px; box-sizing: border-box;
  border-radius: var(--r-xl); background: rgba(252, 251, 250, 0.99); border: 1px solid var(--line-2); box-shadow: 0 10px 28px rgba(43, 35, 38, 0.2);
  font-family: var(--font); animation: pop 140ms ease-out; cursor: default;
}
.pop.left { right: calc(100% + 12px); transform-origin: 100% 100%; }
.pop.right { left: calc(100% + 12px); transform-origin: 0 100%; }
.grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 4px; }
.emo { aspect-ratio: 1; border-radius: var(--r-m); border: none; padding: 3px; background: none; cursor: pointer; transition: background 120ms; }
.emo:hover { background: var(--paper-2); }
.emo img { width: 100%; height: 100%; object-fit: contain; display: block; }
.foot { display: flex; gap: 4px; margin-top: 6px; padding-top: 6px; border-top: 1px solid var(--line); }
.foot button { flex: 1; height: 28px; border-radius: var(--r-m); border: none; cursor: pointer; font: inherit; font-size: 12px; font-weight: 600; display: inline-flex; align-items: center; justify-content: center; gap: 4px; }
.like { background: rgba(var(--accent-rgb), 0.14); color: var(--ink); }
.like:hover { background: rgba(var(--accent-rgb), 0.22); }
.like img { width: 20px; height: 20px; object-fit: contain; }
.more { background: none; color: var(--ink-2); }
.more:hover { background: var(--paper-2); color: var(--ink); }
@keyframes pop { from { opacity: 0; transform: translateY(4px); } }
</style>
