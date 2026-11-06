<script setup lang="ts">
// The album keeps card colors and plays visible owned videos; unowned cards stay still.
import { computed, onBeforeUnmount, watch, type ObjectDirective } from "vue";
import { usePageActive } from "../composables/usePageActive";
import { assetUrl } from "../asset";
import { byTier, cardFrame, cardLabel, playsCardVideo, TIER_LABEL } from "../cards";
import { characterColor, type ManifestCard } from "../manifest";
import { collection } from "../stores/player";
import { reducedMotion } from "../stores/theme";
import Icon from "../ui/Icon.vue";

export type AlbumFilter = "all" | "hidden" | "owned" | "missing";

const props = defineProps<{ cards: ManifestCard[]; filter: AlbumFilter }>();
defineEmits<{ inspect: [card: ManifestCard, from?: DOMRect] }>();

const owned = (c: ManifestCard) => collection.owned[`card:${c.id}`] ?? 0;
const active = usePageActive();
const inView = new Set<HTMLVideoElement>();
const videos = new Set<HTMLVideoElement>();
const MAX_PLAYING = 3;
function scheduleVideos() {
  let playing = 0;
  for (const video of videos) {
    const play = active.value && inView.has(video) && playing < MAX_PLAYING;
    if (play) {
      playing++;
      if (!video.hasAttribute("src")) video.src = video.dataset.src!;
      void video.play().catch(() => {});
    } else if (video.hasAttribute("src")) {
      video.pause();
      video.removeAttribute("src");
      video.load();
    }
  }
}
const visibility = new IntersectionObserver((entries) => {
  for (const entry of entries) {
    if (entry.isIntersecting) inView.add(entry.target as HTMLVideoElement);
    else inView.delete(entry.target as HTMLVideoElement);
  }
  scheduleVideos();
});
const vVisibleVideo: ObjectDirective<HTMLVideoElement> = {
  mounted(video) { videos.add(video); visibility.observe(video); },
  beforeUnmount(video) {
    visibility.unobserve(video); inView.delete(video); videos.delete(video);
    video.pause(); video.removeAttribute("src"); video.load();
    scheduleVideos();
  },
};
watch(active, scheduleVideos);
onBeforeUnmount(() => visibility.disconnect());
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
        <span class="art ui-frame ui-well" :class="[cardFrame(card), { framed: !!cardFrame(card) }]">
          <video
            v-if="playsCardVideo(card, owned(card), reducedMotion)" v-visible-video
            :data-src="assetUrl(card.video)" :poster="assetUrl(card.thumb)"
            :aria-label="card.name" autoplay loop muted playsinline preload="none"
          ></video>
          <img v-else :src="assetUrl(card.thumb)" :alt="card.name" loading="lazy" decoding="async" draggable="false" />
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
  padding: 12px 8px 10px 0;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(106px, 1fr));
  gap: 14px 12px;
}
.slot {
  --well-ratio: 2 / 3;
  --radius: var(--radius-m);
}
/* Photocards: hidden and dance cards sit in their metal frame, the rest are bare. */
.art {
  padding: 0;
  background: var(--c-100);
}
.art.framed {
  padding: 4px;
  background: var(--frame-fill) var(--frame-at) / var(--frame-size);
}
.art.framed img,
.art.framed video {
  border-radius: calc(var(--radius-m) - 3px);
}
.art img,
.art video {
  position: relative;
  width: 100%;
  height: 100%;
  max-width: none;
  max-height: none;
  object-fit: cover;
  filter: none;
}
.slot.locked .art img,
.slot.locked .art video {
  filter: var(--dim);
  transition: transform var(--dur-base) var(--ease-out), filter var(--dur-base);
}
/* Unowned cards are a dimmed original that lights up under the pointer. */
.slot.locked:hover .art img,
.slot.locked:hover .art video {
  filter: none;
}
/* A photo fills its frame, so it zooms in place rather than lifting out of it. */
.slot:hover .art img,
.slot:hover .art video {
  transform: scale(1.04);
}
/* Unowned: the frame stays plain until the pointer lights it, as the ring did before. */
.slot.locked:not(:hover) .art.framed {
  background: var(--c-200);
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
  border-radius: var(--radius-s);
  background: var(--c-800);
  color: #fff;
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
}
.slot.locked .name b {
  color: var(--ink-2);
}
.slot.locked .name small {
  color: var(--ink-3);
}
</style>
