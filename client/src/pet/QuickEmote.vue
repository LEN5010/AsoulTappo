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
  position: absolute; bottom: 0; z-index: 20; width: 236px; padding: 10px; box-sizing: border-box;
  border-radius: 20px; background: rgba(255, 252, 249, 0.98); box-shadow: 0 10px 30px rgba(50, 20, 30, 0.28), inset 0 0 0 1.5px rgba(var(--accent-rgb), 0.3);
  font-family: var(--font); animation: pop 200ms cubic-bezier(0.34, 1.5, 0.64, 1); cursor: default;
}
.pop.left { right: calc(100% + 12px); transform-origin: 100% 100%; }
.pop.right { left: calc(100% + 12px); transform-origin: 0 100%; }
.grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }
.emo { aspect-ratio: 1; border-radius: 14px; border: none; padding: 3px; background: var(--paper-2); cursor: pointer; transition: transform 120ms, background 120ms; }
.emo:hover { transform: scale(1.1); background: rgba(var(--accent-rgb), 0.18); }
.emo img { width: 100%; height: 100%; object-fit: contain; display: block; }
.foot { display: flex; gap: 6px; margin-top: 8px; }
.foot button { flex: 1; height: 30px; border-radius: 999px; border: none; cursor: pointer; font: inherit; font-size: 12px; font-weight: 700; display: inline-flex; align-items: center; justify-content: center; gap: 4px; }
.like { background: rgba(var(--accent-rgb), 0.16); color: var(--ink); }
.like img { width: 20px; height: 20px; object-fit: contain; }
.more { background: var(--paper-2); color: var(--ink-2); }
@keyframes pop { from { opacity: 0; transform: scale(0.85) translateY(6px); } }
</style>
