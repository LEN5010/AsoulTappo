<script setup lang="ts">
// Over a partner's pet after a click on it: a row of keys (poke, rock-paper-scissors, the partner's profile), and
// the three bets once the rock-paper-scissors key is pressed. A press on a bet sends the invite. Closing on a press
// elsewhere, Escape and the timeout is in duelPick.ts and the app root.
import {
  PICK_WIDTH, askWidth, keepPick, pickKeys, pickPoke, pickProfile, pickStake, picking, showStakes, staking,
} from "./duelPick";
import HandImg from "./HandImg.vue";
import PetBubble from "./PetBubble.vue";
import StakeKeys from "./StakeKeys.vue";

defineProps<{ id: string; shift: number; below: boolean }>();
</script>

<template>
  <PetBubble :open="picking === id" :width="staking ? PICK_WIDTH : askWidth()" :shift="shift" :below="below">
    <div data-duel-pick role="dialog" aria-label="和伙伴玩" @pointermove="keepPick">
      <StakeKeys v-if="staking" @pick="pickStake" />
      <div v-else class="keys">
        <button v-if="pickKeys.poke" type="button" class="ui-btn small ask" @click="pickPoke">戳一戳</button>
        <button v-if="pickKeys.duel" type="button" class="ui-btn small ask" @click="showStakes">
          <HandImg name="scissors" :size="18" />猜拳
        </button>
        <button v-if="pickKeys.profile" type="button" class="ui-btn small ask" @click="pickProfile">看主页</button>
      </div>
    </div>
  </PetBubble>
</template>

<style scoped>
.keys {
  display: flex;
  gap: 6px;
}
.ask {
  flex: 1;
  min-width: 0;
  padding: 0;
  gap: 4px;
}
</style>
