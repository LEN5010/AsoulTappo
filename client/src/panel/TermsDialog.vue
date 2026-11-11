<script setup lang="ts">
// Asked at start until the current texts are agreed to. It cannot be closed: agreeing lets the app go online,
// declining quits. Closing the panel window leaves the app offline and asks again next time.
import { ref } from "vue";
import { DOC_TITLES, type DocName } from "../legal";
import { agree, declineAndQuit } from "../legal/consent";
import Modal from "../ui/Modal.vue";
import LegalDoc from "./LegalDoc.vue";

/** The text being read, in place of the question. */
const reading = ref<DocName | null>(null);
const sheet = ref<HTMLElement>();

function read(doc: DocName | null) {
  reading.value = doc;
  // The sheet scrolls; a text opens at its top and the question comes back at its own.
  sheet.value?.closest(".sheet")?.scrollTo({ top: 0 });
}
</script>

<template>
  <Modal locked heading :wide="!!reading" :title="reading ? DOC_TITLES[reading] : '用户协议和隐私政策'">
    <div ref="sheet" class="terms">
      <template v-if="reading">
        <LegalDoc :doc="reading" />
        <div class="actions sticky">
          <button type="button" class="ui-btn" @click="read(null)">返回</button>
        </div>
      </template>
      <template v-else>
        <p class="lead">
          使用 AsoulTappo 前，请阅读并同意<button type="button" class="link" @click="read('terms')">《用户协议》</button>和<button
            type="button" class="link" @click="read('privacy')"
          >《隐私政策》</button>。
        </p>
        <div class="actions">
          <button type="button" class="ui-btn" @click="declineAndQuit">不同意并退出</button>
          <button type="button" class="ui-btn primary" @click="agree">同意</button>
        </div>
      </template>
    </div>
  </Modal>
</template>

<style scoped>
.lead {
  margin: 0 0 20px;
  font: 400 var(--fs-strong)/1.7 var(--font);
  color: var(--ink);
}
.link {
  padding: 0;
  border: 0;
  background: none;
  font: inherit;
  font-weight: 800;
  color: var(--c-800);
  cursor: pointer;
}
.link:hover {
  text-decoration: underline;
}
.link:focus-visible {
  outline: 2px solid var(--c-500);
  outline-offset: 2px;
  border-radius: var(--radius-s);
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.actions .primary {
  min-width: 96px;
}
/* While reading, the way back stays on screen at the foot of the sheet. */
.actions.sticky {
  position: sticky;
  bottom: 0;
  margin: 8px -24px -24px;
  padding: 12px 24px 18px;
  background: linear-gradient(180deg, transparent, var(--surface) 14px);
}
</style>
