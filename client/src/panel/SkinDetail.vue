<script setup lang="ts">
import { computed } from "vue";
import { characterColor, memberOf } from "../manifest";
import { skinSeries } from "../characters";
import { ownsCharacter } from "../items";
import { collection } from "../stores/player";
import { settings } from "../stores/settings";
import { ui } from "../stores/ui";
import { pet } from "../stores/pet";
import Modal from "../ui/Modal.vue";
import Icon from "../ui/Icon.vue";
import PetView from "../pet/PetView.vue";
import SkinArt from "./SkinArt.vue";
const props = defineProps<{ name: string }>();
const emit = defineEmits<{ close: [] }>();
const owned = computed(() => ownsCharacter(props.name, collection.owned));
const equipped = computed(() => settings.character === props.name);
function resonate() { ui.page = 'resonance'; emit('close'); }
</script>

<template>
  <Modal :title="name" wide @close="emit('close')">
    <div class="skin-detail">
      <SkinArt class="portrait" :name="name" :owned="owned" detail />
      <div class="info">
        <span class="ui-tag gold">皮肤藏品</span>
        <h3>{{ name }}</h3>
        <p class="member"><i :style="{ background: characterColor(memberOf(name)) }"></i>{{ memberOf(name) }}</p>
        <dl><div><dt>系列</dt><dd>{{ skinSeries(name) }}</dd></div><div><dt>持有</dt><dd>{{ owned ? '已拥有' : '未解锁' }}</dd></div></dl>
        <div class="live-preview"><PetView :character="name" :scale="0.82" :key-down="pet.keyDown" :mouse-dx="pet.dx" :mouse-dy="pet.dy" :left-down="pet.left" :right-down="pet.right" /><small>桌宠预览</small></div>
        <button v-if="owned" type="button" class="ui-btn primary equip" :disabled="equipped" @click="settings.character = name"><Icon name="shirt" :size="15" />{{ equipped ? '已装备' : '装备皮肤' }}</button>
        <button v-else type="button" class="ui-btn primary equip" @click="resonate"><Icon name="spark" :size="15" />去共鸣获取</button>
      </div>
    </div>
  </Modal>
</template>

<style scoped>
.skin-detail { display: grid; grid-template-columns: minmax(0, .9fr) minmax(0, 1fr); align-items: stretch; gap: 24px; }
.portrait { width: 100%; align-self: center; }
.info { display: flex; flex: 1; min-width: 0; align-items: flex-start; flex-direction: column; gap: 9px; padding-top: 4px; }
h3 { margin: 4px 0 0; font: 800 var(--fs-heading)/1.3 var(--font); text-wrap: balance; }
.member { display: flex; align-items: center; gap: 6px; margin: 0; color: var(--ink-2); font-size: var(--fs-body); font-weight: 700; }
.member i { width: 4px; height: 11px; }
dl { width: 100%; margin: 12px 0 0; font-size: var(--fs-body); }
dl div { display: flex; justify-content: space-between; padding: 10px 0; border-top: 1px solid var(--line); }
dt { color: var(--ink-3); } dd { margin: 0; font-weight: 700; }
.live-preview { display: flex; flex: 1; width: 100%; align-items: center; justify-content: flex-end; flex-direction: column; padding: 12px 0; }
.live-preview small { font-size: var(--fs-caption); color: var(--ink-3); }
.equip { align-self: stretch; margin-top: auto; }
@container panel (max-width: 660px) { .skin-detail { grid-template-columns: minmax(0, 1fr); gap: 20px; } .portrait { width: min(100%, 260px); justify-self: center; } }
</style>
