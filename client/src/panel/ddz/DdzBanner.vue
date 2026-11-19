<script setup lang="ts">
// Dou dizhu on the room page: a strip of the table's mat. At rest it carries the key that starts a game (and the
// faces of members playing one); while an invite is out it seats the three with a tick on those who accepted, the
// stake, and the keys to answer. While this save sits at a table the key brings up the table's window.
import { computed, ref } from "vue";
import { members, shownNick, youId } from "../../stores/room";
import { settings } from "../../stores/settings";
import { answerDdz, ddz, ddzAtTable, ddzBusy, ddzLive, ddzPlaying, ddzReason, leaveDdz } from "../../stores/ddz";
import { openDdzWindow } from "../../stores/ui";
import Icon from "../../ui/Icon.vue";
import DdzCard from "./DdzCard.vue";
import DdzInvite from "./DdzInvite.vue";
import DdzSeats from "./DdzSeats.vue";

/** Bets need an account here and none is signed in (the room page knows the server's info). */
defineProps<{ needAccount?: boolean }>();
const starting = ref(false);
const t = computed(() => (ddz.value?.phase === "invite" || ddz.value?.phase === "over" ? ddz.value : null));
const invite = computed(() => (t.value?.phase === "invite" ? t.value : null));
const seats = computed(() => (invite.value?.seats ?? []).map((s) => ({
  character: s.id === youId.value ? settings.character : s.character,
  nick: s.id === youId.value ? settings.nick.trim() || "我" : shownNick(s),
  ticked: invite.value!.accepted.includes(s.id),
})));
/** The tables of the room, as the faces of their members who are still here. */
const tables = computed(() => Object.values(ddzLive.value).map((ids) =>
  ids.map((id) => members.get(id)).filter((m) => !!m).map((m) => ({ character: m.character, nick: shownNick(m) }))).filter((x) => x.length));
/** This save sits at a table it walked away from, which is still being played. */
const seated = computed(() => !ddz.value && ddzPlaying.value.has(youId.value));
const drain = () => ({ animationDuration: `${Math.max(0, (invite.value?.until ?? 0) - Date.now())}ms` });
</script>

<template>
  <section class="banner" :class="{ inviting: !!invite }" data-rise>
    <template v-if="invite">
      <DdzSeats class="who" :seats="seats" :size="44" />
      <div class="deal">
        <span class="stake"><small>底分</small><Icon name="shard" :size="14" /><b>{{ invite.base.toLocaleString("en-US") }}</b></span>
      </div>
      <div class="acts">
        <template v-if="!invite.sent && !invite.answered">
          <button type="button" class="ui-btn" @click="answerDdz(false)">拒绝</button>
          <button type="button" class="ui-btn white" @click="answerDdz(true)">接受</button>
        </template>
        <button v-else-if="invite.sent" type="button" class="ui-btn" @click="leaveDdz">取消</button>
      </div>
      <span :key="invite.until" class="clock" aria-hidden="true"><i :style="drain()"></i></span>
    </template>
    <template v-else>
      <span class="fan" aria-hidden="true">
        <DdzCard :card="51" :width="44" /><DdzCard :card="44" :width="44" /><DdzCard :card="53" :width="44" />
      </span>
      <div class="title">
        <h4>斗地主</h4>
        <p v-if="t" class="note" role="status">{{ ddzReason(t) }}</p>
      </div>
      <div v-if="tables.length" class="live">
        <DdzSeats v-for="(faces, i) in tables" :key="i" :seats="faces" :size="26" bare />
        <span class="ui-tag light">牌局中</span>
      </div>
      <div class="acts">
        <button v-if="ddzAtTable" type="button" class="ui-btn white" @click="openDdzWindow()">回到牌桌</button>
        <button v-else type="button" class="ui-btn white" :disabled="ddzBusy || seated" @click="starting = true">
          <Icon name="plus" :size="15" />发起
        </button>
      </div>
    </template>
    <DdzInvite v-if="starting" :need-account="needAccount" @close="starting = false" />
  </section>
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
.live { flex: none; display: flex; align-items: center; gap: 10px; }
.acts { flex: none; margin-left: auto; display: flex; gap: 8px; }
.acts .ui-btn { height: 38px; min-width: 76px; padding: 0 16px; }
/* A white key on coral: the one to press. */
.ui-btn.white { --key-lip: var(--c-700); color: var(--c-800); }
.acts .ui-btn:not(.white):not(:disabled) { --key-top: var(--c-300); --key-bottom: var(--c-300); --key-lip: var(--c-600); color: #fff; }
.acts .ui-btn:disabled { --key-top: rgba(255, 255, 255, 0.35); --key-bottom: rgba(255, 255, 255, 0.35); color: rgba(255, 255, 255, 0.9); }
.who { flex: none; padding: 14px 0 12px; }
.deal { min-width: 0; flex: 1; display: flex; flex-direction: column; gap: 6px; }
.stake { display: flex; align-items: center; gap: 4px; font: 800 20px/1 var(--font-latin); }
.stake small { width: 30px; font: 800 var(--fs-caption)/1 var(--font); opacity: 0.9; }
/* The time left to answer, along the foot of the strip. */
.clock { position: absolute; left: 20px; right: 20px; bottom: 12px; height: 4px; border-radius: 2px; background: rgba(255, 255, 255, 0.35); overflow: hidden; }
.clock i { display: block; height: 100%; border-radius: 2px; background: #fff; transform-origin: 0 50%; animation: drain linear forwards; }
@keyframes drain {
  to { transform: scaleX(0); }
}
</style>
