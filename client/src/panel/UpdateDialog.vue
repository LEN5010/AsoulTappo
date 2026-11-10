<script setup lang="ts">
import { computed } from "vue";
import Modal from "../ui/Modal.vue";
import {
  dismissUpdate, installUpdate, openDownloadPage, updateBusy, updateDialogOpen, updateFailed, updateForced, updateOffer,
  updatePercent,
} from "../stores/update";

const label = computed(() => {
  if (updateFailed.value) return "去下载页";
  if (updateBusy.value) return updatePercent.value == null ? "下载中" : `${updatePercent.value}%`;
  return "更新";
});
</script>

<template>
  <Modal v-if="updateDialogOpen && updateOffer" :title="updateForced ? '需要更新' : '发现新版本'" heading :locked="updateForced" @close="dismissUpdate">
    <p class="ver">{{ updateOffer.version }}</p>
    <p v-if="updateOffer.notes" class="notes">{{ updateOffer.notes }}</p>
    <p v-if="updateFailed" role="status" class="failed">自动更新失败，请到下载页手动安装</p>
    <div class="acts">
      <button v-if="!updateForced" type="button" class="ui-btn" :disabled="updateBusy" @click="dismissUpdate">稍后</button>
      <button v-if="!updateFailed" type="button" class="ui-btn" @click="openDownloadPage">去网页下载</button>
      <button type="button" class="ui-btn primary" :class="{ pulse: !updateBusy }" @click="installUpdate">{{ label }}</button>
    </div>
  </Modal>
</template>

<style scoped>
.ver {
  margin: 0;
  font: 800 40px/1 var(--font-latin);
  color: var(--ink);
}
.notes {
  margin: 14px 0 0;
  white-space: pre-wrap;
  font-size: var(--fs-strong);
  font-weight: 700;
  line-height: 1.55;
  color: var(--ink);
}
.failed {
  margin: 14px 0 0;
  font-size: var(--fs-label);
  font-weight: 700;
  color: var(--c-700);
}
.acts {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 20px;
}
.acts .primary {
  min-width: 96px;
}
</style>
