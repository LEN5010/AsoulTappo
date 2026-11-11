<script setup lang="ts">
// The room as one table: the own pet and the members' live pets, empty seats outlined. A full row opens the next.
// A press on a seat opens that member's profile: the own seat the 排行 page, a partner's on a server that answers.
import { computed } from "vue";
import { PET_BASE } from "../characters";
import { characterColor } from "../manifest";
import { MAX_ROOM_SIZE } from "../net/protocol";
import { pet } from "../stores/pet";
import { canProfile, localPet, others, shownNick } from "../stores/room";
import { settings } from "../stores/settings";
import NamePill from "../pet/NamePill.vue";
import PetView from "../pet/PetView.vue";

/** null for the own seat. */
const emit = defineEmits<{ profile: [id: string | null] }>();

const ROW = 6;
const SCALE = 0.46;
const PILL_WIDTH = PET_BASE.width * SCALE;

const vacant = computed(() => {
  const seated = others.value.length + 1;
  return Math.min(Math.ceil(seated / ROW) * ROW, MAX_ROOM_SIZE) - seated;
});
</script>

<template>
  <section class="table ui-frame" data-rise>
    <div class="seats">
      <button type="button" class="seat" title="我的主页" aria-label="我的主页" @click="emit('profile', null)">
        <PetView
          :character="settings.character" :scale="SCALE" :min-emote="34"
          :key-down="pet.keyDown" :mouse-dx="pet.dx" :mouse-dy="pet.dy"
          :left-down="pet.left" :right-down="pet.right" :emote="localPet.emote" :win="localPet.win"
        />
        <NamePill :nick="settings.nick.trim() || '我'" :color="characterColor(settings.character)" :width="PILL_WIDTH" />
      </button>
      <component
        :is="canProfile(m) ? 'button' : 'div'" v-for="m in others" :key="m.id" class="seat"
        v-bind="canProfile(m) ? { type: 'button', title: `${shownNick(m)}的主页`, 'aria-label': `${shownNick(m)}的主页` } : {}" @click="canProfile(m) && emit('profile', m.id)"
      >
        <PetView :character="m.character" :scale="SCALE" :min-emote="34" :pulse="m.pulse" :emote="m.emote" :combo="m.combo" :win="m.win" :motion-id="m.id" />
        <NamePill :nick="shownNick(m)" :color="characterColor(m.character)" :width="PILL_WIDTH" />
      </component>
      <div v-for="n in vacant" :key="n" class="seat vacant"><i aria-hidden="true"></i></div>
    </div>
  </section>
</template>

<style scoped>
/* A light wall behind one long table. */
.table {
  --radius: var(--radius-l);
  background: var(--c-100);
  padding: 50px 12px 12px;
}
.seats {
  position: relative;
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 26px 6px;
}
.seat {
  min-width: 0;
  height: 86px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
}
button.seat {
  width: 100%;
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  color: inherit;
  cursor: pointer;
}
.seat :deep(.bg) {
  filter: var(--contour);
}
.vacant i {
  width: 72px;
  height: 58px;
  margin-bottom: 12px;
  box-sizing: border-box;
  border: 2px dashed var(--c-300);
  border-radius: var(--radius-m);
}
</style>
