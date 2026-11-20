<script setup lang="ts">
// Over the own pet for dou dizhu: an invite to answer (or the own invite waiting), with the three faces and a tick
// on those who accepted; a call to an open table of the room, with who sits there and the key that sits down; how an
// invite ended; and, while a game goes on with the table out of sight, a key that brings the table up. The server
// keeps the time; the bar only shows it.
import { computed } from "vue";
import { answerDdz, ddz, ddzBubble, ddzCall, ddzCanSit, ddzReason, dismissDdzCall, leaveDdz, sitDdz } from "../stores/ddz";
import { shownNick, youId } from "../stores/room";
import { settings } from "../stores/settings";
import { openDdzWindow } from "../stores/ui";
import DdzSeats from "../panel/ddz/DdzSeats.vue";
import { useInviteKeys } from "../panel/ddz/inviteKeys";
import Icon from "../ui/Icon.vue";
import PetBubble from "./PetBubble.vue";
import { DDZ_WIDTH } from "./duelPick";

defineProps<{ shift?: number; below?: boolean }>();

const t = computed(() => ddz.value);
const call = computed(() => (ddzBubble.value === "call" ? ddzCall.value : null));
const seats = computed(() => {
  if (call.value) return call.value.seats.map((s) => (!s ? null : "id" in s ? { character: s.character, nick: shownNick(s) } : "pending" as const));
  return (t.value?.seats ?? []).map((s) => (!s.id ? null : {
    character: s.id === youId.value ? settings.character : s.character,
    nick: s.id === youId.value ? "我" : shownNick(s),
    ticked: t.value!.accepted.includes(s.id),
  }));
});
const base = computed(() => call.value?.base ?? t.value?.base ?? 0);
const drain = () => ({ animationDuration: `${Math.max(0, (call.value?.until ?? t.value?.until ?? 0) - Date.now())}ms` });
const keys = useInviteKeys(() => (ddzBubble.value === "invite" ? t.value?.id : undefined), answerDdz);
// Sitting down at the table called to is consent, as accepting is: the same guard.
const callKeys = useInviteKeys(() => call.value?.table, (sit, table) => (sit ? sitDdz(table) : dismissDdzCall()));
</script>

<template>
  <PetBubble :open="!!ddzBubble" :width="ddzBubble === 'turn' || ddzBubble === 'table' ? 148 : DDZ_WIDTH" :shift="shift" :below="below">
    <div v-if="call" :key="`call-${call.table}`" class="ddz" role="dialog" aria-label="斗地主">
      <header class="who">
        <DdzSeats :seats="seats" :size="28" bare />
        <span class="stake"><Icon name="shard" :size="13" />{{ base.toLocaleString("en-US") }}</span>
      </header>
      <div class="body">
        <div class="keys">
          <button type="button" class="ui-btn primary" :disabled="!ddzCanSit(call.base)" @pointerdown="callKeys.press()" @click="callKeys.answer(true, $event)">入座</button>
          <button type="button" class="ui-btn" @pointerdown="callKeys.press()" @click="callKeys.answer(false, $event)">拒绝</button>
        </div>
      </div>
      <div :key="call.until" class="ui-bar" aria-hidden="true"><i :style="drain()" /></div>
    </div>
    <div v-else-if="t && ddzBubble" :key="`${t.id}-${ddzBubble === 'invite' || ddzBubble === 'over' ? 'ask' : 'game'}`" class="ddz" role="dialog" aria-label="斗地主">
      <button v-if="ddzBubble === 'turn' || ddzBubble === 'table'" type="button" class="ui-btn back" :class="{ primary: ddzBubble === 'turn' }" @click="openDdzWindow()">
        {{ ddzBubble === "turn" ? "轮到你了" : "回到牌桌" }}
      </button>
      <template v-else>
        <header class="who">
          <DdzSeats :seats="seats" :size="28" bare />
          <span class="stake"><Icon name="shard" :size="13" />{{ base.toLocaleString("en-US") }}</span>
        </header>
        <div class="body" :class="{ tall: ddzBubble === 'over' }">
          <p v-if="ddzBubble === 'over'" class="line">{{ ddzReason(t) }}</p>
          <div v-else-if="!t.sent" class="keys">
            <button type="button" class="ui-btn primary" :disabled="t.answered" @pointerdown="keys.press()" @click="keys.answer(true, $event)">接受</button>
            <button type="button" class="ui-btn" :disabled="t.answered" @pointerdown="keys.press()" @click="keys.answer(false, $event)">拒绝</button>
          </div>
          <div v-else class="keys one">
            <p class="line">等待回应</p>
            <button type="button" class="ui-btn" @click="leaveDdz(t.id, 'invite')">取消</button>
          </div>
        </div>
        <div v-if="ddzBubble === 'invite'" :key="t.until" class="ui-bar" aria-hidden="true"><i :style="drain()" /></div>
      </template>
    </div>
  </PetBubble>
</template>

<style scoped>
.ddz { display: flex; flex-direction: column; gap: 8px; }
.who { display: flex; align-items: center; justify-content: space-between; gap: 8px; height: 30px; padding: 0 2px; }
/* On paper an empty seat's ring takes the coral of the mat. */
.who :deep(.empty .face) { border-color: var(--c-300); }
.stake { flex: none; display: inline-flex; align-items: center; gap: 2px; font: 800 var(--fs-strong)/1 var(--font-latin); color: var(--c-700); }
/* One row for every step, so the paper keeps its size; without a countdown the row also takes the bar's place. */
.body { height: 44px; display: flex; align-items: center; justify-content: center; }
.body.tall { height: 58px; }
.keys { display: grid; grid-template-columns: 1fr 1fr; align-items: center; gap: 6px; width: 100%; }
.keys .ui-btn { min-width: 0; height: 40px; padding: 0; }
.line { margin: 0; font: 800 var(--fs-label)/1.35 var(--font); color: var(--ink-2); text-align: center; }
.back { width: 100%; height: 40px; padding: 0; }
/* The bar empties as the time runs out. */
.ui-bar { height: 6px; }
.ui-bar > i { width: 100%; transition: none; transform-origin: 0 50%; animation: drain linear forwards; }
@keyframes drain {
  to { transform: scaleX(0); }
}
</style>
