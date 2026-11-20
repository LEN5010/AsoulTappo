<script setup lang="ts">
// The dou dizhu lobby, the face of the table's window while this save sits at no table (DdzApp.vue; the browser
// preview floats it over the desk page, pet/DdzFrame.vue): on a coral mat the three stakes as big keys, each with how
// many wait there; pressing one waits in the queue there, and that key shows the time waited and the key that stops.
// A table the queue made, or an invite, comes up on the mat to answer; an open table this save sits at, with the key
// that stands up. Under the mat, today's net win and what is left under the cap; in a room, the room's open tables
// and the key that opens one. The numbers come from GET /api/ddz/lobby, read every few seconds while it is in sight.
import { computed, onBeforeUnmount, ref, watch } from "vue";
import type { DdzLobby } from "../../net/protocol";
import { loadDdzLobby, status } from "../../stores/player";
import { duelDnd, members, shownNick } from "../../stores/room";
import { settings } from "../../stores/settings";
import {
  answerDdz, ddz, ddzBusy, ddzCanCall, ddzConfig, ddzDeposit, ddzLink, ddzLinkOff, ddzMatchable, ddzOthersWaiting, ddzQueue,
  ddzReason, ddzRetry, ddzStakeOpen, ddzTableSeen, ddzTables, leaveDdz, queueDdz, unqueueDdz, type DdzState,
} from "../../stores/ddz";
import Icon from "../../ui/Icon.vue";
import DdzInvite from "./DdzInvite.vue";
import DdzOpenRow from "./DdzOpenRow.vue";
import DdzSeats from "./DdzSeats.vue";
import { useInviteKeys } from "./inviteKeys";
import { useWaited } from "./waited";

const emit = defineEmits<{ close: []; drag: [e: PointerEvent] }>();

/** How often the lobby's numbers are read while it is in sight. */
const POLL_MS = 4000;
const lobby = ref<DdzLobby | null>(null);
const off = ref(false);
let poll: ReturnType<typeof setTimeout> | undefined;
let alive = true;
async function read() {
  clearTimeout(poll);
  const got = await loadDdzLobby();
  if (!alive) return;
  if (got === "off") off.value = true;
  else if (got) lobby.value = got;
  if (ddzTableSeen.value) poll = setTimeout(read, POLL_MS);
}
watch(ddzTableSeen, (seen) => { if (seen) void read(); else clearTimeout(poll); }, { immediate: true });
// Waiting or not changes the counts and the shards: read again at once.
watch(() => [ddzQueue.value?.base, ddz.value?.phase], () => { if (ddzTableSeen.value) void read(); });
onBeforeUnmount(() => { alive = false; clearTimeout(poll); });

const stakes = computed(() => ddzConfig.value?.stakes ?? []);
/** A stake this save can pay: as the server last said, and as its shards say now. */
const affords = (base: number) => (lobby.value?.tiers.find((x) => x.base === base)?.afford ?? true) && ddzStakeOpen(base);
/** Others waiting at [base]: the connection's counts while it is up, else the lobby's last read. */
function waitingAt(base: number): number {
  if (ddzLink.value === "open") return ddzOthersWaiting(base);
  const n = lobby.value?.tiers.find((x) => x.base === base)?.waiting ?? 0;
  return Math.max(0, n - (ddzQueue.value?.base === base ? 1 : 0));
}

/** An invite or a table of the queue to answer, or how one ended. */
const asked = computed(() => (ddz.value?.phase === "invite" || ddz.value?.phase === "over" ? ddz.value : null));
/** The open table this save sits at. */
const mine = computed(() => (ddz.value?.phase === "open" ? ddz.value : null));
const faces = (t: DdzState, ticks: boolean) => t.seats.map((s, i) => {
  if (s.pending) return "pending" as const;
  if (i === t.you) return { character: settings.character, nick: settings.nick.trim() || "我", ticked: ticks && t.accepted.includes(s.id) };
  if (!s.id) return null;
  return { character: s.character, nick: shownNick(s), ticked: ticks && t.accepted.includes(s.id) };
});
const keys = useInviteKeys(() => (asked.value?.phase === "invite" ? asked.value.id : undefined), answerDdz);
const drain = (until: number) => ({ animationDuration: `${Math.max(0, until - Date.now())}ms` });

const waited = useWaited(() => ddzQueue.value?.since);

/** What keeps this save out of the queue, in words; "" when nothing does. */
const blocked = computed(() => {
  const cfg = ddzConfig.value;
  const l = lobby.value;
  if (off.value || ddzLinkOff.value) return "这个服务器不能匹配";
  if (!cfg || !status.value?.ddz) return "";
  if (l && !l.account) return "登录 Asasfans 账号后才能斗地主";
  const taps = l?.taps ?? status.value.totals.taps;
  if (taps < cfg.minTaps) {
    const need = cfg.minTaps % 10000 === 0 ? `${cfg.minTaps / 10000} 万` : cfg.minTaps.toLocaleString("en-US");
    return `累计敲击满 ${need} 下后可以斗地主`;
  }
  if ((l?.left ?? cfg.dailyWinCap - (status.value.ddz.net ?? 0)) <= 0) return "今天赢到上限了，明天再来";
  if (duelDnd()) return "免打扰时不能匹配";
  if (ddzRetry.value && !ddzQueue.value) return "稍后再匹配";
  if (ddzBusy.value && !asked.value && !mine.value) return "你已经在牌桌上";
  return "";
});

const net = computed(() => lobby.value?.net ?? status.value?.ddz?.net ?? 0);
const left = computed(() => lobby.value?.left ?? Math.max(0, (ddzConfig.value?.dailyWinCap ?? 0) - net.value));
const signed = (n: number) => `${n > 0 ? "+" : ""}${n.toLocaleString("en-US")}`;

/** The room's open tables, while this save is free to sit down at one. */
const roomTables = computed(() => (ddzMatchable.value && !ddzBusy.value ? ddzTables.value : []));
/** The sheet that opens a table in the room, or calls someone to the open table this save opened. */
const sheet = ref<"open" | "call" | null>(null);
const callable = computed(() => [...members.values()].some(ddzCanCall));
</script>

<template>
  <div class="lobby" data-overlay>
    <div class="wall" @pointerdown.self="(e) => e.button === 0 && emit('drag', e)">
      <header class="top" @pointerdown.self="(e) => e.button === 0 && emit('drag', e)">
        <h2>斗地主</h2>
        <button type="button" class="ui-btn small ghost shut-key" title="关闭" aria-label="关闭" @click="emit('close')">
          <Icon name="close" :size="18" />
        </button>
      </header>

      <section class="mat">
        <!-- A table to answer: its seats, the stake, the keys, and the time left. -->
        <div v-if="asked" :key="asked.id" class="ask">
          <DdzSeats :seats="faces(asked, true)" :size="64" />
          <span class="stake"><small>底分</small><Icon name="shard" :size="18" /><b>{{ asked.base.toLocaleString("en-US") }}</b></span>
          <p v-if="asked.phase === 'over'" class="line">{{ ddzReason(asked) }}</p>
          <div v-else-if="!asked.sent" class="acts">
            <button type="button" class="ui-btn white large" :disabled="asked.answered" @pointerdown="keys.press()" @click="keys.answer(false, $event)">拒绝</button>
            <button type="button" class="ui-btn white large" :disabled="asked.answered" @pointerdown="keys.press()" @click="keys.answer(true, $event)">接受</button>
          </div>
          <div v-else class="acts">
            <button type="button" class="ui-btn white large" @click="leaveDdz(asked.id, 'invite')">取消</button>
          </div>
        </div>
        <!-- The open table this save sits at. -->
        <div v-else-if="mine" :key="mine.id" class="ask">
          <DdzSeats :seats="faces(mine, false)" :size="64" />
          <span class="stake"><small>底分</small><Icon name="shard" :size="18" /><b>{{ mine.base.toLocaleString("en-US") }}</b></span>
          <div v-if="!mine.starting" class="acts">
            <template v-if="mine.you === 0">
              <button type="button" class="ui-btn white large" @click="leaveDdz(mine.id, 'open')">散桌</button>
              <button v-if="mine.via === 'room'" type="button" class="ui-btn white large" :disabled="!callable" @click="sheet = 'call'">邀请</button>
            </template>
            <button v-else type="button" class="ui-btn white large" @click="leaveDdz(mine.id, 'open')">起身</button>
          </div>
        </div>
        <!-- The stakes: a key each; the one waited at shows the time and the key that stops. -->
        <template v-else>
          <div class="tiers">
            <template v-for="s in stakes" :key="s">
              <div v-if="ddzQueue?.base === s" class="tier waiting" role="status">
                <span class="base"><Icon name="shard" :size="26" />{{ s.toLocaleString("en-US") }}</span>
                <span class="time">匹配中<b>{{ waited }}</b></span>
                <button type="button" class="ui-btn white" @click="unqueueDdz">取消</button>
              </div>
              <button
                v-else type="button" class="ui-btn white tier" :disabled="!!blocked || !affords(s)"
                :title="affords(s) ? undefined : `碎片不够押金 ${ddzDeposit(s).toLocaleString('en-US')}`" @click="queueDdz(s)"
              >
                <span class="base"><Icon name="shard" :size="26" />{{ s.toLocaleString("en-US") }}</span>
                <span class="count"><Icon name="users" :size="13" />{{ waitingAt(s) }}</span>
              </button>
            </template>
          </div>
          <p v-if="blocked" class="line">{{ blocked }}</p>
        </template>
        <span v-if="asked?.phase === 'invite'" :key="asked.until" class="clock" aria-hidden="true"><i :style="drain(asked.until)"></i></span>
      </section>

      <footer class="today">
        <span>今日<b :class="{ up: net > 0, down: net < 0 }">{{ signed(net) }}</b></span>
        <span>还可赢<b>{{ left.toLocaleString("en-US") }}</b></span>
      </footer>

      <section v-if="ddzMatchable" class="room">
        <header>
          <h3>房间</h3>
          <button type="button" class="ui-btn" :disabled="ddzBusy" @click="sheet = 'open'"><Icon name="plus" :size="15" />开桌</button>
        </header>
        <div v-if="roomTables.length" class="rows">
          <DdzOpenRow v-for="x in roomTables" :key="x.table" :table="x" />
        </div>
      </section>
    </div>
    <div class="lobby-overlay"></div>
    <DdzInvite v-if="sheet" :mode="sheet" to=".lobby-overlay" @close="sheet = null" />
  </div>
</template>

<style scoped>
.lobby { position: absolute; inset: 0; overflow: hidden; border-radius: var(--radius-l); }
.lobby-overlay { position: absolute; inset: 0; z-index: 10; overflow: hidden; border-radius: var(--radius-l); pointer-events: none; }
.lobby-overlay > :deep(*) { pointer-events: auto; }
/* The same light wall as the table's. */
.wall {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 12px 20px 20px;
  box-sizing: border-box;
  background: var(--c-100);
  font-family: var(--font);
  color: var(--ink);
  user-select: none;
  overflow: auto;
}
.top { display: flex; align-items: center; justify-content: space-between; height: 36px; }
.top h2 { margin: 0 0 0 6px; font: 800 var(--fs-heading)/1 var(--font); color: var(--c-700); pointer-events: none; }
.shut-key { width: 40px; height: 36px; padding: 0; }

/* The mat: as the table's, a coral block with a white line inside its edge and sparse dots in the corner. */
.mat {
  position: relative;
  flex: 1;
  min-height: 300px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 18px;
  padding: 36px 32px;
  border-radius: 26px;
  background: var(--grad-sky);
  box-shadow: 0 12px 28px -16px rgba(var(--c-900-rgb), 0.55), inset 0 1px 0 rgba(255, 255, 255, 0.45);
  color: #fff;
}
.mat::before {
  content: "";
  position: absolute;
  inset: 11px;
  border-radius: 17px;
  box-shadow: inset 0 0 0 1.5px rgba(255, 255, 255, 0.5);
  pointer-events: none;
}
.mat::after {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: #fff;
  opacity: 0.3;
  pointer-events: none;
  mask: radial-gradient(circle, #000 1.3px, transparent 1.8px) 0 0 / 18px 18px, radial-gradient(120% 100% at 100% 0, #000 10%, transparent 55%);
  mask-composite: intersect;
  -webkit-mask-composite: source-in;
}
.mat > * { position: relative; z-index: 1; }

/* Every key on coral is white (the button spec: a change of colour only means selected). */
.ui-btn.white { --key-lip: var(--c-700); color: var(--c-800); }
.mat .ui-btn:disabled { --key-top: rgba(255, 255, 255, 0.35); --key-bottom: rgba(255, 255, 255, 0.35); color: rgba(255, 255, 255, 0.9); }

/* The stakes: three big keys, the stake in the middle and how many wait there in the corner. */
.tiers { width: 100%; max-width: 820px; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 20px; }
.tier {
  position: relative;
  height: 168px;
  padding: 0;
  flex-direction: column;
  gap: 10px;
  border-radius: 20px;
}
.tier .base { display: flex; align-items: center; gap: 4px; font: 800 52px/1 var(--font-latin); letter-spacing: -1px; }
.tier .base .icon { color: var(--c-500); }
.tier:disabled .base .icon { color: inherit; }
.tier .count {
  position: absolute;
  top: 12px;
  right: 14px;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font: 800 var(--fs-strong)/1 var(--font-latin);
  color: var(--c-600);
}
.tier:disabled .count { color: inherit; }
/* The stake waited at: the key turned over, white on the mat, with the time and the key that stops. */
.tier.waiting {
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px dashed rgba(255, 255, 255, 0.8);
  background: rgba(255, 255, 255, 0.16);
  color: #fff;
}
.tier.waiting .base { font-size: 40px; }
.tier.waiting .base .icon { color: #fff; }
.tier.waiting .time { display: flex; align-items: baseline; gap: 6px; font: 800 var(--fs-strong)/1 var(--font); }
.tier.waiting .time b { font: 800 var(--fs-section)/1 var(--font-latin); font-variant-numeric: tabular-nums; }
.tier.waiting .ui-btn { height: 28px; padding: 0 14px; font-size: var(--fs-label); }

.line { margin: 0; font: 800 var(--fs-strong)/1.4 var(--font); text-align: center; opacity: 0.95; }

/* A table to answer, or the open table this save sits at. */
.ask { display: flex; flex-direction: column; align-items: center; gap: 16px; width: 100%; max-width: 520px; }
.ask :deep(.tag) { color: var(--ink); }
.stake { display: flex; align-items: center; gap: 5px; font: 800 28px/1 var(--font-latin); }
.stake small { font: 800 var(--fs-label)/1 var(--font); opacity: 0.9; margin-right: 2px; }
.acts { display: flex; gap: 12px; }
.acts .ui-btn { min-width: 120px; }
/* The time left to answer, along the foot of the mat. */
.mat > .clock { position: absolute; left: 32px; right: 32px; bottom: 22px; height: 5px; border-radius: 3px; background: rgba(255, 255, 255, 0.35); overflow: hidden; }
.clock i { display: block; height: 100%; border-radius: 3px; background: #fff; transform-origin: 0 50%; animation: drain linear forwards; }
@keyframes drain {
  to { transform: scaleX(0); }
}

/* Today: the net win and what is left under the cap, as two figures on the wall. */
.today { display: flex; justify-content: center; gap: 28px; font: 800 var(--fs-body)/1 var(--font); color: var(--ink-2); }
.today span { display: flex; align-items: baseline; gap: 6px; }
.today b { font: 800 var(--fs-section)/1 var(--font-latin); color: var(--ink); font-variant-numeric: tabular-nums; }
.today b.up { color: var(--c-600); }

/* The room's open tables, on a strip of the mat each, and the key that opens one. */
.room { display: flex; flex-direction: column; gap: 10px; }
.room header { display: flex; align-items: center; justify-content: space-between; }
.room h3 { margin: 0 0 0 6px; font: 800 var(--fs-strong)/1 var(--font); color: var(--ink-2); }
.rows {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 18px 12px 20px;
  border-radius: var(--radius-l);
  background: var(--grad-sky);
  color: #fff;
}
</style>
