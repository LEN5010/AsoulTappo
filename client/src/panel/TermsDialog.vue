<script setup lang="ts">
// Asked at start until the current texts are agreed to and this version's statement that the app is free is
// confirmed: the first start after installing and after every update. It cannot be closed, and its key works only
// after the dialog has been in view for HOLD_MS. Agreeing lets the app go online; declining quits. Closing the panel
// window leaves the app offline and asks again next time.
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { DOC_TITLES, STATEMENT, type DocName } from "../legal";
import { HOLD_MS, agree, declineAndQuit, holdLeft, termsCurrent } from "../legal/consent";
import { ui } from "../stores/ui";
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

// The hold counts only while the panel is on screen, so a dialog waiting behind a closed or minimized panel has not
// been seen.
const TICK_MS = 100;
const shownMs = ref(0);
const left = computed(() => holdLeft(shownMs.value));
/** How much of the hold has passed, 0 to 1: the bar under the statement. */
const held = computed(() => Math.min(1, shownMs.value / HOLD_MS));
let timer: ReturnType<typeof setInterval> | undefined;
onMounted(() => {
  timer = setInterval(() => {
    if (ui.panelOpen && !ui.panelMinimized && !document.hidden) shownMs.value += TICK_MS;
    if (!left.value) clearInterval(timer);
  }, TICK_MS);
});
onBeforeUnmount(() => clearInterval(timer));

function confirm() {
  if (!left.value) agree();
}
</script>

<template>
  <Modal locked heading :wide="!!reading" :title="reading ? DOC_TITLES[reading] : '免费声明'">
    <div ref="sheet" class="terms">
      <template v-if="reading">
        <LegalDoc :doc="reading" />
        <div class="actions sticky">
          <button type="button" class="ui-btn" @click="read(null)">返回</button>
        </div>
      </template>
      <template v-else>
        <div class="statement">
          <p v-for="line in STATEMENT" :key="line">{{ line }}</p>
          <div
            class="hold" :class="{ done: left === 0 }" role="progressbar" aria-label="阅读进度"
            aria-valuemin="0" aria-valuemax="100" :aria-valuenow="Math.round(held * 100)"
          >
            <i :style="{ width: `${held * 100}%` }"></i>
          </div>
        </div>
        <p class="lead">
          <template v-if="termsCurrent">使用 AsoulTappo 受</template><template v-else>使用 AsoulTappo 前，请阅读并同意</template><button
            type="button" class="link" @click="read('terms')"
          >《用户协议》</button>和<button
            type="button" class="link" @click="read('privacy')"
          >《隐私政策》</button><template v-if="termsCurrent">约束。</template><template v-else>。</template>
        </p>
        <div class="actions">
          <button v-if="!termsCurrent" type="button" class="ui-btn" @click="declineAndQuit">不同意并退出</button>
          <button type="button" class="ui-btn primary" :disabled="left > 0" @click="confirm">
            {{ termsCurrent ? "确认" : "同意" }}<template v-if="left > 0">（{{ left }}）</template>
          </button>
        </div>
      </template>
    </div>
  </Modal>
</template>

<style scoped>
/* The statement is the part to read: larger than the line about the texts under it. */
.statement {
  margin: 0 0 16px;
  padding: 14px 16px;
  border-radius: var(--radius-m);
  background: var(--c-50);
}
.statement p {
  margin: 0;
  font: 500 var(--fs-strong)/1.7 var(--font);
  color: var(--ink);
}
.statement p + p {
  margin-top: 6px;
}
.statement p:first-child {
  font-weight: 800;
}
/* The hold as a bar: it fills while the statement is in view, and the key under it unlocks when it is full. */
.hold {
  height: 8px;
  margin-top: 14px;
  border-radius: 4px;
  background: var(--c-200);
  overflow: hidden;
}
.hold i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--c-500);
  transition: width 100ms linear;
}
.hold.done i {
  background: var(--ok);
}
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
