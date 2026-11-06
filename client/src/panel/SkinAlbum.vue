<script setup lang="ts">
import { computed, ref } from "vue";
import { manifest, characterColor } from "../manifest";
import { ownsCharacter } from "../items";
import { collection } from "../stores/player";
import { settings } from "../stores/settings";
import FilterChips from "../ui/FilterChips.vue";
import Icon from "../ui/Icon.vue";
import SkinArt from "./SkinArt.vue";
import SkinDetail from "./SkinDetail.vue";
const filter = ref('all');
const selected = ref('');
const owned = (name: string) => ownsCharacter(name, collection.owned);
const unlocked = computed(() => manifest.skins.filter((skin) => owned(skin.name)).length);
const skins = computed(() => manifest.skins.filter((skin) => filter.value === 'all' || owned(skin.name) === (filter.value === 'owned')));
const FILTERS = [{ id: 'all', label: '全部' }, { id: 'owned', label: '已拥有' }, { id: 'missing', label: '未拥有' }];
</script>

<template>
  <div class="skin-album">
    <header><FilterChips v-model="filter" :options="FILTERS" label="皮肤筛选" /><span>已解锁 <b>{{ unlocked }}</b> / {{ manifest.skins.length }}</span></header>
    <div class="wall ui-scroll"><div class="skin-grid">
      <button v-for="skin in skins" :key="skin.name" type="button" class="skin-card ui-tile" :aria-label="`${skin.name}，${owned(skin.name) ? '已拥有' : '未解锁'}，查看详情`" @click="selected = skin.name">
        <span class="cover"><SkinArt :name="skin.name" :owned="owned(skin.name)" /><span class="state ui-tag" :class="{ dark: owned(skin.name) }"><Icon :name="settings.character === skin.name ? 'check' : owned(skin.name) ? 'shirt' : 'lock'" :size="11" />{{ settings.character === skin.name ? '已装备' : owned(skin.name) ? '已拥有' : '未解锁' }}</span></span>
        <span class="meta"><b>{{ skin.name }}</b><small><i :style="{ background: characterColor(skin.member) }"></i>{{ skin.member }}<span>查看详情 <Icon name="back" :size="11" /></span></small></span>
      </button>
    </div><p v-if="!skins.length" class="ui-empty">当前筛选下没有皮肤</p></div>
    <SkinDetail v-if="selected" :name="selected" @close="selected = ''" />
  </div>
</template>

<style scoped>
.skin-album { display: flex; flex-direction: column; flex: 1; min-height: 0; }
header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin: 2px 0 12px; }
header > span { font-size: var(--fs-label); color: var(--ink-2); white-space: nowrap; }
header b { font: 800 var(--fs-section)/1 var(--font-latin); color: var(--c-700); }
.wall { flex: 1; min-height: 0; overflow: auto; padding: 3px 6px 12px 2px; }
.skin-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(165px, 1fr)); gap: 24px 18px; }
.skin-card { min-width: 0; max-width: 260px; align-items: stretch; text-align: left; }
.cover { position: relative; display: block; transition: transform var(--dur-base) var(--ease-out); }
.skin-card:hover :deep(.figure) { transform: translateY(-4px); }
/* Unowned skins stay a dimmed original until the pointer lights them up. */
.skin-card:hover :deep(.locked .figure) { filter: var(--contour) drop-shadow(0 0 2.5px rgba(255, 255, 255, 0.9)); }
.state { position: absolute; right: 12px; bottom: 12px; display: flex; align-items: center; gap: 4px; font-size: var(--fs-caption); }
.meta { display: flex; flex-direction: column; gap: 7px; margin-top: 12px; }
.meta b { font-size: var(--fs-strong); font-weight: 800; }
.meta small { display: flex; align-items: center; gap: 5px; color: var(--ink-2); font-size: var(--fs-label); }
.meta i { width: 3px; height: 10px; }
.meta small span { display: inline-flex; align-items: center; gap: 3px; margin-left: auto; color: var(--ink-3); font-size: var(--fs-caption); }
.meta small svg { transform: rotate(180deg); }
</style>
