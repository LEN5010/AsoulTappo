<script setup lang="ts">
// The settings page's feedback (stores/feedback.ts): a text, an optional contact and, in the desktop app, the latest
// part of the log, which the player ticks to send. Closes once sent; the settings row says so. The text and the
// contact stay in the settings until a send goes through, so closing the dialog keeps them. The send lives in the
// store: a dialog opened again while it is out shows it going and closes once it answers.
import { computed, ref } from "vue";
import Modal from "../ui/Modal.vue";
import { isTauri } from "../composables/tauri";
import {
  FEEDBACK_CONTACT_MAX, FEEDBACK_TEXT_MAX, feedbackSending, submitFeedback, type FeedbackResult,
} from "../stores/feedback";
import { settings } from "../stores/settings";

const emit = defineEmits<{ close: []; sent: [left: number] }>();

const withLog = ref(feedbackSending.value?.draft.log ?? false);
const busy = computed(() => feedbackSending.value !== null);
const failed = ref("");
const ready = computed(() => !!settings.feedbackText.trim() && !busy.value);

async function follow(result: Promise<FeedbackResult>) {
  const r = await result;
  if (r.ok) emit("sent", r.left);
  else failed.value = r.message;
}

if (feedbackSending.value) void follow(feedbackSending.value.result);

async function send() {
  if (!ready.value) return;
  failed.value = "";
  const draft = { text: settings.feedbackText, contact: settings.feedbackContact, log: isTauri && withLog.value };
  await follow(submitFeedback(draft));
}
</script>

<template>
  <Modal title="意见反馈" heading :locked="busy" @close="emit('close')">
    <form class="feedback" @submit.prevent="send">
      <textarea
        v-model="settings.feedbackText" class="ui-input text" :maxlength="FEEDBACK_TEXT_MAX" rows="6" placeholder="遇到的问题或建议"
        aria-label="反馈内容"
      ></textarea>
      <input
        v-model="settings.feedbackContact" class="ui-input" :maxlength="FEEDBACK_CONTACT_MAX" placeholder="联系方式（选填）"
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
