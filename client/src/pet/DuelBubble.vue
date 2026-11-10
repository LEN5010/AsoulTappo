<script setup lang="ts">
// Over the own pet for the length of a rock-paper-scissors duel: the invite to answer (or the own invite waiting),
// the three hands to throw, then how it ended. Every step keeps the same frame: the other member and the bet on top,
// one row of keys or hands, the countdown bar at the bottom. The server keeps the time; the bar only shows it.
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { HANDS, type Hand } from "../net/protocol";
import { answerDuel, duel, throwHand } from "../stores/room";
import CharacterAvatar from "../ui/CharacterAvatar.vue";
import Icon from "../ui/Icon.vue";
import HandImg from "./HandImg.vue";
import PetBubble from "./PetBubble.vue";
import { DUEL_WIDTH } from "./duelPick";

defineProps<{ shift?: number; below?: boolean }>();

const HAND_NAMES: Record<Hand, string> = { rock: "石头", scissors: "剪刀", paper: "布" };
const REASONS: Record<string, string> = {
  declined: "对方不接受", timeout: "对方没有回应", gone: "对方已离开", no_shards: "碎片不足", duel_cap: "超出今天的上限",
  idle: "都没出拳，已退还", draws: "平局太多，已退还",
};

const now = ref(Date.now());
let timer: ReturnType<typeof setInterval> | undefined;
watch(() => duel.value?.until, (until) => {
  clearInterval(timer);
  now.value = Date.now();
  if (!until || until <= now.value) return;
  timer = setInterval(() => {
    now.value = Date.now();
    if (now.value >= until) clearInterval(timer);
  }, 100);
}, { immediate: true });
onBeforeUnmount(() => clearInterval(timer));

const d = computed(() => duel.value);
const ticking = computed(() => d.value?.phase === "invite" || d.value?.phase === "throw");
const left = computed(() => {
  const x = d.value;
  return x && ticking.value ? Math.max(0, Math.min(1, (x.until - now.value) / (x.sec * 1000))) : 0;
});
</script>

<template>
  <PetBubble :open="!!d" :width="DUEL_WIDTH" :shift="shift" :below="below">
    <div v-if="d" :key="d.id" class="duel" role="dialog" aria-label="猜拳">
      <header class="who">
        <CharacterAvatar v-if="d.other.character" :character="d.other.character" :size="24" />
        <b>{{ d.other.nick }}</b>
        <span class="bet"><Icon name="shard" :size="13" />{{ d.bet.toLocaleString("en-US") }}</span>
      </header>

      <!-- Hands of the last draw, mine on the left facing theirs. -->
      <div v-if="d.phase === 'throw' && d.shown" class="draw">
        <span class="ui-tag light">平局</span>
        <span class="face small">
          <HandImg v-if="d.shown.mine" class="hand mine" :name="d.shown.mine" :size="22" />
          <HandImg v-if="d.shown.theirs" class="hand theirs" :name="d.shown.theirs" :size="22" />
        </span>
      </div>

      <div class="body" :class="{ tall: !ticking }">
        <template v-if="d.phase === 'invite'">
          <div v-if="!d.sent" class="keys two">
            <button type="button" class="ui-btn primary" :disabled="d.answered" @click="answerDuel(true)">接受</button>
            <button type="button" class="ui-btn" :disabled="d.answered" @click="answerDuel(false)">拒绝</button>
          </div>
          <p v-else class="line">等待回应</p>
        </template>

        <div v-else-if="d.phase === 'throw'" class="keys three">
          <button
            v-for="h in HANDS" :key="h" type="button" class="ui-btn hand-key" :class="{ on: d.hand === h }"
            :aria-pressed="d.hand === h" :disabled="!!d.hand && d.hand !== h" :title="HAND_NAMES[h]" :aria-label="HAND_NAMES[h]"
            @click="throwHand(h)"
          >
            <HandImg :name="h" :size="28" />
          </button>
        </div>

        <div v-else-if="d.phase === 'result'" class="face">
          <span class="slot" :class="{ lost: !d.won }">
            <HandImg v-if="d.shown?.mine" class="hand mine" :name="d.shown.mine" :size="34" />
            <i v-else class="none">?</i>
          </span>
          <b class="verdict" :class="{ won: d.won }">
            {{ d.won ? "赢了" : "输了" }}<span v-if="d.won" class="gain"><Icon name="shard" :size="14" />+{{ d.prize.toLocaleString("en-US") }}</span>
          </b>
          <span class="slot" :class="{ lost: d.won }">
            <HandImg v-if="d.shown?.theirs" class="hand theirs" :name="d.shown.theirs" :size="34" />
            <i v-else class="none">?</i>
          </span>
        </div>

        <p v-else class="line">{{ REASONS[d.reason] ?? "已取消" }}</p>
      </div>

      <div v-if="ticking" class="ui-bar" aria-hidden="true"><i :style="{ width: `${left * 100}%` }" /></div>
    </div>
  </PetBubble>
</template>

<style scoped>
.duel { display: flex; flex-direction: column; gap: 8px; }
.who { display: flex; align-items: center; gap: 6px; min-width: 0; height: 24px; }
.who b { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font: 800 var(--fs-label)/1.3 var(--font); }
.bet { flex: none; display: inline-flex; align-items: center; gap: 2px; font: 800 var(--fs-label)/1 var(--font-latin); color: var(--c-700); }
/* One row for every step, so the paper keeps its size from the invite to the result: without a countdown the row
   also takes the bar's place. */
.body { height: 44px; display: flex; align-items: center; justify-content: center; }
.body.tall { height: 58px; }
.keys { display: grid; gap: 6px; width: 100%; }
.keys.two { grid-template-columns: 1fr 1fr; }
.keys.three { grid-template-columns: repeat(3, 1fr); }
.keys .ui-btn { min-width: 0; height: 40px; padding: 0; }
.hand-key:disabled { opacity: 0.55; }
.line { margin: 0; font: 800 var(--fs-label)/1.35 var(--font); color: var(--ink-2); text-align: center; }
.draw { display: flex; align-items: center; justify-content: center; gap: 8px; height: 20px; }
/* Two hands face to face: mine on the left, theirs mirrored on the right. */
.face { display: flex; align-items: center; justify-content: center; gap: 10px; width: 100%; }
.face.small { width: auto; gap: 4px; }
.hand.theirs { scale: -1 1; }
.slot { flex: none; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center; color: var(--ink); }
.slot.lost { color: var(--ink-3); }
.none {
  width: 30px; height: 30px; box-sizing: border-box; border: 2px dashed var(--ink-3); border-radius: 50%;
  display: flex; align-items: center; justify-content: center; font: 800 13px/1 var(--font-latin); font-style: normal; color: var(--ink-3);
}
.verdict { flex: 1; min-width: 0; display: inline-flex; align-items: center; justify-content: center; font: 800 var(--fs-strong)/1 var(--font); color: var(--ink-2); white-space: nowrap; }
.verdict.won { color: var(--ink); }
.gain { display: inline-flex; align-items: center; gap: 2px; margin-left: 4px; font: 800 var(--fs-label)/1 var(--font-latin); color: var(--c-700); }
/* The bar empties as the time runs out; no transition, so it also counts down with reduced motion. */
.ui-bar { height: 6px; }
.ui-bar > i { transition: none; }
</style>
