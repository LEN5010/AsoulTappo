<script setup lang="ts">
// Update rewards for this version, offered after the update dialog and the announcements. Closing it without
// claiming puts it away until the panel window opens again.
import { computed, ref } from "vue";
import Modal from "../ui/Modal.vue";
import Icon from "../ui/Icon.vue";
import { claimUpdateRewards, updateRewards } from "../stores/player";
import { unreadNotice, updateDialogOpen } from "../stores/update";

const total = computed(() => updateRewards.value.reduce((n, r) => n + r.shards, 0));
const key = computed(() => updateRewards.value.map((r) => r.id).join(","));
const putAway = ref("");
const busy = ref(false);
const shown = computed(() => total.value > 0 && !updateDialogOpen.value && !unreadNotice.value && putAway.value !== key.value);

async function claim() {
  busy.value = true;
  try {
    await claimUpdateRewards();
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <Modal v-if="shown" title="更新奖励" heading @close="putAway = key">
    <p class="gift"><Icon name="shard" :size="30" />+{{ total.toLocaleString("en-US") }}</p>
    <div class="acts">
      <button type="button" class="ui-btn primary" :disabled="busy" @click="claim">领取</button>
    </div>
  </Modal>
</template>

<style scoped>
.gift {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin: 8px 0 0;
  color: var(--c-700);
  font: 800 40px/1 var(--font-latin);
}
.acts {
  display: flex;
  justify-content: flex-end;
  margin-top: 24px;
}
.acts .primary {
  min-width: 96px;
}
</style>
