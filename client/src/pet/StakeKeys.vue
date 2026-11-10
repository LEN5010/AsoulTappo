<script setup lang="ts">
// The three bets of a duel as keys that deepen with the bet: white, light coral, coral. The bet is on the key, what
// the winner gets under it. A bet the save cannot pay, or whose win would pass today's cap, is off.
import { duelConfig, stakeOpen } from "../stores/room";
import Icon from "../ui/Icon.vue";

defineProps<{ disabled?: boolean }>();
const emit = defineEmits<{ pick: [bet: number] }>();
const TIERS = ["low", "mid", "high"];
</script>

<template>
  <div v-if="duelConfig" class="stakes">
    <div v-for="(s, i) in duelConfig.stakes" :key="s.bet" class="stake">
      <button
        type="button" class="ui-btn key" :class="TIERS[Math.min(i, TIERS.length - 1)]"
        :disabled="disabled || !stakeOpen(s.bet)" @click="emit('pick', s.bet)"
      >
        <Icon name="shard" :size="13" />{{ s.bet.toLocaleString("en-US") }}
      </button>
      <small>赢 {{ s.prize.toLocaleString("en-US") }}</small>
    </div>
  </div>
</template>

<style scoped>
.stakes { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.stake { min-width: 0; display: flex; flex-direction: column; align-items: center; gap: 7px; }
.stake .ui-btn.key {
  width: 100%; min-width: 0; height: 40px; padding: 0; gap: 2px;
  font: 800 15px/1 var(--font-latin); color: var(--ink);
}
.key .icon { color: var(--c-600); }
/* The keycap's own colours, one step deeper per bet. */
.stake .ui-btn.mid:not(:disabled) { --key-top: var(--c-100); --key-bottom: var(--c-200); --key-lip: var(--c-300); }
.stake .ui-btn.high:not(:disabled) { --key-top: var(--c-400); --key-bottom: var(--c-500); --key-lip: var(--c-600); }
.stake .ui-btn.mid:hover:not(:disabled) { --key-top: var(--c-50); --key-bottom: var(--c-100); }
.stake .ui-btn.high:hover:not(:disabled) { --key-top: var(--c-300); --key-bottom: var(--c-400); }
.high:not(:disabled) .icon { color: var(--c-800); }
small { font: 700 var(--fs-caption)/1 var(--font); color: var(--ink-2); white-space: nowrap; }
.key:disabled { color: var(--ink-3); }
.key:disabled .icon, .key:disabled + small { color: var(--ink-3); }
</style>
