<script setup lang="ts">
// The album view of one pool: every card in a slot, cards not owned yet stay gray until hovered.
import { computed } from "vue";
import { assetUrl } from "../asset";
import { byTier, cardLabel, TIER_LABEL } from "../cards";
import { characterColor, type ManifestCard } from "../manifest";
import { collection } from "../stores/player";
import Icon from "../ui/Icon.vue";

export type AlbumFilter = "all" | "hidden" | "owned" | "missing";

const props = defineProps<{ cards: ManifestCard[]; filter: AlbumFilter }>();
defineEmits<{ inspect: [card: ManifestCard, from?: DOMRect] }>();

const owned = (c: ManifestCard) => collection.owned[`card:${c.id}`] ?? 0;
const visible = computed(() =>
  props.cards
    .filter((card) => {
      if (props.filter === "owned") return owned(card) > 0;
      if (props.filter === "missing") return owned(card) === 0;
      if (props.filter === "hidden") return card.tier !== "normal";
      return true;
    })
    .sort(byTier),
);
</script>

<template>
  <div class="album ui-scroll">
    <div class="grid">
      <button
        v-for="card in visible" :key="card.id" type="button"
        class="slot ui-tile" :class="[card.tier, { locked: !owned(card) }]"
        :title="card.name" data-rise
        @click="$emit('inspect', card, owned(card) ? ($event.currentTarget as HTMLElement).querySelector('.art')?.getBoundingClientRect() : undefined)"
      >
        <span class="art ui-frame ui-well" :class="{ 'ui-ring': card.tier !== 'normal' }">
          <img :src="assetUrl(card.thumb)" :alt="card.name" loading="lazy" decoding="async" draggable="false" />
          <i v-if="card.tier !== 'normal'" class="tier ui-tag" :class="{ gold: card.tier === 'big' }">{{ TIER_LABEL[card.tier] }}</i>
          <b v-if="owned(card) > 1" class="count ui-tag dark">×{{ owned(card) }}</b>
          <span v-if="card.video && owned(card)" class="live" title="动态卡面"><Icon name="play" :size="9" /></span>
        </span>
        <span class="name">
          <b>{{ cardLabel(card).title }}</b>
          <small><i :style="{ background: characterColor(card.characters[0] ?? '') }" aria-hidden="true"></i>{{ cardLabel(card).who }}</small>
        </span>
      </button>
    </div>
    <p v-if="!visible.length" class="ui-empty">当前筛选下没有卡牌</p>
  </div>
</template>

<style scoped>
.album {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 2px 8px 10px 0;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(106px, 1fr));
  gap: 14px 12px;
}
.slot {
  --well-ratio: 2 / 3;
  --cut: var(--cut-m);
}
.art {
  padding: 0;
  background: var(--accent-tint);
  box-shadow: none;
}
.art img {
  position: relative;
  width: 100%;
  height: 100%;
  max-width: none;
  max-height: none;
  object-fit: cover;
  filter: none;
}
.slot.locked .art img {
  filter: grayscale(1) opacity(0.7);
  transition: transform var(--dur-base) var(--ease-out), filter var(--dur-base);
}
.slot.locked:hover .art img {
  filter: none;
}
.slot.small .art {
  --ring: var(--accent);
}
.slot.big .art {
  --ring: var(--gold);
}
.slot.locked:not(:hover) .art {
  --ring: var(--line-2);
}
.tier {
  position: absolute;
  left: 6px;
  top: 5px;
  z-index: 1;
  line-height: 16px;
  padding: 0 5px;
}
.count {
  position: absolute;
  right: 7px;
  top: 5px;
  z-index: 1;
  line-height: 16px;
  padding: 0 5px;
}
.live {
  position: absolute;
  left: 7px;
  bottom: 7px;
  z-index: 1;
  width: 22px;
  height: 16px;
  background: var(--ink);
  color: var(--on-ink);
  transform: skewX(var(--skew));
  display: flex;
  align-items: center;
  justify-content: center;
}
.name {
  width: 100%;
  margin-top: 6px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  text-align: center;
}
.name b,
.name small {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.name b {
  font-size: var(--fs-label);
  font-weight: 800;
}
.name small {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: var(--fs-caption);
  font-weight: 700;
  color: var(--ink-2);
}
.name i {
  flex: none;
  width: 3px;
  height: 9px;
  transform: skewX(var(--skew));
}
.slot.locked .name b {
  color: var(--ink-2);
}
.slot.locked .name small {
  color: var(--ink-3);
}
</style>
