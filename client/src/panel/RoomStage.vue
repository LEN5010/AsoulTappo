<script setup lang="ts">
// The room as one table: the own pet and the members' live pets, empty seats outlined.
import { computed } from "vue";
import { PET_BASE } from "../characters";
import { pet } from "../stores/pet";
import { localPet, others } from "../stores/room";
import { settings } from "../stores/settings";
import NamePill from "../pet/NamePill.vue";
import PetView from "../pet/PetView.vue";

const SEATS = 6;
const SCALE = 0.46;
const PILL_WIDTH = PET_BASE.width * SCALE;

// The own pet takes a seat; when the room outgrows the table the last seat counts the rest.
const seated = computed(() => others.value.slice(0, others.value.length > SEATS - 1 ? SEATS - 2 : SEATS - 1));
const hidden = computed(() => others.value.length - seated.value.length);
const vacant = computed(() => SEATS - 1 - seated.value.length - (hidden.value ? 1 : 0));
</script>

<template>
  <section class="table ui-frame" data-rise>
    <i class="halftone" aria-hidden="true"></i>
    <i class="stripe" aria-hidden="true"></i>
    <div class="seats">
      <div class="seat">
        <PetView
          :character="settings.character" :scale="SCALE" :min-emote="34"
          :key-down="pet.keyDown" :mouse-dx="pet.dx" :mouse-dy="pet.dy"
          :left-down="pet.left" :right-down="pet.right" :emote="localPet.emote"
        />
        <NamePill :nick="settings.nick.trim() || '我'" :width="PILL_WIDTH" />
      </div>
      <div v-for="m in seated" :key="m.id" class="seat">
        <PetView :character="m.character" :scale="SCALE" :min-emote="34" :pulse="m.pulse" :emote="m.emote" :combo="m.combo" />
        <NamePill :nick="m.nick" :width="PILL_WIDTH" />
      </div>
      <div v-if="hidden" class="seat more"><b>+{{ hidden }}</b></div>
      <div v-for="n in vacant" :key="n" class="seat vacant"><i aria-hidden="true"></i></div>
    </div>
  </section>
</template>

<style scoped>
.table {
  --cut: var(--cut-l);
  background: var(--accent);
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
.stripe {
  position: absolute;
  top: -10px;
  bottom: -10px;
  right: 18%;
  width: 130px;
  background: rgba(255, 255, 255, 0.2);
  transform: skewX(var(--skew));
}
.seats {
  position: relative;
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 6px;
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
.seat :deep(.art) {
  filter: var(--contour);
}
.vacant i {
  width: 72px;
  height: 58px;
  margin-bottom: 12px;
  box-sizing: border-box;
  border: 2px dashed rgba(255, 255, 255, 0.72);
  transform: skewX(var(--skew));
}
.more b {
  margin-bottom: 24px;
  font: italic 800 var(--fs-title)/1 var(--font-latin);
  color: var(--on-accent);
}
</style>
