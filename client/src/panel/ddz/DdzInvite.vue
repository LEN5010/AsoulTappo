<script setup lang="ts">
// Starting a dou dizhu game: the three seats on a strip of the mat, the base stake as three keys in a tray, and the
// key that goes. [mode] picks how: "invite" picks two members of the room (the members as keys, those who cannot be
// asked greyed); "match" waits in the server's queue (each stake shows how many others wait at it); "open" opens a
// table in the room, the two other seats left empty. "call" asks one member to the open table this save opened, at
// its stake: no tray, the members as keys.
import { computed, ref, watch } from "vue";
import { status } from "../../stores/player";
import { duelDnd, members, shownNick, youId } from "../../stores/room";
import { settings } from "../../stores/settings";
import {
  callDdz, ddz, ddzCanCall, ddzCanInvite, ddzCanOpen, ddzCanQueue, ddzCanStart, ddzConfig, ddzDeposit, ddzOthersWaiting,
  ddzRetry, ddzStakeOpen, inviteDdz, openDdz, queueDdz,
} from "../../stores/ddz";
import CharacterAvatar from "../../ui/CharacterAvatar.vue";
import Icon from "../../ui/Icon.vue";
import Modal from "../../ui/Modal.vue";
import DdzSeats from "./DdzSeats.vue";

/** Bets need an account here and none is signed in. */
const props = defineProps<{ needAccount?: boolean; mode: "invite" | "match" | "open" | "call" }>();
const emit = defineEmits<{ close: [] }>();

const stakes = computed(() => ddzConfig.value?.stakes ?? []);
/** In the queue, the open stake most others wait at comes first. */
const first = () => (props.mode === "match"
  ? [...stakes.value].filter(ddzStakeOpen).sort((a, b) => ddzOthersWaiting(b) - ddzOthersWaiting(a))[0]
  : stakes.value.find(ddzStakeOpen));
const base = ref(first() ?? 0);
watch(stakes, (list) => { if (!list.includes(base.value) || !ddzStakeOpen(base.value)) base.value = list.find(ddzStakeOpen) ?? 0; });

/** The open table being called to ("call"). */
const table = computed(() => (props.mode === "call" && ddz.value?.phase === "open" ? ddz.value : null));
const others = computed(() => [...members.values()].filter((m) => m.id !== youId.value));
/** Two members to invite ("invite"), or one to call ("call"). */
const picked = ref<string[]>([]);
const want = computed(() => (props.mode === "call" ? 1 : 2));
const pickable = (id: string) => {
  const m = members.get(id);
  return !!m && (props.mode === "call" ? ddzCanCall(m) : ddzCanInvite(m));
};
// A member picked who left, or sat down at another table, is dropped.
watch(() => picked.value.filter(pickable), (still) => { if (still.length !== picked.value.length) picked.value = still; });
function toggle(id: string) {
  if (want.value === 1) picked.value = picked.value.includes(id) ? [] : [id];
  else picked.value = picked.value.includes(id) ? picked.value.filter((x) => x !== id) : picked.value.length < 2 ? [...picked.value, id] : picked.value;
}
const seats = computed(() => {
  const me = { character: settings.character, nick: settings.nick.trim() || "我" };
  const face = (id: string | undefined) => {
    if (id === youId.value) return me;
    const m = id ? members.get(id) : undefined;
    return m ? { character: m.character, nick: shownNick(m) } : null;
  };
  if (table.value) {
    // The table's seats, the one picked shown in the first empty seat.
    let call: string | undefined = picked.value[0];
    return table.value.seats.map((s, i) => {
      if (i === table.value!.you) return me;
      if (s.pending) return "pending" as const;
      if (s.id) return { character: s.character, nick: shownNick(s) };
      const shown = face(call);
      call = undefined;
      return shown;
    });
  }
  if (props.mode !== "invite") return [null, me, null];
  return [face(picked.value[0]), me, face(picked.value[1])];
});

/** What stands in the way of a game, in words; "" when nothing does. */
const blocked = computed(() => {
  const cfg = ddzConfig.value;
  const s = status.value;
  if (!cfg || !s?.ddz) return "";
  if (props.mode === "call") return "";
  if (props.needAccount) return "登录 Asasfans 账号后才能斗地主";
  if (s.totals.taps < cfg.minTaps) {
    const need = cfg.minTaps % 10000 === 0 ? `${cfg.minTaps / 10000} 万` : cfg.minTaps.toLocaleString("en-US");
    return `累计敲击满 ${need} 下后可以斗地主`;
  }
  if (s.ddz.net >= cfg.dailyWinCap) return "今天赢到上限了，明天再来";
  if (!cfg.stakes.some(ddzStakeOpen)) return "碎片不够押金";
  if (props.mode === "match") return duelDnd() ? "免打扰时不能匹配" : ddzRetry.value ? "稍后再匹配" : "";
  if (props.mode === "open") return duelDnd() ? "免打扰时不能开桌" : "";
  if (others.value.filter(ddzCanInvite).length < 2) return "房间里要有两位能上桌的伙伴";
  return "";
});
const ready = computed(() => {
  switch (props.mode) {
    case "call": return !!table.value && picked.value.length === 1;
    case "match": return ddzStakeOpen(base.value) && ddzCanQueue.value;
    case "open": return ddzStakeOpen(base.value) && ddzCanOpen.value;
    default: return ddzStakeOpen(base.value) && ddzCanStart.value && picked.value.length === 2;
  }
});
const go = { invite: "邀请", match: "匹配", open: "开桌", call: "邀请" };
function send() {
  if (!ready.value) return;
  if (props.mode === "call") callDdz(picked.value[0]!, table.value!.id);
  else if (props.mode === "match") queueDdz(base.value);
  else if (props.mode === "open") openDdz(base.value);
  else inviteDdz([...picked.value], base.value);
  emit("close");
}
</script>

<template>
  <Modal title="斗地主" flush @close="emit('close')">
    <div class="strip">
      <h3>斗地主</h3>
      <DdzSeats :seats="seats" />
    </div>
    <div class="body">
      <div v-if="table">
        <p class="label">底分</p>
        <p class="fixed"><Icon name="shard" :size="14" />{{ table.base.toLocaleString("en-US") }}</p>
      </div>
      <div v-else>
        <p class="label">底分</p>
        <div class="stakes">
          <button
            v-for="s in stakes" :key="s" type="button" class="ui-btn stake" :class="{ primary: base === s }"
            :aria-pressed="base === s" :disabled="!ddzStakeOpen(s)"
            :title="ddzStakeOpen(s) ? undefined : `碎片不够押金 ${ddzDeposit(s).toLocaleString('en-US')}`" @click="base = s"
          >
            <Icon name="shard" :size="14" />{{ s.toLocaleString("en-US") }}
            <em v-if="mode === 'match' && ddzOthersWaiting(s)" class="waiting"><Icon name="users" :size="11" />{{ ddzOthersWaiting(s) }}</em>
          </button>
        </div>
      </div>
      <div v-if="mode === 'invite' || mode === 'call'">
        <p class="label">邀请</p>
        <div v-if="others.length" class="members">
          <button
            v-for="m in others" :key="m.id" type="button" class="ui-btn member" :class="{ on: picked.includes(m.id) }"
            :aria-pressed="picked.includes(m.id)" :disabled="!pickable(m.id) || (picked.length === want && !picked.includes(m.id))"
            @click="toggle(m.id)"
          >
            <CharacterAvatar class="face" :character="m.character" :size="32" />
            <span>{{ shownNick(m) }}</span>
            <i v-if="picked.includes(m.id)" class="tick"><Icon name="check" :size="12" /></i>
          </button>
        </div>
        <p v-else class="ui-empty">房间里还没有别人</p>
      </div>
      <p v-if="blocked" class="blocked">{{ blocked }}</p>
      <button v-else type="button" class="ui-btn primary go" :disabled="!ready" @click="send">{{ go[mode] }}</button>
    </div>
  </Modal>
</template>

<style scoped>
/* A strip of the table's mat across the top of the sheet, the three seats on it. */
.strip {
  position: relative;
  height: 150px;
  padding-bottom: 16px;
  box-sizing: border-box;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  background: var(--grad-sky);
}
.strip::before {
  content: "";
  position: absolute;
  inset: 8px;
  border-radius: 13px;
  box-shadow: inset 0 0 0 1.5px rgba(255, 255, 255, 0.5);
  pointer-events: none;
}
.strip::after {
  content: "";
  position: absolute;
  inset: 0;
  background: #fff;
  opacity: 0.3;
  pointer-events: none;
  mask: radial-gradient(circle, #000 1.1px, transparent 1.5px) 0 0 / 14px 14px, radial-gradient(120% 120% at 100% 0, #000 10%, transparent 55%);
  mask-composite: intersect;
  -webkit-mask-composite: source-in;
}
.strip h3 { position: absolute; left: 22px; top: 18px; margin: 0; font: 800 18px/1.2 var(--font); color: #fff; z-index: 1; }
.strip .seats { position: relative; z-index: 1; }

.body { padding: 18px 24px 22px; display: flex; flex-direction: column; gap: 16px; }
.label { margin: 0 0 8px; font: 800 12px/1 var(--font); color: var(--ink-2); }

/* The base stakes: three keys in one tray, all alike; the one chosen is the coral key, pressed down. A stake whose
   deposit the save cannot pay is greyed, the deposit in its tooltip. */
.stakes {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
  padding: 6px 6px 8px;
  border-radius: calc(var(--radius-key) + 6px);
  background: var(--c-100);
}
.stake { height: 44px; min-width: 0; padding: 0; gap: 3px; font: 800 18px/1 var(--font-latin); }
.stake .icon { color: var(--c-600); }
.stake.primary:not(:disabled) { color: #fff; text-shadow: 0 1px 0 var(--c-600); }
.stake.primary:not(:disabled) .icon { color: #fff; }
.stake:disabled, .stake:disabled .icon { color: var(--ink-3); }
/* Others waiting at a stake: a small count in the key's corner. */
.stake { position: relative; }
.stake .waiting {
  position: absolute;
  top: 4px;
  right: 6px;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font: 800 11px/1 var(--font-latin);
  font-style: normal;
  color: var(--c-600);
}
.stake .waiting .icon { color: inherit; }
.stake.primary:not(:disabled) .waiting { color: #fff; }
.stake:disabled .waiting { color: var(--ink-3); }

/* The room's members: a key each, with a face. A picked one stays down with a tick. */
.members { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; max-height: 164px; overflow: auto; padding: 2px 2px 5px; margin: -2px -2px -5px; }
.member { height: 44px; min-width: 0; padding: 0 12px 0 6px; justify-content: flex-start; gap: 8px; font-size: 13px; }
.member .face { border-radius: 50%; box-shadow: 0 0 0 2px #fff; }
.member span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.member .tick { margin-left: auto; flex: none; width: 18px; height: 18px; border-radius: 50%; background: var(--c-500); display: grid; place-items: center; color: #fff; }
.member:disabled .face { filter: grayscale(1); opacity: 0.7; }

/* The stake of the table called to: as a stake key, but fixed. */
.fixed { margin: 0; height: 44px; display: flex; align-items: center; justify-content: center; gap: 3px; border-radius: var(--radius-key); background: var(--c-100); font: 800 18px/1 var(--font-latin); color: var(--ink); }
.fixed .icon { color: var(--c-600); }

.go { height: 42px; font-size: 15px; }
.blocked { margin: 0; height: 42px; display: grid; place-items: center; border-radius: var(--radius-key); background: var(--c-50); font: 800 var(--fs-body)/1.3 var(--font); color: var(--ink-2); text-align: center; }
</style>
