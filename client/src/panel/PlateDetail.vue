<script setup lang="ts">
// A name plate before wearing it: its picture, the set that unlocks it, and the own pet with the plate under it
// as partners see it. A card plate shows the card and its cards; a sweep plate its picture and its emotes.
import { computed } from "vue";
import { assetUrl } from "../asset";
import { cardFrame, poolName } from "../cards";
import { characterColor, emoteCover, manifest, type ManifestCard, type ManifestEmote } from "../manifest";
import { collection } from "../stores/player";
import { settings } from "../stores/settings";
import { ui } from "../stores/ui";
import { pet } from "../stores/pet";
import Modal from "../ui/Modal.vue";
import Icon from "../ui/Icon.vue";
import PetView from "../pet/PetView.vue";
import NamePlate from "../pet/NamePlate.vue";
import { nameBand, plateNeeds, plateSet, plateSize, type Plate } from "../pet/plates";

const props = defineProps<{ plate: Plate }>();
const emit = defineEmits<{ close: [] }>();

/** The pet's size in the preview, as in the skin preview. */
const SCALE = 0.82;
const size = plateSize(SCALE);
const font = nameBand(SCALE).font;
const owns = (item: string) => !!collection.owned[item];
const has = (c: ManifestCard) => owns(`card:${c.id}`);
const hasEmote = (e: ManifestEmote) => owns(`emote:${e.key}`);
const card = computed(() => (props.plate.kind === "card" ? props.plate.card : null));
const owned = computed(() => !card.value || has(card.value));
/** The cards to collect, the big hidden card first. */
const set = computed(() => (card.value ? plateSet(card.value) : []));
/** The emotes to collect: owned ones first, each group in set order. */
const emotes = computed(() => {
  const all = props.plate.kind === "sweep" ? props.plate.emotes : [];
  return [...all.filter(hasEmote), ...all.filter((e) => !hasEmote(e))];
});
const needs = computed(() => plateNeeds(props.plate));
const collected = computed(() => needs.value.filter(owns).length);
const unlocked = computed(() => collected.value === needs.value.length);
const worn = computed(() => settings.plate === props.plate.id);
const nick = computed(() => settings.nick.trim() || "匿名小面包");
const pool = computed(() =>
  card.value ? poolName(manifest.series.find((s) => s.id === card.value!.series)?.name ?? card.value.series) : "");
function go(page: "resonance" | "park") { ui.page = page; emit("close"); }
</script>

<template>
  <Modal :title="plate.name" wide @close="emit('close')">
    <div class="plate-detail">
      <div v-if="card" class="art ui-frame frame-gold" :class="{ locked: !owned }">
        <img :src="assetUrl(owned ? card.full : card.thumb)" :style="{ backgroundImage: `url(${assetUrl(card.thumb)})` }" :alt="card.name" />
      </div>
      <div v-else-if="plate.kind === 'sweep'" class="art ui-frame frame-gold sweep">
        <img :src="plate.sweep.src" :alt="plate.name" />
      </div>
      <div class="info">
        <span class="ui-tag gold">铭牌</span>
        <h3>{{ plate.name }}</h3>
        <p v-if="card" class="member"><i :style="{ background: characterColor(card.characters[0]!) }"></i>{{ card.characters.join(" / ") }}</p>
        <dl>
          <div v-if="card"><dt>系列</dt><dd>{{ pool }}</dd></div>
          <div><dt>解锁</dt><dd>{{ unlocked ? '已解锁' : `${collected} / ${needs.length}` }}</dd></div>
        </dl>
        <ul v-if="card" class="set" :style="{ '--n': set.length }" aria-label="解锁需要的卡片">
          <li
            v-for="c in set" :key="c.id" :class="[cardFrame(c), { missing: !has(c) }]"
            :title="`${c.name}：${has(c) ? '已拥有' : '未获得'}`"
          >
            <img :src="assetUrl(c.thumb)" :alt="c.name" loading="lazy" decoding="async" />
          </li>
        </ul>
        <ul v-else class="emotes" aria-label="解锁需要的表情">
          <li v-for="e in emotes" :key="e.key" :class="{ missing: !hasEmote(e) }" :title="`${e.name}：${hasEmote(e) ? '已拥有' : '未获得'}`">
            <img :src="assetUrl(emoteCover(e.key))" :alt="e.name" loading="lazy" decoding="async" draggable="false" />
          </li>
        </ul>
        <div class="live-preview">
          <PetView :character="settings.character" :scale="SCALE" :key-down="pet.keyDown" :mouse-dx="pet.dx" :mouse-dy="pet.dy" :left-down="pet.left" :right-down="pet.right" />
          <NamePlate :card="plate.id" :nick="nick" :color="characterColor(settings.character)" :width="size.width" :height="size.height" :font="font" />
          <small>桌宠预览</small>
        </div>
        <button v-if="unlocked" type="button" class="ui-btn primary equip" :disabled="worn" @click="settings.plate = plate.id"><Icon name="check" :size="15" />{{ worn ? '使用中' : '使用铭牌' }}</button>
        <button v-else-if="card" type="button" class="ui-btn primary equip" @click="go('resonance')"><Icon name="spark" :size="15" />去共鸣获取</button>
        <button v-else-if="ui.page !== 'park'" type="button" class="ui-btn primary equip" @click="go('park')"><Icon name="ticket" :size="15" />去刮刮乐</button>
      </div>
    </div>
  </Modal>
</template>

<style scoped>
.plate-detail { display: grid; grid-template-columns: minmax(0, .9fr) minmax(0, 1fr); align-items: stretch; gap: 24px; }
.art { --radius: var(--radius-l); align-self: center; width: 100%; aspect-ratio: 2 / 3; box-sizing: border-box; padding: 6px; background: var(--frame-fill) var(--frame-at) / var(--frame-size); }
.art img { width: 100%; height: 100%; display: block; object-fit: cover; background: center / cover no-repeat; border-radius: calc(var(--radius-l) - 5px); }
.art.locked img { filter: brightness(0.74); }
/* A cut-out picture on the coral it stands on in the plate. */
.art.sweep img { background: var(--c-500); }
.info { display: flex; min-width: 0; align-items: flex-start; flex-direction: column; gap: 9px; padding-top: 4px; }
h3 { margin: 6px 0 2px; font: 800 clamp(22px, 3cqw, 28px)/1.25 var(--font); text-wrap: balance; }
.member { display: flex; align-items: center; gap: 6px; margin: 0; color: var(--ink); font-size: var(--fs-body); font-weight: 700; }
.member i { width: 4px; height: 11px; }
dl { width: 100%; margin: 12px 0 0; font-size: var(--fs-body); }
dl div { display: flex; justify-content: space-between; padding: 10px 0; border-top: 1px solid var(--c-100); }
dt { color: var(--ink-3); } dd { margin: 0; font-weight: 700; }
/* The set in one row, in the metal frames of the album: missing cards dimmed. */
.set { display: grid; grid-template-columns: repeat(var(--n), minmax(0, 36px)); gap: 4px; width: 100%; margin: 0; padding: 0; list-style: none; }
.set li { aspect-ratio: 2 / 3; box-sizing: border-box; padding: 2px; border-radius: 5px; background: var(--c-100); }
.set li.frame-gold, .set li.frame-rose { background: var(--frame-fill) var(--frame-at) / var(--frame-size); }
.set img { width: 100%; height: 100%; display: block; object-fit: cover; border-radius: 3px; }
.set li.missing img { filter: var(--dim); }
/* The emote set in two rows of ten: missing ones in grey, still whole. */
.emotes { display: grid; grid-template-columns: repeat(10, minmax(0, 36px)); gap: 4px; width: 100%; margin: 0; padding: 0; list-style: none; }
.emotes li { display: grid; place-items: center; aspect-ratio: 1; border-radius: 6px; background: var(--c-100); }
.emotes img { width: 86%; height: 86%; display: block; object-fit: contain; }
.emotes li.missing { background: var(--c-50); }
.emotes li.missing img { filter: grayscale(1); }
.live-preview { display: flex; flex: 1; width: 100%; align-items: center; justify-content: flex-end; flex-direction: column; gap: 2px; padding: 12px 0; }
.live-preview small { margin-top: 6px; font-size: var(--fs-caption); color: var(--ink-3); }
.equip { align-self: stretch; margin-top: auto; }
@container panel (max-width: 660px) { .plate-detail { grid-template-columns: minmax(0, 1fr); gap: 20px; } .art { width: min(100%, 260px); justify-self: center; } }
</style>
