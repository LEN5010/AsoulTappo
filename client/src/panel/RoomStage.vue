<script setup lang="ts">
// The room as one table: the own pet and the members' live pets, empty seats outlined. A full row opens the next.
import { computed } from "vue";
import { PET_BASE } from "../characters";
import { MAX_ROOM_SIZE } from "../net/protocol";
import { pet } from "../stores/pet";
import { localPet, others } from "../stores/room";
import { settings } from "../stores/settings";
import NamePill from "../pet/NamePill.vue";
import PetView from "../pet/PetView.vue";

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
    <i class="halftone" aria-hidden="true"></i>
    <div class="seats">
      <div class="seat">
        <PetView
          :character="settings.character" :scale="SCALE" :min-emote="34"
          :key-down="pet.keyDown" :mouse-dx="pet.dx" :mouse-dy="pet.dy"
          :left-down="pet.left" :right-down="pet.right" :emote="localPet.emote"
        />
        <NamePill :nick="settings.nick.trim() || '我'" :width="PILL_WIDTH" />
      </div>
      <div v-for="m in others" :key="m.id" class="seat">
        <PetView :character="m.character" :scale="SCALE" :min-emote="34" :pulse="m.pulse" :emote="m.emote" :combo="m.combo"
          :key-down="m.motion.keyDown" :mouse-dx="m.motion.dx" :mouse-dy="m.motion.dy"
          :left-down="m.motion.left" :right-down="m.motion.right" smooth-mouse />
        <NamePill :nick="m.nick" :width="PILL_WIDTH" />
      </div>
      <div v-for="n in vacant" :key="n" class="seat vacant"><i aria-hidden="true"></i></div>
    </div>
  </section>
</template>

<style scoped>
.table {
  --radius: var(--radius-l);
  background: var(--grad-sky);
  padding: 50px 12px 12px;
}
.halftone {
  position: absolute;
  inset: auto 0 0;
  height: 110px;
  background: var(--surface);
  opacity: 0.34;
  mask: var(--halftone) left bottom / 280px auto repeat-x;
  -webkit-mask: var(--halftone) left bottom / 280px auto repeat-x;
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
.seat :deep(.bg) {
  filter: var(--contour);
}
.vacant i {
  width: 72px;
  height: 58px;
  margin-bottom: 12px;
  box-sizing: border-box;
  border: 2px dashed rgba(255, 255, 255, 0.72);
}
</style>
