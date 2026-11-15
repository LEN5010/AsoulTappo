<script setup lang="ts">
// Card detail: the artwork beside its facts. Videos start with sound when the card audio setting is on.
// With the album's cards it steps through the owned ones, and the artwork opens in a full-panel viewer.
import { computed, nextTick, onMounted, ref, watch, type ObjectDirective } from "vue";
import { usePageActive } from "../composables/usePageActive";
import { assetUrl, warmVideo } from "../asset";
import { cardFrame, cardLabel, playsCardVideo, poolName, TIER_LABEL } from "../cards";
import { characterColor, manifest, type ManifestCard } from "../manifest";
import { economy } from "../stores/economy";
import { getItem } from "../items";
import { MAX_SHOWCASE } from "../net/protocol";
import { collection } from "../stores/player";
import { settings } from "../stores/settings";
import { ui } from "../stores/ui";
import CraftAction from "../ui/CraftAction.vue";
import { reducedMotion } from "../stores/theme";
import Icon from "../ui/Icon.vue";
import Modal from "../ui/Modal.vue";
import { flyFrom } from "../ui/motion";
import { stepIndex } from "./album";
import ArtViewer from "./ArtViewer.vue";
import StepKeys from "./StepKeys.vue";

/** `cards` is the album as the grid shows it; without it there is nothing to step to. */
const props = defineProps<{ card: ManifestCard; cards?: readonly ManifestCard[]; from?: DOMRect; preview?: boolean }>();
const emit = defineEmits<{ close: []; step: [card: ManifestCard] }>();

const pageActive = usePageActive();
const ownedOf = (card: ManifestCard) => collection.owned[`card:${card.id}`] ?? 0;
const count = computed(() => ownedOf(props.card));
const animated = computed(() => playsCardVideo(props.card, count.value, reducedMotion.value, props.preview));
const item = computed(() => getItem(`card:${props.card.id}`)!);
const label = computed(() => cardLabel(props.card));
const pool = computed(() => poolName(manifest.series.find((s) => s.id === props.card.series)?.name ?? props.card.series));
/** On the profile room members open: owned cards only, at most MAX_SHOWCASE. */
const shown = computed(() => settings.showcase.includes(props.card.id));
const showcaseFull = computed(() => !shown.value && settings.showcase.length >= MAX_SHOWCASE);
function toggleShowcase() {
  if (shown.value) settings.showcase = settings.showcase.filter((id) => id !== props.card.id);
  else if (!showcaseFull.value) settings.showcase = [...settings.showcase, props.card.id];
}

// Unowned cards only have a locked thumbnail, so stepping passes over them.
const neighbour = (delta: -1 | 1) => {
  const list = props.cards;
  if (!list) return undefined;
  return list[stepIndex(list, props.card.id, (c) => c.id, delta, (c) => ownedOf(c) > 0)];
};
const prevCard = computed(() => neighbour(-1));
const nextCard = computed(() => neighbour(1));
function step(delta: -1 | 1) {
  const card = delta < 0 ? prevCard.value : nextCard.value;
  if (!card) return;
  resume = { at: 0, paused: false };
  emit("step", card);
}
// The full artwork comes from the server: fetch the neighbours ahead of a step.
const warmed = new Set<string>();
watch([prevCard, nextCard], (cards) => {
  for (const card of cards) {
    if (!card) continue;
    if (playsCardVideo(card, ownedOf(card), reducedMotion.value)) warmVideo(assetUrl(card.video));
    else if (!warmed.has(card.id)) {
      warmed.add(card.id);
      new Image().src = assetUrl(card.full);
    }
  }
}, { immediate: true });

// Modal teleports with `defer`, so the artwork exists only after the next tick. The detail stays mounted
// while stepping, so the flight from the album runs on the first open only.
const artEl = ref<HTMLElement>();
onMounted(async () => {
  await nextTick();
  if (props.from && artEl.value) flyFrom(props.from, artEl.value, assetUrl(props.card.thumb));
});

const viewable = computed(() => props.preview || count.value > 0);
const viewing = ref(false);
watch(viewable, (v) => !v && (viewing.value = false));

// One video at a time: the detail's or the viewer's. Moving between them keeps its place and pause.
const video = ref<HTMLVideoElement>();
const paused = ref(false);
const muted = ref(!settings.cardAudio);
let resume = { at: 0, paused: false };
function setViewing(on: boolean) {
  const v = video.value;
  resume = v ? { at: v.currentTime, paused: v.paused } : { at: 0, paused: false };
  viewing.value = on;
}
/** Plays with the current sound toggle; a webview that refuses audible playback mutes it, as playCardVideo does. */
function start(v: HTMLVideoElement) {
  v.muted = muted.value;
  v.volume = settings.volume;
  const at = resume.at;
  if (at && v.readyState >= HTMLMediaElement.HAVE_METADATA) v.currentTime = at;
  else if (at) v.addEventListener("loadedmetadata", () => (v.currentTime = at), { once: true });
  paused.value = resume.paused;
  if (resume.paused) return;
  v.play().catch(() => {
    if (v.muted) return;
    v.muted = muted.value = true;
    void v.play().catch(() => {});
  });
}
watch(video, (v) => v && start(v));
function togglePlay() {
  const v = video.value;
  if (!v) return;
  if (v.paused) void v.play();
  else v.pause();
}
/** Lets go of a video's decoder when its card or view changes; WebKit holds on to it otherwise. */
const vReleaseVideo: ObjectDirective<HTMLVideoElement> = {
  beforeUnmount(v) {
    v.pause();
    v.removeAttribute("src");
    v.load();
  },
};
</script>

<template>
  <Modal :title="card.name" wide :still="!!from" :covered="viewing" @close="emit('close')">
    <div class="detail" :class="card.tier">
      <div ref="artEl" class="art ui-frame" :class="[cardFrame(card), { framed: !!cardFrame(card), locked: !preview && !count }]">
          <video
            v-if="animated && pageActive && !viewing" :key="card.id" ref="video" v-release-video :src="assetUrl(card.video)" :poster="assetUrl(card.thumb)"
            :style="{ backgroundImage: `url(${assetUrl(card.thumb)})` }"
            :muted="muted" loop playsinline
            @play="paused = false" @pause="paused = true"
          ></video>
          <img v-else :key="card.id" :src="assetUrl(viewable && !(animated && viewing) ? card.full : card.thumb)" :style="{ backgroundImage: `url(${assetUrl(card.thumb)})` }" :alt="card.name" />

        <button v-if="viewable" type="button" class="zoom" aria-label="放大" @click="setViewing(true)"></button>
        <StepKeys v-if="cards" :prev="!!prevCard" :next="!!nextCard" :keyboard="!viewing" @step="step" />
        <div v-if="animated" class="controls">
          <button type="button" class="ui-btn small ghost" :aria-label="paused ? '播放' : '暂停'" @click="togglePlay">
            <Icon :name="paused ? 'play' : 'pause'" :size="14" />
          </button>
          <button type="button" class="ui-btn small ghost" :aria-label="muted ? '打开声音' : '关闭声音'" :aria-pressed="!muted" @click="muted = !muted">
            <Icon :name="muted ? 'mute' : 'sound'" :size="14" />
          </button>
        </div>
      </div>

      <div class="info">
        <span class="ui-tag" :class="{ gold: card.tier === 'big', dark: card.tier === 'normal' }">{{ TIER_LABEL[card.tier] }}</span>
        <h3>{{ label.title }}</h3>
        <p class="who"><i :style="{ background: characterColor(card.characters[0] ?? '') }" aria-hidden="true"></i>{{ label.who }}</p>
        <dl>
          <div><dt>卡池</dt><dd>{{ pool }}</dd></div>
          <div><dt>持有</dt><dd :class="{ missing: !count }">{{ count ? `×${count}` : "未拥有" }}</dd></div>
          <div v-if="card.video"><dt>卡面</dt><dd>{{ card.still ? "有声" : "动态" }}</dd></div>
        </dl>
        <CraftAction :key="item.id" :item="item" />
        <button
          v-if="count && !preview" type="button" class="ui-btn showcase" :disabled="showcaseFull"
          :title="showcaseFull ? '主页最多展示 3 张，先取下一张' : undefined" :aria-pressed="shown" @click="toggleShowcase"
        >
          <Icon :name="shown ? 'check' : 'plus'" :size="15" />{{ shown ? "取消展示" : showcaseFull ? "展示位已满" : "展示到主页" }}
        </button>
        <button v-if="!count && !economy?.craftCost[card.rarity] && !preview" type="button" class="ui-btn primary resonance" @click="ui.page = 'resonance'; emit('close')">去共鸣获取</button>
      </div>
    </div>

    <template #front>
      <ArtViewer
        v-if="viewing" :id="card.id" :ratio="2 / 3" :label="card.name"
        :steps="!!cards" :prev="!!prevCard" :next="!!nextCard"
        @step="step" @close="setViewing(false)"
      >
        <video
          v-if="animated && pageActive" :key="card.id" ref="video" v-release-video :src="assetUrl(card.video)" :poster="assetUrl(card.thumb)"
          :style="{ backgroundImage: `url(${assetUrl(card.thumb)})` }"
          :muted="muted" loop playsinline
          @play="paused = false" @pause="paused = true"
        ></video>
        <img v-else :key="card.id" :src="assetUrl(card.full)" :style="{ backgroundImage: `url(${assetUrl(card.thumb)})` }" :alt="card.name" draggable="false" />
        <template v-if="animated" #controls>
          <button type="button" class="ui-btn small ghost" :aria-label="paused ? '播放' : '暂停'" @click="togglePlay">
            <Icon :name="paused ? 'play' : 'pause'" :size="14" />
          </button>
          <button type="button" class="ui-btn small ghost" :aria-label="muted ? '打开声音' : '关闭声音'" :aria-pressed="!muted" @click="muted = !muted">
            <Icon :name="muted ? 'mute' : 'sound'" :size="14" />
          </button>
        </template>
      </ArtViewer>
    </template>
  </Modal>
</template>

<style scoped>
.detail {
  display: flex;
  gap: 24px;
  align-items: stretch;
}
.art {
  --radius: var(--radius-l);
  flex: none;
  height: min(440px, calc(100cqh - 120px));
  aspect-ratio: 2 / 3;
  box-sizing: border-box;
  background: var(--c-100);
}
/* Hidden and dance cards sit in their metal frame, as in the album and on the resonance page. */
.art.framed {
  padding: 6px;
  background: var(--frame-fill) var(--frame-at) / var(--frame-size);
}
.art video,
.art img {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
  background: center / cover no-repeat;
}
.art.framed video,
.art.framed img {
  border-radius: calc(var(--radius-l) - 5px);
}
.art.locked video,
.art.locked img {
  filter: brightness(0.74);
  transition: filter var(--dur-base);
}
/* The whole artwork is the key into the viewer; the step and video keys sit above it. */
.zoom {
  position: absolute;
  inset: 0;
  z-index: 3;
  padding: 0;
  border: 0;
  background: none;
  cursor: zoom-in;
}
.zoom:focus-visible {
  outline: 2px solid var(--focus, var(--ink));
  outline-offset: -2px;
  border-radius: inherit;
}
.controls {
  position: absolute;
  left: 12px;
  bottom: 12px;
  z-index: 4;
  display: flex;
  gap: 8px;
}
/* Two identical flat keys on a frosted face, so they read over any artwork. The icons carry the
   state, so the sound key ignores the pressed look other toggles use. */
.controls .ui-btn,
.controls .ui-btn[aria-pressed]:not(:disabled) {
  --key-top: rgba(255, 255, 255, 0.86);
  --key-bottom: rgba(255, 255, 255, 0.86);
  --key-y: 0px;
  --key-lip-h: 0px;
  width: 32px;
  padding: 0;
  color: var(--ink);
  backdrop-filter: blur(6px);
}
.controls .ui-btn:hover:not(:disabled) {
  --key-top: #fff;
  --key-bottom: #fff;
}
.controls .ui-btn:active:not(:disabled) {
  --key-top: var(--c-100);
  --key-bottom: var(--c-100);
}

.info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  padding-top: 4px;
}
h3 {
  margin: 6px 0 2px;
  font: 800 clamp(22px, 3cqw, 28px)/1.25 var(--font);
  text-wrap: balance;
}
.who {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--fs-body);
  font-weight: 700;
  color: var(--ink);
}
.who i {
  width: 4px;
  height: 11px;
}
dl {
  width: 100%;
  margin: 14px 0 0;
}
dl > div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
  border-top: 1px solid var(--c-100);
  font-size: var(--fs-body);
}
dt {
  color: var(--ink-3);
  font-weight: 700;
}
dd {
  margin: 0;
  font-weight: 700;
  color: var(--ink);
}
dd.missing {
  color: var(--ink-3);
}
.resonance, .showcase { align-self: stretch; margin-top: auto; }
@container panel (max-width: 660px) {
  .detail { gap: 16px; }
  .art { max-width: 44%; height: auto; align-self: flex-start; }
}
</style>
