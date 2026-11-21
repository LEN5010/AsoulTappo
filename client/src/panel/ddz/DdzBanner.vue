<script setup lang="ts">
// Dou dizhu on the online page, in a room or not: a strip of the table's mat. At rest it carries the key that waits
// in the queue (DdzInvite.vue, a stake to pick) and, in a room, the key that opens a table (on a server without
// open tables, the key that invites), and how many wait in the queue or how many games the room plays; while
// this save waits it shows the stake, the time waited and the key that stops; while an invite is out it seats the three
// with a tick on those who accepted, the stake as a chip after them, and the keys to answer over the time left; at an
// open table it seats who sits there with the empty seats as dashed rings, the stake, and the keys to call someone and
// to put the table away (the opener's) or to leave. While this save sits at a table the key brings up the table's window. Under it, on paper
// (DdzTables.vue), the room's other open tables while this save is free to sit down, and the room's games under way,
// each with the key that watches it, while this save is in no game itself.
import { computed, ref } from "vue";
import { inRoom, members, shownNick, youId } from "../../stores/room";
import { settings } from "../../stores/settings";
import {
  answerDdz, ddz, ddzAtTable, ddzBusy, ddzCanCall, ddzCanWatch, ddzConfig, ddzLink, ddzLive, ddzMatchable, ddzOthersWaiting, ddzPlaying,
  ddzQueue, ddzQueueOn, ddzReason, ddzRetry, ddzTables, leaveDdz, unqueueDdz, type DdzState,
} from "../../stores/ddz";
import { openDdzWindow } from "../../stores/ui";
import Icon from "../../ui/Icon.vue";
import { grow, shrink } from "../../ui/motion";
import DdzCard from "./DdzCard.vue";
import DdzInvite from "./DdzInvite.vue";
import DdzSeats from "./DdzSeats.vue";
import DdzTables from "./DdzTables.vue";
import { useInviteKeys } from "./inviteKeys";
import { useWaited } from "./waited";

/** Bets need an account here and none is signed in (the room page knows the server's info). */
defineProps<{ needAccount?: boolean }>();
/** The sheet that starts a game: from the queue, by invite, by opening a table; or calls someone to the open table. */
const sheet = ref<"match" | "invite" | "open" | "call" | null>(null);
const t = computed(() => (ddz.value?.phase === "invite" || ddz.value?.phase === "over" ? ddz.value : null));
const invite = computed(() => (t.value?.phase === "invite" ? t.value : null));
/** The open table this save sits at. */
const mine = computed(() => (ddz.value?.phase === "open" ? ddz.value : null));
/** The seats' faces; the own seat by its index, as a table of the queue's names this save by another id than the room's. */
const faces = (table: DdzState | null, ticks: boolean) => (table?.seats ?? []).map((s, i) => {
  if (s.pending) return "pending" as const;
  const own = i === table!.you;
  if (!s.id && !own) return null;
  return {
    character: own ? settings.character : s.character,
    nick: own ? settings.nick.trim() || "我" : shownNick(s),
    ticked: ticks && table!.accepted.includes(s.id),
  };
});
const seats = computed(() => faces(invite.value, true));
const mineSeats = computed(() => faces(mine.value, false));
/** Someone of the room may be called to the open table. */
const callable = computed(() => [...members.values()].some(ddzCanCall));
/** How many games the room plays. */
const games = computed(() => Object.keys(ddzLive.value).length);
/** This save sits at a table it walked away from, which is still being played. */
const seated = computed(() => inRoom.value && !ddz.value && ddzPlaying.value.has(youId.value));
/** The room's open tables, while this save is free to sit down at one. */
const roomTables = computed(() => (ddzMatchable.value && !ddzBusy.value && !seated.value && !ddzAtTable.value ? ddzTables.value : []));
/** The room's games under way, to watch, while this save is in no game itself. */
const liveTables = computed(() => (ddzCanWatch.value ? Object.entries(ddzLive.value) : []));
const drain = () => ({ animationDuration: `${Math.max(0, (invite.value?.until ?? 0) - Date.now())}ms` });
const keys = useInviteKeys(() => invite.value?.id, answerDdz);

/** Waiting in the queue (an invite or a table on screen comes first). */
const queued = computed(() => (t.value || ddzAtTable.value ? null : ddzQueue.value));
/** Others waiting at any stake, while this save does not wait and hears the counts (in a room with open tables, or on the dou dizhu connection). */
const othersWaiting = computed(() => ((ddzMatchable.value || ddzLink.value === "open") && !ddzQueue.value
  ? (ddzConfig.value?.stakes ?? []).reduce((n, s) => n + ddzOthersWaiting(s), 0) : 0));
const waited = useWaited(() => queued.value?.since);
</script>

<template>
  <section class="banner" :class="{ inviting: !!invite || !!mine }" data-rise>
    <template v-if="invite">
      <DdzSeats class="who" :seats="seats" :size="44" :stake="invite.base" />
      <div :key="invite.id" class="acts answer">
        <div class="row">
          <template v-if="!invite.sent && !invite.answered">
            <button type="button" class="ui-btn white" @pointerdown="keys.press()" @click="keys.answer(false, $event)">拒绝</button>
            <button type="button" class="ui-btn white" @pointerdown="keys.press()" @click="keys.answer(true, $event)">接受</button>
          </template>
          <button v-else-if="invite.sent" type="button" class="ui-btn white" @click="leaveDdz(invite.id, 'invite')">取消</button>
        </div>
        <span :key="invite.until" class="clock" aria-hidden="true"><i :style="drain()"></i></span>
      </div>
    </template>
    <template v-else-if="mine">
      <DdzSeats class="who" :seats="mineSeats" :size="44" :stake="mine.base" />
      <div v-if="!mine.starting" class="acts">
        <template v-if="mine.you === 0">
          <button type="button" class="ui-btn white" @click="leaveDdz(mine.id, 'open')">散桌</button>
          <button type="button" class="ui-btn white" :disabled="!callable" @click="sheet = 'call'">邀请</button>
        </template>
        <button v-else type="button" class="ui-btn white" @click="leaveDdz(mine.id, 'open')">离开</button>
      </div>
    </template>
    <template v-else>
      <span class="fan" aria-hidden="true">
        <DdzCard :card="51" :width="44" /><DdzCard :card="44" :width="44" /><DdzCard :card="53" :width="44" />
      </span>
      <div class="title">
        <h4>斗地主</h4>
        <p v-if="t" class="note" role="status">{{ ddzReason(t) }}</p>
        <p v-else-if="queued" class="note waiting" role="status">匹配中<b>{{ waited }}</b></p>
        <p v-else-if="ddzQueueOn && ddzRetry" class="note" role="status">稍后再匹配</p>
        <p v-else-if="othersWaiting" class="note">{{ othersWaiting }} 人匹配中</p>
        <p v-else-if="games" class="note">{{ games }} 局进行中</p>
      </div>
      <span v-if="queued" class="stake"><small>底分</small><Icon name="shard" :size="14" /><b>{{ queued.base.toLocaleString("en-US") }}</b></span>
      <div class="acts">
        <button v-if="ddzAtTable" type="button" class="ui-btn white" @click="openDdzWindow()">回到牌桌</button>
        <button v-else-if="queued" type="button" class="ui-btn white" @click="unqueueDdz">取消</button>
        <template v-else>
          <button v-if="ddzMatchable" type="button" class="ui-btn white" :disabled="ddzBusy || seated" @click="sheet = 'open'">
            <Icon name="plus" :size="15" />开桌
          </button>
          <!-- A room on a server without open tables: the invite as before. -->
          <button v-else-if="inRoom" type="button" class="ui-btn white" :disabled="ddzBusy || seated" @click="sheet = 'invite'">
            <Icon name="plus" :size="15" />发起
          </button>
          <button v-if="ddzQueueOn" type="button" class="ui-btn white" :disabled="ddzBusy || seated" @click="sheet = 'match'">匹配</button>
        </template>
      </div>
    </template>
    <DdzInvite v-if="sheet" :mode="sheet" :need-account="needAccount" @close="sheet = null" />
  </section>
  <Transition :css="false" @enter="grow" @leave="shrink">
    <DdzTables v-if="roomTables.length || liveTables.length" :open="roomTables" :live="liveTables" />
  </Transition>
</template>

<style scoped>
/* A strip of the mat: coral, a white line inside its edge, sparse dots in the corner. */
.banner {
  position: relative;
  min-height: 76px;
  padding: 0 18px 0 20px;
  display: flex;
  align-items: center;
  gap: 14px;
  border-radius: var(--radius-l);
  background: var(--grad-sky);
  box-shadow: 0 10px 22px -14px rgba(var(--c-900-rgb), 0.55), inset 0 1px 0 rgba(255, 255, 255, 0.45);
  color: #fff;
  overflow: hidden;
}
.banner.inviting { min-height: 104px; }
.banner::before {
  content: "";
  position: absolute;
  inset: 7px;
  border-radius: 10px;
  box-shadow: inset 0 0 0 1.5px rgba(255, 255, 255, 0.5);
  pointer-events: none;
}
/* At rest the cards rise out of the bottom left corner: the line gives way there instead of running behind them. */
.banner:not(.inviting)::before {
  mask: radial-gradient(ellipse 64px 46px at 54px 100%, transparent 70%, #000 100%);
}
.banner::after {
  content: "";
  position: absolute;
  inset: 0;
  background: #fff;
  opacity: 0.3;
  pointer-events: none;
  mask: radial-gradient(circle, #000 1.1px, transparent 1.5px) 0 0 / 14px 14px, radial-gradient(90% 160% at 100% 0, #000 10%, transparent 55%);
  mask-composite: intersect;
  -webkit-mask-composite: source-in;
}
.banner > * { position: relative; z-index: 1; }
/* Three cards held as a hand: turned about one point under the strip, each over the one before it, so the big joker on
   the right shows 阿草 whole; their feet are cut off by the strip's edge. */
.fan { flex: none; position: relative; align-self: stretch; width: 92px; margin-left: -6px; }
/* Over the card's own `position: relative`. */
.banner .fan > * { position: absolute; left: calc(50% - 22px); bottom: -8px; transform-origin: 50% 170%; }
.fan > :nth-child(1) { rotate: -16deg; }
.fan > :nth-child(3) { rotate: 16deg; }
.title { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 4px; }
.title h4 { margin: 0; font: 800 22px/1 var(--font); letter-spacing: 1px; text-shadow: 0 2px 0 var(--c-600); }
.note { margin: 0; font: 800 var(--fs-label)/1.2 var(--font); opacity: 0.95; }
/* The time waited ticks in figures of one width, so the line does not jitter. */
.note.waiting { display: flex; align-items: baseline; gap: 6px; }
.note.waiting b { font: 800 var(--fs-label)/1.2 var(--font-latin); font-variant-numeric: tabular-nums; }
.acts { flex: none; margin-left: auto; display: flex; gap: 8px; }
.acts .ui-btn { height: 38px; min-width: 76px; padding: 0 16px; }
/* Every key on coral is white (the button spec: a change of colour only means selected). */
.ui-btn.white { --key-lip: var(--c-700); color: var(--c-800); }
.acts .ui-btn:disabled { --key-top: rgba(255, 255, 255, 0.35); --key-bottom: rgba(255, 255, 255, 0.35); color: rgba(255, 255, 255, 0.9); }
.who { flex: 0 1 auto; min-width: 0; padding: 16px 0 14px; margin-left: -4px; }
/* The keys that answer an invite stand over the time left to do it. */
.acts.answer { flex-direction: column; align-items: stretch; gap: 9px; min-width: 160px; }
.acts .row { display: flex; justify-content: flex-end; gap: 8px; }
.stake { display: flex; align-items: center; gap: 4px; font: 800 20px/1 var(--font-latin); }
.stake small { width: 30px; font: 800 var(--fs-caption)/1 var(--font); opacity: 0.9; }
.clock { display: block; height: 4px; border-radius: 2px; background: rgba(255, 255, 255, 0.35); overflow: hidden; }
.clock i { display: block; height: 100%; border-radius: 2px; background: #fff; transform-origin: 0 50%; animation: drain linear forwards; }
@keyframes drain {
  to { transform: scaleX(0); }
}
</style>
