<script setup lang="ts">
// Over a partner's pet after a click on it: one key, and the three bets once that key is pressed. A press on a bet
// sends the invite. Closing on a press elsewhere, Escape and the timeout is in duelPick.ts and the app root.
import { ASK_WIDTH, PICK_WIDTH, keepPick, pickStake, picking, showStakes, staking } from "./duelPick";
import Icon from "../ui/Icon.vue";
import PetBubble from "./PetBubble.vue";
import StakeKeys from "./StakeKeys.vue";

defineProps<{ id: string; shift: number; below: boolean }>();
</script>

<template>
  <PetBubble :open="picking === id" :width="staking ? PICK_WIDTH : ASK_WIDTH" :shift="shift" :below="below">
    <div data-duel-pick role="dialog" aria-label="猜拳" @pointermove="keepPick">
      <StakeKeys v-if="staking" @pick="pickStake" />
      <button v-else type="button" class="ui-btn small ask" @click="showStakes">
        <Icon name="hand-scissors" :size="15" />猜拳
      </button>
    </div>
  </PetBubble>
</template>

<style scoped>
.ask {
  width: 100%;
  padding: 0;
  gap: 4px;
}
</style>
