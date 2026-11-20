<script setup lang="ts">
// The settings page's feedback (stores/feedback.ts): a text, an optional contact and, in the desktop app, the latest
// part of the log, ticked by default. Closes once sent; the settings row says so.
import { computed, ref } from "vue";
import Modal from "../ui/Modal.vue";
import { isTauri } from "../composables/tauri";
import { FEEDBACK_CONTACT_MAX, FEEDBACK_TEXT_MAX, sendFeedback } from "../stores/feedback";

const emit = defineEmits<{ close: []; sent: [left: number] }>();

const text = ref("");
const contact = ref("");
const withLog = ref(true);
const busy = ref(false);
const failed = ref("");
const ready = computed(() => !!text.value.trim() && !busy.value);

async function send() {
  if (!ready.value) return;
  busy.value = true;
  failed.value = "";
  const r = await sendFeedback({ text: text.value, contact: contact.value, log: isTauri && withLog.value });
  busy.value = false;
  if (r.ok) emit("sent", r.left);
  else failed.value = r.message;
}
</script>

<template>
  <Modal title="意见反馈" heading :locked="busy" @close="emit('close')">
    <form class="feedback" @submit.prevent="send">
      <textarea
        v-model="text" class="ui-input text" :maxlength="FEEDBACK_TEXT_MAX" rows="6" placeholder="遇到的问题或建议"
        aria-label="反馈内容"
      ></textarea>
      <input
        v-model="contact" class="ui-input" :maxlength="FEEDBACK_CONTACT_MAX" placeholder="联系方式（选填）"
        aria-label="联系方式" autocomplete="off"
      />
      <label v-if="isTauri" class="ui-row log">
        <span>附带运行日志</span>
        <input v-model="withLog" class="ui-switch" type="checkbox" />
      </label>
      <p v-if="failed" class="ui-error" role="alert">{{ failed }}</p>
      <button class="ui-btn primary large" type="submit" :disabled="!ready">{{ busy ? "发送中…" : "发送" }}</button>
    </form>
  </Modal>
</template>

<style scoped>
.feedback {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: min(420px, 100%);
  margin: 0 auto;
  padding-bottom: 6px;
}
.feedback .ui-input {
  height: 40px;
  background: var(--c-100);
  box-shadow: none;
}
.feedback .ui-input:focus {
  box-shadow: 0 0 0 2px var(--ink);
}
.feedback .text {
  height: auto;
  min-height: 132px;
  padding: 10px 12px;
  line-height: 1.5;
  resize: vertical;
}
.log {
  padding: 0 2px;
}
.ui-error {
  margin: 0;
}
</style>
