<script setup lang="ts">
// Over the own pet after a partner poked it: who did it, and a key to poke back. Closes by itself (stores/room.ts).
import { closePoked, poked, pokeSoon } from "../stores/room";
import { POKED_WIDTH } from "./duelPick";
import PetBubble from "./PetBubble.vue";

defineProps<{ shift: number; below: boolean }>();
function pokeBack() {
  const from = poked.value?.id;
  closePoked();
  if (from) pokeSoon(from);
}
</script>

<template>
  <PetBubble :open="!!poked" :width="POKED_WIDTH" :shift="shift" :below="below">
    <div class="poked" role="status">
      <p><b>{{ poked?.nick }}</b> 戳了戳你</p>
      <button type="button" class="ui-btn small primary" @click="pokeBack">戳回去</button>
    </div>
  </PetBubble>
</template>

<style scoped>
.poked { display: flex; flex-direction: column; gap: 6px; }
.poked p {
  margin: 0; font: 700 var(--fs-label)/1.35 var(--font);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
</style>
