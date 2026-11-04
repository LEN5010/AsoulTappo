<script setup lang="ts">
import { computed } from "vue";
import { assetUrl } from "../asset";
import { getItem, RARITY_LABEL } from "../items";
import { characterColor, type Rarity } from "../manifest";
import type { Drop } from "../net/api";
import CardBack from "./CardBack.vue";

const props = defineProps<{ drop: Drop; settled: boolean }>();
defineEmits<{ done: [] }>();
const item = computed(() => getItem(props.drop.item)!);
</script>

<template>
  <div class="emote-spot" :class="[drop.rarity, { settled }]">
    <i class="halo" aria-hidden="true"></i>
    <div class="row">
      <div class="flip" @animationend.self="$emit('done')">
        <div class="reverse ui-frame"><CardBack /></div>
        <div class="face ui-frame">
          <span class="ui-tag">{{ RARITY_LABEL[drop.rarity as Rarity] }}</span>
          <img :src="assetUrl(item.art)" :alt="item.name" draggable="false" />
          <small>表情贴纸</small>
        </div>
      </div>
      <div class="facts">
        <span class="ui-tag">{{ RARITY_LABEL[drop.rarity as Rarity] }}表情</span>
        <h3>{{ item.name }}</h3>
        <p><i :style="{ background: characterColor(item.characters[0]!) }"></i>{{ item.group }}</p>
        <b v-if="drop.new" class="fresh">NEW</b>
        <b v-else>已拥有 ×{{ drop.count }}<template v-if="drop.shards"> · 碎片 +{{ drop.shards }}</template></b>
      </div>
    </div>
  </div>
</template>

<style scoped>
.emote-spot {
  position: absolute;
  inset: 0;
  overflow: hidden;
  background: var(--grad-sky);
  color: var(--ink);
}
.halo {
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse at 35% 50%, var(--surface), transparent 65%);
  opacity: 0.65;
}
.row {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 44px;
  height: 100%;
  padding: 50px 40px;
  box-sizing: border-box;
}
.flip {
  position: relative;
  height: min(420px, 70cqh);
  aspect-ratio: 2 / 3;
  flex: none;
  transform-style: preserve-3d;
  animation: flip 560ms var(--ease-out) backwards;
}
.face, .reverse {
  position: absolute;
  inset: 0;
  backface-visibility: hidden;
  overflow: hidden;
  --radius: var(--radius-l);
}
.face {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  padding: 20px;
  background: var(--surface);
  box-shadow: inset 0 0 0 2px var(--line-2), var(--glow-s);
}
.face img {
  width: 100%;
  height: 68%;
  object-fit: contain;
  filter: var(--contour);
}
.face small {
  color: var(--ink-3);
  font-size: var(--fs-label);
  font-weight: 800;
}
.reverse { transform: rotateY(180deg); }
.facts {
  flex: 0 1 300px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
}
h3 {
  margin: 2px 0;
  font: 800 var(--fs-display)/1.15 var(--font);
}
p {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  color: var(--ink-2);
  font-size: var(--fs-body);
}
p i { width: 5px; height: 14px; flex: none; }
.fresh {
  margin-top: 12px;
  font: 800 var(--fs-title)/1 var(--font-latin);
  letter-spacing: 0.06em;
  color: var(--accent-deep);
}
.settled .flip { animation: none; }
@keyframes flip {
  from { transform: perspective(900px) rotateY(180deg) scale(0.9); }
  to { transform: perspective(900px) rotateY(0) scale(1); }
}
@container panel (max-height: 560px) {
  .row { gap: 28px; }
  h3 { font-size: var(--fs-title); }
}
</style>
