<script setup lang="ts">
// The notice board: the server's current announcements, one page each, newest first. It opens on the newest one due;
// the pages due when it opened carry a dot until they are looked at. Closing it closes every due one (stores/update).
import { computed, ref } from "vue";
import Modal from "../ui/Modal.vue";
import { closeNoticeBoard, dueNotices, noticeDate, notices, noticeSeen, readNotice } from "../stores/update";

const fresh = ref(new Set(dueNotices.value.map((a) => a.id)));
const picked = ref(dueNotices.value[0]?.id ?? notices.value[0]?.id ?? "");
/** The page open now; the newest when the picked one has left the list. */
const page = computed(() => notices.value.find((a) => a.id === picked.value) ?? notices.value[0]);

function pick(id: string) {
  picked.value = id;
  if (fresh.value.has(id)) fresh.value = new Set([...fresh.value].filter((f) => f !== id));
}
pick(picked.value);

const tabs = ref<HTMLElement[]>([]);
/** Up and down move between pages, as in a tab list. */
function step(e: KeyboardEvent, i: number) {
  const to = e.key === "ArrowDown" ? i + 1 : e.key === "ArrowUp" ? i - 1 : -1;
  const target = notices.value[to];
  if (!target) return;
  e.preventDefault();
  pick(target.id);
  tabs.value[to]?.focus();
}
</script>

<template>
  <Modal title="公告" heading wide @close="closeNoticeBoard">
    <div v-if="page" class="board">
      <div class="tabs ui-scroll" role="tablist" aria-orientation="vertical" aria-label="公告列表">
        <button
          v-for="(a, i) in notices" :key="a.id" ref="tabs" type="button" role="tab" class="tab"
          :class="{ on: a.id === page.id }" :aria-selected="a.id === page.id" :tabindex="a.id === page.id ? 0 : -1"
          @click="pick(a.id)" @keydown="step($event, i)"
        >
          <b>{{ a.title }}</b>
          <small v-if="a.since">{{ noticeDate(a.since) }}</small>
          <i v-if="fresh.has(a.id)" class="dot" aria-label="未读"></i>
        </button>
      </div>
      <div class="pane">
        <article :key="page.id" class="page ui-scroll" role="tabpanel">
          <h4>{{ page.title }}</h4>
          <small v-if="page.since" class="date">{{ noticeDate(page.since) }}</small>
          <p v-if="page.body" class="body">{{ page.body }}</p>
        </article>
        <div class="acts">
          <button v-if="page.daily && !noticeSeen(page.id)" type="button" class="ui-btn" @click="readNotice(page.id)">不再出现</button>
          <button type="button" class="ui-btn primary" @click="closeNoticeBoard">知道了</button>
        </div>
      </div>
    </div>
  </Modal>
</template>

<style scoped>
/* A fixed height, so turning pages does not resize the sheet; each side scrolls on its own. */
.board {
  display: grid;
  grid-template-columns: minmax(128px, 34%) 1fr;
  gap: 18px;
  height: min(380px, calc(100cqh - 150px));
  min-height: 220px;
}
.tabs {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 0;
  overflow-y: auto;
  padding: 2px 4px 2px 0;
}
.tab {
  position: relative;
  flex: none;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 3px;
  width: 100%;
  padding: 9px 22px 9px 12px;
  box-sizing: border-box;
  border: 0;
  border-radius: var(--radius-key);
  background: transparent;
  color: var(--ink-2);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out);
}
.tab:hover {
  background: var(--c-50);
}
.tab.on {
  background: var(--c-100);
  color: var(--ink);
}
.tab.on::before {
  content: "";
  position: absolute;
  left: 0;
  top: 10px;
  bottom: 10px;
  width: 3px;
  border-radius: 2px;
  background: var(--c-500);
}
.tab b {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  font-size: var(--fs-body);
  font-weight: 800;
  line-height: 1.35;
}
.tab small,
.date {
  font-size: var(--fs-caption);
  font-weight: 700;
  color: var(--ink-3);
}
.dot {
  position: absolute;
  top: 12px;
  right: 9px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--c-700);
}
/* The keys sit under the scrolling text, so the text cannot clip their shadow. */
.pane {
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.page {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding-right: 4px;
  animation: turn var(--dur-base) var(--ease-out);
}
.page h4 {
  margin: 0;
  font-size: var(--fs-section);
  font-weight: 800;
  line-height: 1.3;
  color: var(--ink);
}
.date {
  margin-top: 4px;
}
.body {
  margin: 14px 0 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: var(--fs-strong);
  font-weight: 700;
  line-height: 1.55;
  color: var(--ink);
}
.acts {
  flex: none;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding-top: 16px;
}
.acts .primary {
  min-width: 96px;
}
@keyframes turn {
  from { opacity: 0; transform: translateY(6px); }
}
@media (prefers-reduced-motion: reduce) {
  .page { animation: none; }
}
</style>
