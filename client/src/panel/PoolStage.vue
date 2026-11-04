<script setup lang="ts">
// Resonance stage: a framed card, the pool's tier counts and a lineup of its cards and skins.
import { computed, ref } from "vue";
import { assetUrl } from "../asset";
import { getCharacter } from "../characters";
import { getCard, type Rarity } from "../manifest";
import type { Item } from "../items";
import { poolOf } from "../resonance";
import { collection } from "../stores/player";
import { reducedMotion } from "../stores/theme";
import Icon from "../ui/Icon.vue";

defineProps<{ busy: boolean }>();
const emit = defineEmits<{ inspect: [item: Item] }>();

const LINEUP_SIZE = 7;
const STATS: { rarity: Rarity; label: string; icon: string }[] = [
  { rarity: "legendary", label: "大隐藏", icon: "crown" },
  { rarity: "skin", label: "皮肤", icon: "shirt" },
  { rarity: "epic", label: "史诗", icon: "spark" },
  { rarity: "rare", label: "稀有", icon: "gem" },
  { rarity: "uncommon", label: "罕见", icon: "gem" },
  { rarity: "common", label: "普通", icon: "star5" },
];

const pool = poolOf();
const all = Object.values(pool).flat();
const previews = [...pool.legendary, ...pool.skin, ...pool.epic, ...pool.common].filter((i) => i.kind !== "emote");
const have = (items: Item[]) => items.filter((i) => collection.owned[i.id]).length;

const selected = ref(previews[0]?.id ?? "");
const active = computed(() => previews.find((i) => i.id === selected.value) ?? previews[0]);
const card = computed(() => (active.value?.kind === "card" ? getCard(active.value.ref) : undefined));

const page = ref(0);
const pageCount = Math.ceil(previews.length / LINEUP_SIZE);
const lineup = computed(() => previews.slice(page.value * LINEUP_SIZE, (page.value + 1) * LINEUP_SIZE));
const turn = (step: number) => (page.value = (page.value + step + pageCount) % pageCount);
const thumb = (item: Item) => (item.kind === "card" ? assetUrl(item.art) : getCharacter(item.ref)?.bg);
</script>

<template>
  <section class="pool-stage">
    <button v-if="active" type="button" class="hero" :disabled="busy" :title="active.name" @click="emit('inspect', active)">
      <span class="frame">
        <span class="art ui-frame">
          <template v-if="card">
            <video
              v-if="card.video && !reducedMotion" :key="card.id"
              :src="assetUrl(card.video)" :poster="assetUrl(card.thumb)" autoplay loop muted playsinline
            ></video>
            <img v-else :key="card.id" :src="assetUrl(card.full)" :alt="card.name" :style="{ backgroundImage: `url(${assetUrl(card.thumb)})` }" draggable="false" />
          </template>
          <img v-else class="skin" :src="getCharacter(active.ref)?.bg" :alt="active.name" draggable="false" />
        </span>
        <b class="crest">A-SOUL</b>
        <b class="plate">{{ active.name }}</b>
      </span>
      <Icon name="spark" :size="26" class="twinkle top" />
      <Icon name="spark" :size="14" class="twinkle side" />
    </button>

    <div class="info">
      <header class="title">
        <svg class="orbit" viewBox="0 0 320 110" aria-hidden="true">
          <ellipse cx="160" cy="55" rx="150" ry="34" transform="rotate(-8 160 55)" />
        </svg>
        <h3>此间共鸣</h3>
        <em>Resonance</em>
        <small>A-SOUL TAPPO</small>
      </header>

      <div class="stats">
        <template v-for="s in STATS" :key="s.rarity">
          <span v-if="pool[s.rarity].length" class="stat">
            <Icon :name="s.icon" :size="16" />{{ s.label }}<b>{{ have(pool[s.rarity]) }}</b><i>/ {{ pool[s.rarity].length }}</i>
          </span>
        </template>
      </div>

      <p class="collected">
        <Icon name="layers" :size="16" />
        已收集 <b>{{ have(all) }}</b><i>/ {{ all.length }}</i>
        <template v-if="active"><span class="sep">·</span><span class="now">{{ active.name }}</span></template>
      </p>

      <div class="lineup">
        <button v-if="pageCount > 1" type="button" class="flip" aria-label="上一页" :disabled="busy" @click="turn(-1)">
          <Icon name="back" :size="18" />
        </button>
        <div :key="page" class="row">
          <button
            v-for="item in lineup" :key="item.id" type="button" class="mini" :class="{ on: active?.id === item.id }"
            :disabled="busy" :title="item.name" :aria-pressed="active?.id === item.id" @click="selected = item.id"
          >
            <span class="ui-frame"><img :class="{ skin: item.kind !== 'card' }" :src="thumb(item)" :alt="item.name" draggable="false" /></span>
          </button>
        </div>
        <button v-if="pageCount > 1" type="button" class="flip next" aria-label="下一页" :disabled="busy" @click="turn(1)">
          <Icon name="back" :size="18" />
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.pool-stage {
  /* 240px covers the page title, the dock below and the page padding. */
  --hero-h: max(250px, min(44cqw, 100cqh - 240px));
  flex: 1 0 auto;
  display: flex;
  align-items: stretch;
  min-height: var(--hero-h);
  padding: 4px 6px 8px 8px;
}

.hero {
  position: relative;
  z-index: 1;
  flex: none;
  align-self: center;
  width: calc(var(--hero-h) * 0.7);
  height: var(--hero-h);
  padding: 0;
  border: 0;
  background: none;
  cursor: pointer;
}
.hero::before,
.hero::after {
  content: "";
  position: absolute;
  z-index: -1;
  border-radius: var(--radius-m);
}
.hero::before {
  inset: -2px -12px 22px 26px;
  background: var(--accent-mid);
  opacity: 0.55;
  transform: rotate(3deg);
}
.hero::after {
  inset: 26px 8px -8px -2px;
  background: var(--accent-soft);
  transform: rotate(-2deg);
}
.frame {
  position: absolute;
  inset: 0;
  padding: 6px;
  box-sizing: border-box;
  border-radius: var(--radius-m);
  background: linear-gradient(135deg, var(--gold-soft), var(--gold) 46%, var(--gold-soft));
  box-shadow: 0 12px 24px -14px rgba(var(--ink-rgb), 0.6);
  transition: transform var(--dur-base) var(--ease-out);
}
.hero:hover:not(:disabled) .frame {
  transform: translateY(-3px);
}
.art {
  display: block;
  width: 100%;
  height: 100%;
  background: var(--ink);
}
.art::after {
  content: "";
  position: absolute;
  inset: 4px;
  border-radius: var(--radius-s);
  box-shadow: inset 0 0 0 1px rgba(var(--gold-rgb), 0.8);
  pointer-events: none;
}
.art img,
.art video {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
  background: center / cover;
}
.art img.skin {
  object-fit: contain;
  background: var(--accent-tint);
}
.crest,
.plate {
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  box-sizing: border-box;
  background: var(--ink);
  box-shadow: 0 0 0 1px var(--gold);
  color: var(--gold-soft);
  white-space: nowrap;
}
.crest {
  top: 2px;
  padding: 3px 18px 4px;
  border-radius: 0 0 var(--radius-l) var(--radius-l);
  font: 800 var(--fs-caption)/1 var(--font-latin);
  letter-spacing: 0.18em;
}
.plate {
  bottom: 16px;
  max-width: 78%;
  padding: 4px 14px;
  border-radius: var(--radius-s);
  overflow: hidden;
  text-overflow: ellipsis;
  font: 700 var(--fs-label)/1.3 var(--font);
}
.twinkle {
  position: absolute;
  z-index: 2;
  color: var(--gold-soft);
  fill: var(--surface);
  stroke-width: 1.2;
  pointer-events: none;
}
.twinkle.top {
  top: -10px;
  left: -10px;
}
.twinkle.side {
  top: 14px;
  left: 20px;
}

.info {
  position: relative;
  flex: 1;
  min-width: 0;
  margin-left: -22px;
  padding: 14px 20px 18px 42px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 8px;
  border-radius: var(--radius-l);
  background: linear-gradient(135deg, var(--surface) 55%, var(--accent-tint));
  box-shadow: inset 0 0 0 1px var(--line-2), 0 10px 22px -18px rgba(var(--accent-rgb), 0.7);
}

.title {
  position: relative;
  padding: 4px 0 2px 12px;
}
.orbit {
  position: absolute;
  left: -14px;
  top: -8px;
  width: min(100%, 300px);
  height: auto;
  fill: none;
  stroke: var(--accent-mid);
  stroke-width: 1.4;
  pointer-events: none;
}
h3 {
  position: relative;
  margin: 0;
  font: 800 clamp(28px, 4.2cqw, 40px)/1.15 var(--font);
  letter-spacing: 0.03em;
}
.title em {
  position: relative;
  display: block;
  margin: -5px 0 0 30px;
  font: italic 400 clamp(16px, 2.4cqw, 23px)/1 "Snell Roundhand", "Segoe Script", "Brush Script MT", cursive;
  color: var(--accent-deep);
}
.title small {
  position: absolute;
  top: 2px;
  right: 0;
  font: 800 var(--fs-caption)/1 var(--font-latin);
  letter-spacing: 0.14em;
  color: var(--ink-3);
}

.stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px 12px;
}
.stat {
  display: flex;
  align-items: center;
  height: 32px;
  padding: 0 10px;
  border-radius: var(--radius-m);
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line-2);
  font-size: var(--fs-body);
  font-weight: 500;
  color: var(--ink-2);
  white-space: nowrap;
}
.stat svg {
  margin-right: 7px;
  color: var(--accent-deep);
}
.stat b,
.collected b {
  margin-left: auto;
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: var(--ink);
}
.stat i,
.collected i {
  margin-left: 4px;
  font-style: normal;
  color: var(--ink-3);
}

.collected {
  position: relative;
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  padding: 7px 2px;
  border-top: 1px dashed var(--line-2);
  border-bottom: 1px solid var(--line-2);
  font-size: var(--fs-body);
  font-weight: 500;
  color: var(--ink-2);
}
.collected svg {
  flex: none;
  color: var(--accent-deep);
}
.collected b {
  margin-left: 0;
}
.collected i {
  margin-left: 0;
}
.sep {
  color: var(--ink-3);
}
.now {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  color: var(--ink);
}

.lineup {
  display: flex;
  align-items: center;
  gap: 4px;
  padding-bottom: 8px;
}
.flip {
  flex: none;
  width: 22px;
  height: 40px;
  padding: 0;
  display: grid;
  place-items: center;
  border: 0;
  background: none;
  color: var(--ink-2);
  cursor: pointer;
}
.flip:hover:not(:disabled) {
  color: var(--accent-deep);
}
.flip.next svg {
  transform: rotate(180deg);
}
.row {
  flex: 1;
  min-width: 0;
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 6px;
}
.mini {
  position: relative;
  aspect-ratio: 0.76;
  padding: 2px;
  border: 0;
  border-radius: var(--radius-s);
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line-2);
  cursor: pointer;
  transition: transform var(--dur-fast) var(--ease-out), box-shadow var(--dur-fast);
}
.mini:hover:not(:disabled) {
  transform: translateY(-2px);
}
.mini.on {
  box-shadow: 0 0 0 2px var(--accent), var(--glow-s);
}
.mini.on::after {
  content: "";
  position: absolute;
  left: 50%;
  bottom: -11px;
  width: 10px;
  height: 10px;
  margin-left: -5px;
  background: var(--accent);
  clip-path: polygon(50% 0, 62% 38%, 100% 50%, 62% 62%, 50% 100%, 38% 62%, 0 50%, 38% 38%);
}
.mini span {
  display: block;
  width: 100%;
  height: 100%;
}
.mini img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.mini img.skin {
  object-fit: contain;
  background: var(--accent-tint);
}

@container panel (max-width: 820px) {
  .title small {
    display: none;
  }
  .info {
    padding-right: 12px;
  }
}
</style>
