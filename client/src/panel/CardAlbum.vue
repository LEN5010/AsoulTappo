<script setup lang="ts">
// The album keeps card colors and plays visible owned videos; unowned cards stay still. An owned holo version
// (镭射款) is marked in the corner; under the pointer that one card leans and its foil moves.
import { computed, onBeforeUnmount, ref, watch, type ObjectDirective } from "vue";
import { usePageActive } from "../composables/usePageActive";
import { assetUrl, warmVideo } from "../asset";
import { albumCards, cardFrame, cardLabel, ownsHolo, playsCardVideo, TIER_LABEL, type AlbumFilter } from "../cards";
import HoloArt from "../holo/HoloArt.vue";
import HoloBadge from "../holo/HoloBadge.vue";
import { tiltTransform } from "../holo/shader";
import { useTilt } from "../holo/useTilt";
import { characterColor, type ManifestCard } from "../manifest";
import { collection } from "../stores/player";
import { reducedMotion } from "../stores/theme";
import Icon from "../ui/Icon.vue";

const props = defineProps<{ cards: ManifestCard[]; filter: AlbumFilter }>();
/** `inspect` hands over the cards as shown, for stepping in the detail; none under 未拥有, where nothing can be viewed. */
defineEmits<{ inspect: [card: ManifestCard, from: DOMRect | undefined, cards: ManifestCard[] | undefined] }>();

const owned = (c: ManifestCard) => collection.owned[`card:${c.id}`] ?? 0;
const holo = (c: ManifestCard) => ownsHolo(c, collection.owned);
/** Under 镭射 a card without its holo version is dimmed, even when the card itself is owned. */
const locked = (c: ManifestCard) => (props.filter === "holo" ? !holo(c) : !owned(c));

// One holo card at a time runs the shading: the one under the pointer, until it is level again after the pointer left.
const tilting = ref<string | null>(null);
const { tilt, lit, follow, leave, reset } = useTilt(undefined, () => (tilting.value = null));
function enter(card: ManifestCard) {
  if (playsCardVideo(card, owned(card), reducedMotion.value)) warmVideo(assetUrl(card.video));
  if (!holo(card) || tilting.value === card.id) return;
  reset();
  tilting.value = card.id;
}
function move(card: ManifestCard, e: PointerEvent) {
  if (tilting.value !== card.id) return;
  follow(e, (e.currentTarget as HTMLElement).querySelector(".art"));
}
function exit(card: ManifestCard) {
  if (tilting.value === card.id) leave();
}
/** The card opens in its detail, which covers the album: it goes level at once and lets its canvas go. */
function stopTilt() {
  reset();
  tilting.value = null;
}
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
const visible = computed(() => albumCards(props.cards, props.filter, collection.owned));
</script>

<template>
  <div class="album ui-scroll">
    <div class="grid">
      <button
        v-for="card in visible" :key="card.id" type="button"
        class="slot ui-tile" :class="[card.tier, { locked: locked(card), tilting: tilting === card.id }]"
        :title="card.name" data-rise
        @pointerenter="enter(card)" @pointermove="move(card, $event)" @pointerleave="exit(card)"
        @click="stopTilt(); $emit('inspect', card, owned(card) ? ($event.currentTarget as HTMLElement).querySelector('.art')?.getBoundingClientRect() : undefined, filter === 'missing' ? undefined : visible)"
      >
        <span
          class="art ui-frame ui-well" :class="[cardFrame(card), { framed: !!cardFrame(card) }]"
          :style="tilting === card.id ? { transform: tiltTransform(tilt, 600) } : undefined"
        >
          <HoloArt
            v-if="tilting === card.id && card.holo"
            :art="assetUrl(card.thumb)" :mask="assetUrl(card.holo.mask)" :shine="card.holo.shine" :tilt="tilt" :lit="lit" :alt="card.name"
          />
          <video
            v-else-if="playsCardVideo(card, owned(card), reducedMotion)" v-visible-video
            :data-src="assetUrl(card.video)" :poster="assetUrl(card.thumb)"
            :style="{ backgroundImage: `url(${assetUrl(card.thumb)})` }"
            :aria-label="card.name" autoplay loop muted playsinline preload="none"
          ></video>
          <img v-else :src="assetUrl(card.thumb)" :alt="card.name" loading="lazy" decoding="async" draggable="false" />
          <i v-if="card.tier !== 'normal'" class="tier ui-tag" :class="{ gold: card.tier === 'big' }">{{ TIER_LABEL[card.tier] }}</i>
          <b v-if="owned(card) > 1" class="count ui-tag dark" :class="{ beside: holo(card) }">×{{ owned(card) }}</b>
          <HoloBadge v-if="holo(card)" class="holo-mark" />
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
/* The thumbnail also sits behind the video: WebKit drops the poster while a video loads. */
.art video {
  background: center / cover no-repeat;
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
.count.beside {
  right: 27px;
}
.holo-mark {
  position: absolute;
  right: 8px;
  top: 6px;
  z-index: 1;
}
/* The leaning card: no zoom on top of the lean, and a shadow that lifts it off the page. */
.slot.tilting .art {
  z-index: 1;
  box-shadow: 0 12px 22px -12px rgba(var(--shadow-rgb), 0.55);
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
