<script setup lang="ts">
// Skin detail. With the album's skins it steps through the owned ones, and the artwork opens in a full-panel viewer.
// An owned skin can be given a note, shown instead of its title (stores/skinNotes.ts); the title then sits in the table.
import { computed, nextTick, ref, watch } from "vue";
import { characterColor, memberOf, skinTitle } from "../manifest";
import { getCharacter, skinSeries } from "../characters";
import { ownsCharacter } from "../items";
import { collection } from "../stores/player";
import { SKIN_NOTE_MAX, settings } from "../stores/settings";
import { setSkinNote, shownSkinName, skinNote } from "../stores/skinNotes";
import { ui } from "../stores/ui";
import { poolFor } from "../resonance";
import { pet } from "../stores/pet";
import Modal from "../ui/Modal.vue";
import Icon from "../ui/Icon.vue";
import PetView from "../pet/PetView.vue";
import SkinArt from "./SkinArt.vue";
import { stepIndex } from "./album";
import ArtViewer from "./ArtViewer.vue";
import StepKeys from "./StepKeys.vue";
import { STANDALONE } from "../edition";
/** `names` is the album as the grid shows it; without it there is nothing to step to. */
const props = defineProps<{ name: string; names?: readonly string[] }>();
const emit = defineEmits<{ close: []; step: [name: string] }>();
const owned = computed(() => ownsCharacter(props.name, collection.owned));
const equipped = computed(() => settings.character === props.name);
function resonate() { ui.pool = poolFor(`char:${props.name}`); ui.page = 'resonance'; emit('close'); }

// Stepping passes over unowned skins, as the card album does with unowned cards.
const neighbour = (delta: -1 | 1) => {
  const list = props.names;
  return list?.[stepIndex(list, props.name, (n) => n, delta, (n) => ownsCharacter(n, collection.owned))];
};
const prevName = computed(() => neighbour(-1));
const nextName = computed(() => neighbour(1));
function step(delta: -1 | 1) {
  const name = delta < 0 ? prevName.value : nextName.value;
  if (name) emit('step', name);
}
const viewing = ref(false);
watch(owned, (o) => !o && (viewing.value = false));

const naming = ref(false);
const noteDraft = ref("");
const noteBox = ref<HTMLInputElement>();
async function startNaming() {
  noteDraft.value = skinNote(props.name);
  naming.value = true;
  await nextTick();
  noteBox.value?.select();
}
function saveNote() {
  if (!naming.value) return;
  naming.value = false;
  setSkinNote(props.name, noteDraft.value);
}
watch(() => props.name, () => (naming.value = false));

// A two-form skin changes in the preview as it does on the desktop, by typing; a form key holds one of the two, and
// the same key again lets go.
const twoForm = computed(() => !!getCharacter(props.name)?.form);
const formPin = ref<boolean | null>(null);
function pinForm(form: boolean) {
  formPin.value = formPin.value === form ? null : form;
}
watch(() => props.name, () => (formPin.value = null));
</script>

<template>
  <Modal :title="skinTitle(name)" wide :covered="viewing" @close="emit('close')">
    <div class="skin-detail">
      <div class="portrait">
        <SkinArt :name="name" :owned="owned" detail />
        <button v-if="owned" type="button" class="zoom" aria-label="放大" @click="viewing = true"></button>
        <StepKeys v-if="names" :prev="!!prevName" :next="!!nextName" :keyboard="!viewing" @step="step" />
      </div>
      <div class="info">
        <span class="ui-tag gold">皮肤藏品</span>
        <div class="name-row">
          <input
            v-if="naming" ref="noteBox" v-model="noteDraft" class="ui-input note" :maxlength="SKIN_NOTE_MAX" :placeholder="skinTitle(name)"
            aria-label="备注名" spellcheck="false" @keydown.enter="saveNote" @keydown.esc.stop="naming = false" @blur="saveNote"
          />
          <h3 v-else>{{ shownSkinName(name) }}</h3>
          <button v-if="owned && !naming" type="button" class="ui-btn small ghost rename" aria-label="备注名" title="备注名" @click="startNaming">
            <Icon name="pencil" :size="15" />
          </button>
        </div>
        <p class="member"><i :style="{ background: characterColor(memberOf(name)) }"></i>{{ memberOf(name) }}</p>
        <dl><div v-if="skinNote(name)"><dt>原名</dt><dd>{{ skinTitle(name) }}</dd></div><div><dt>系列</dt><dd>{{ skinSeries(name) }}</dd></div><div v-if="!STANDALONE"><dt>持有</dt><dd>{{ owned ? '已拥有' : '未解锁' }}</dd></div></dl>
        <div class="live-preview">
          <PetView :character="name" :scale="0.82" :key-down="pet.keyDown" :form-press="pet.formPress" :mouse-dx="pet.dx" :mouse-dy="pet.dy" :left-down="pet.left" :right-down="pet.right" :form="formPin" />
          <div v-if="twoForm" class="form-keys" role="group" aria-label="形态">
            <button type="button" class="ui-btn small" :class="{ primary: formPin === false }" :aria-pressed="formPin === false" @click="pinForm(false)">一形态</button>
            <button type="button" class="ui-btn small" :class="{ primary: formPin === true }" :aria-pressed="formPin === true" @click="pinForm(true)">二形态</button>
          </div>
          <small v-else>桌宠预览</small>
        </div>
        <button v-if="owned" type="button" class="ui-btn primary equip" :disabled="equipped" @click="settings.character = name"><Icon name="shirt" :size="15" />{{ equipped ? '已装备' : '装备皮肤' }}</button>
        <button v-else type="button" class="ui-btn primary equip" @click="resonate"><Icon name="spark" :size="15" />去共鸣获取</button>
      </div>
    </div>

    <template #front>
      <ArtViewer
        v-if="viewing" :id="name" :ratio="16 / 9" :label="skinTitle(name)"
        :steps="!!names" :prev="!!prevName" :next="!!nextName"
        @step="step" @close="viewing = false"
      >
        <img :key="name" class="full" :src="getCharacter(name)!.bg" :alt="skinTitle(name)" draggable="false" />
      </ArtViewer>
    </template>
  </Modal>
</template>

<style scoped>
.skin-detail { display: grid; grid-template-columns: minmax(0, .9fr) minmax(0, 1fr); align-items: stretch; gap: 24px; }
.portrait { position: relative; width: 100%; align-self: center; border-radius: var(--radius-l); }
/* The whole artwork is the key into the viewer; the step keys sit above it. */
.zoom { position: absolute; inset: 0; z-index: 3; padding: 0; border: 0; border-radius: inherit; background: none; cursor: zoom-in; }
.zoom:focus-visible { outline: 2px solid var(--focus, var(--ink)); outline-offset: -2px; }
/* The skin picture has no ground of its own; it sits on the same paper as in the album. */
.full { background-color: var(--c-100); }
.info { display: flex; flex: 1; min-width: 0; align-items: flex-start; flex-direction: column; gap: 9px; padding-top: 4px; }
.name-row { display: flex; align-items: center; gap: 6px; width: 100%; margin: 6px 0 2px; }
h3 { min-width: 0; margin: 0; font: 800 clamp(22px, 3cqw, 28px)/1.25 var(--font); text-wrap: balance; overflow-wrap: anywhere; }
.note { flex: 1; min-width: 0; font: 800 clamp(18px, 2.4cqw, 22px)/1.25 var(--font); }
.rename { flex: none; padding: 0 6px; }
.member { display: flex; align-items: center; gap: 6px; margin: 0; color: var(--ink); font-size: var(--fs-body); font-weight: 700; }
.member i { width: 4px; height: 11px; }
dl { width: 100%; margin: 12px 0 0; font-size: var(--fs-body); }
dl div { display: flex; justify-content: space-between; padding: 10px 0; border-top: 1px solid var(--c-100); }
dt { color: var(--ink-3); } dd { margin: 0; font-weight: 700; }
.live-preview { display: flex; flex: 1; width: 100%; align-items: center; justify-content: flex-end; flex-direction: column; padding: 12px 0; }
.live-preview small { font-size: var(--fs-caption); color: var(--ink-3); }
.form-keys { display: flex; gap: 8px; margin-top: 6px; }
.equip { align-self: stretch; margin-top: auto; }
@container panel (max-width: 660px) { .skin-detail { grid-template-columns: minmax(0, 1fr); gap: 20px; } .portrait { width: min(100%, 260px); justify-self: center; } }
</style>
