<script setup lang="ts">
// An announcement from the server, shown once: closing it marks it read on this device. A daily one comes back
// the next day until the player turns it off.
import Modal from "../ui/Modal.vue";
import { closeNotice, readNotice, unreadNotice, updateDialogOpen } from "../stores/update";
</script>

<template>
  <Modal
    v-if="unreadNotice && !updateDialogOpen" :key="unreadNotice.id" :title="unreadNotice.title" heading
    @close="closeNotice(unreadNotice)"
  >
    <p v-if="unreadNotice.body" class="body">{{ unreadNotice.body }}</p>
    <div class="acts">
      <button v-if="unreadNotice.daily" type="button" class="ui-btn" @click="readNotice(unreadNotice.id)">不再出现</button>
      <button type="button" class="ui-btn primary" @click="closeNotice(unreadNotice)">知道了</button>
    </div>
  </Modal>
</template>

<style scoped>
.body {
  margin: 0;
  white-space: pre-wrap;
  font-size: var(--fs-strong);
  font-weight: 700;
  line-height: 1.55;
  color: var(--ink);
}
.acts {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}
.acts .primary {
  min-width: 96px;
}
</style>
