<script setup lang="ts">
// A name plate before wearing it: the card, the set that unlocks it, and the own pet with the plate under it
// as partners see it.
import { computed } from "vue";
import { assetUrl } from "../asset";
import { cardFrame, poolName } from "../cards";
import { characterColor, manifest, type ManifestCard } from "../manifest";
import { collection } from "../stores/player";
import { settings } from "../stores/settings";
import { ui } from "../stores/ui";
import { pet } from "../stores/pet";
import Modal from "../ui/Modal.vue";
import Icon from "../ui/Icon.vue";
import PetView from "../pet/PetView.vue";
import NamePlate from "../pet/NamePlate.vue";
import { nameBand, plateSet, plateSize } from "../pet/plates";

const props = defineProps<{ card: ManifestCard }>();
const emit = defineEmits<{ close: [] }>();

/** The pet's size in the preview, as in the skin preview. */
const SCALE = 0.82;
const plate = plateSize(SCALE);
const font = nameBand(SCALE).font;
const has = (c: ManifestCard) => !!collection.owned[`card:${c.id}`];
const owned = computed(() => has(props.card));
/** The cards to collect, the big hidden card first. */
const set = computed(() => plateSet(props.card));
const collected = computed(() => set.value.filter(has).length);
const unlocked = computed(() => collected.value === set.value.length);
const worn = computed(() => settings.plate === props.card.id);
const nick = computed(() => settings.nick.trim() || "匿名小面包");
const pool = computed(() => poolName(manifest.series.find((s) => s.id === props.card.series)?.name ?? props.card.series));
function resonate() { ui.page = "resonance"; emit("close"); }
</script>

<template>
  <Modal :title="card.name" wide @close="emit('close')">
    <div class="plate-detail">
      <div class="art ui-frame frame-gold" :class="{ locked: !owned }">
        <img :src="assetUrl(owned ? card.full : card.thumb)" :style="{ backgroundImage: `url(${assetUrl(card.thumb)})` }" :alt="card.name" />
      </div>
      <div class="info">
        <span class="ui-tag gold">铭牌</span>
        <h3>{{ card.name }}</h3>
        <p class="member"><i :style="{ background: characterColor(card.characters[0]!) }"></i>{{ card.characters.join(" / ") }}</p>
        <dl>
          <div><dt>系列</dt><dd>{{ pool }}</dd></div>
          <div><dt>解锁</dt><dd>{{ unlocked ? '已解锁' : `${collected} / ${set.length}` }}</dd></div>
        </dl>
        <ul class="set" :style="{ '--n': set.length }" aria-label="解锁需要的卡片">
          <li
            v-for="c in set" :key="c.id" :class="[cardFrame(c), { missing: !has(c) }]"
            :title="`${c.name}：${has(c) ? '已拥有' : '未获得'}`"
          >
            <img :src="assetUrl(c.thumb)" :alt="c.name" />
          </li>
        </ul>
        <div class="live-preview">
          <PetView :character="settings.character" :scale="SCALE" :key-down="pet.keyDown" :mouse-dx="pet.dx" :mouse-dy="pet.dy" :left-down="pet.left" :right-down="pet.right" />
          <NamePlate :card="card.id" :nick="nick" :color="characterColor(settings.character)" :width="plate.width" :height="plate.height" :font="font" />
          <small>桌宠预览</small>
        </div>
        <button v-if="unlocked" type="button" class="ui-btn primary equip" :disabled="worn" @click="settings.plate = card.id"><Icon name="check" :size="15" />{{ worn ? '使用中' : '使用铭牌' }}</button>
        <button v-else type="button" class="ui-btn primary equip" @click="resonate"><Icon name="spark" :size="15" />去共鸣获取</button>
      </div>
    </div>
  </Modal>
</template>

<style scoped>
.plate-detail { display: grid; grid-template-columns: minmax(0, .9fr) minmax(0, 1fr); align-items: stretch; gap: 24px; }
.art { --radius: var(--radius-l); align-self: center; width: 100%; aspect-ratio: 2 / 3; box-sizing: border-box; padding: 6px; background: var(--frame-fill) var(--frame-at) / var(--frame-size); }
.art img { width: 100%; height: 100%; display: block; object-fit: cover; background: center / cover no-repeat; border-radius: calc(var(--radius-l) - 5px); }
.art.locked img { filter: brightness(0.74); }
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
.live-preview { display: flex; flex: 1; width: 100%; align-items: center; justify-content: flex-end; flex-direction: column; gap: 2px; padding: 12px 0; }
.live-preview small { margin-top: 6px; font-size: var(--fs-caption); color: var(--ink-3); }
.equip { align-self: stretch; margin-top: auto; }
@container panel (max-width: 660px) { .plate-detail { grid-template-columns: minmax(0, 1fr); gap: 20px; } .art { width: min(100%, 260px); justify-self: center; } }
</style>
