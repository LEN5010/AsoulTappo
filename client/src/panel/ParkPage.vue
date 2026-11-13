<script setup lang="ts">
// The park (docs/design/amusement-park.md §11): the top block with the coins, then a section for each game. The
// games open at manifest economy.park.coin.minTaps taps in all; until then the top block shows how far there is to
// go. Today's free coin is taken on the first visit of the day (§2.2). While the page is open it loads again with
// the status every RELOAD_MS at most: race and lottery prizes, the jackpot and a new day change without coins moving.
import { computed, onActivated, onDeactivated, ref, watch } from "vue";
import { manifest } from "../manifest";
import { status } from "../stores/player";
import { claimGift, loadPark, noPark, park, parkError } from "../stores/park";
import ParkTop from "./park/ParkTop.vue";
import ScratchSection from "./park/ScratchSection.vue";
import RaceSection from "./park/RaceSection.vue";
import LotterySection from "./park/LotterySection.vue";
import RedeemDialog from "./park/RedeemDialog.vue";

const MIN_TAPS = manifest.economy.park!.coin.minTaps;
const RELOAD_MS = 15000;

const open = computed(() => !!park.value?.unlocked);
/** The park could not be loaded: why, while there is nothing to show. */
const loadError = ref("");
const gift = ref(0);
const giftKey = ref(0);
const redeem = ref(false);

let active = false;
let entering = false;
let loadedAt = 0;
async function enter() {
  if (entering || noPark.value) return;
  entering = true;
  loadedAt = Date.now();
  try {
    const state = await loadPark();
    // Being offline already shows in the top bar; a refusal from the server shows here.
    const failed = state || park.value ? null : parkError.value;
    loadError.value = failed && failed.status > 0 ? failed.message : "";
    if (!state?.unlocked || !state.gift) return;
    const got = await claimGift();
    if (got) {
      gift.value = got;
      giftKey.value++;
    }
  } finally {
    entering = false;
  }
}

onActivated(() => {
  active = true;
  void enter();
});
onDeactivated(() => {
  active = false;
  redeem.value = false;
});
// Another save, a server that has just been reached, or the taps that open the park: load it again.
watch(() => [status.value?.player, (status.value?.totals.taps ?? 0) >= MIN_TAPS] as const, ([player, enough], [was, before]) => {
  if (active && player && (player !== was || (enough && !before))) void enter();
});
// Each heartbeat brings a new status; the page follows it, not faster than RELOAD_MS.
watch(status, () => {
  if (active && Date.now() - loadedAt >= RELOAD_MS) void enter();
});
</script>

<template>
  <div class="park-page ui-scroll">
    <p v-if="noPark" class="ui-error" role="status">当前服务器未开放游乐园</p>
    <template v-else>
      <p v-if="loadError" class="ui-error" role="alert">{{ loadError }}</p>
      <ParkTop :gift="gift" :gift-key="giftKey" @redeem="redeem = true" />
      <template v-if="open">
        <ScratchSection />
        <RaceSection />
        <LotterySection />
      </template>
    </template>
    <RedeemDialog v-if="redeem" @close="redeem = false" />
  </div>
</template>

<style scoped>
.park-page {
  height: 100%;
  box-sizing: border-box;
  overflow-y: auto;
  padding: 24px 20px 20px 16px;
  display: flex;
  flex-direction: column;
  gap: 22px;
}
.park-page > .ui-error {
  margin: 0;
}
</style>
