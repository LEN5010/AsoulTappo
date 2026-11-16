<script setup lang="ts">
// Starting a dou dizhu game: the three seats on a strip of the mat (the own one and the two members picked), the
// base stake as three keys with the deposit under each, the room's members as keys to pick two of, and the key that
// sends the invite. Members who cannot be asked are greyed.
import { computed, ref, watch } from "vue";
import { status } from "../../stores/player";
import { members, shownNick, youId } from "../../stores/room";
import { settings } from "../../stores/settings";
import { ddzCanInvite, ddzCanStart, ddzConfig, ddzDeposit, ddzStakeOpen, inviteDdz } from "../../stores/ddz";
import CharacterAvatar from "../../ui/CharacterAvatar.vue";
import Icon from "../../ui/Icon.vue";
import Modal from "../../ui/Modal.vue";
import DdzSeats from "./DdzSeats.vue";

const emit = defineEmits<{ close: [] }>();
const TIERS = ["low", "mid", "high"];

const stakes = computed(() => ddzConfig.value?.stakes ?? []);
const base = ref(stakes.value.find(ddzStakeOpen) ?? 0);
watch(stakes, (list) => { if (!list.includes(base.value) || !ddzStakeOpen(base.value)) base.value = list.find(ddzStakeOpen) ?? 0; });

const others = computed(() => [...members.values()].filter((m) => m.id !== youId.value));
const picked = ref<string[]>([]);
// A member picked who left, or sat down at another table, is dropped.
watch(() => picked.value.filter((id) => { const m = members.get(id); return m && ddzCanInvite(m); }),
  (still) => { if (still.length !== picked.value.length) picked.value = still; });
function toggle(id: string) {
  picked.value = picked.value.includes(id) ? picked.value.filter((x) => x !== id) : picked.value.length < 2 ? [...picked.value, id] : picked.value;
}
const seats = computed(() => [
  picked.value[0], youId.value, picked.value[1],
].map((id) => {
  if (id === youId.value) return { character: settings.character, nick: settings.nick.trim() || "我" };
  const m = id ? members.get(id) : undefined;
  return m ? { character: m.character, nick: shownNick(m) } : null;
}));

/** What stands in the way of a game, in words; "" when nothing does. */
const blocked = computed(() => {
  const cfg = ddzConfig.value;
  const s = status.value;
  if (!cfg || !s?.ddz) return "";
  if (s.totals.taps < cfg.minTaps) {
    const need = cfg.minTaps % 10000 === 0 ? `${cfg.minTaps / 10000} 万` : cfg.minTaps.toLocaleString("en-US");
    return `累计敲击满 ${need} 下后可以斗地主`;
  }
  if (s.ddz.net >= cfg.dailyWinCap) return "今天赢到上限了，明天再来";
  if (!cfg.stakes.some(ddzStakeOpen)) return "碎片不够押金";
  if (others.value.filter(ddzCanInvite).length < 2) return "房间里要有两位能上桌的伙伴";
  return "";
});
const ready = computed(() => ddzCanStart.value && picked.value.length === 2 && ddzStakeOpen(base.value));
function send() {
  if (!ready.value) return;
  inviteDdz([...picked.value], base.value);
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
      <div>
        <p class="label">底分</p>
        <div class="stakes">
          <div v-for="(s, i) in stakes" :key="s" class="stake">
            <button
              type="button" class="ui-btn key" :class="[TIERS[Math.min(i, TIERS.length - 1)], { on: base === s }]"
              :aria-pressed="base === s" :disabled="!ddzStakeOpen(s)" @click="base = s"
            >
              <Icon name="shard" :size="13" />{{ s.toLocaleString("en-US") }}
            </button>
            <small>押 {{ ddzDeposit(s).toLocaleString("en-US") }}</small>
          </div>
        </div>
      </div>
      <div>
        <p class="label">邀请</p>
        <div v-if="others.length" class="members">
          <button
            v-for="m in others" :key="m.id" type="button" class="ui-btn member" :class="{ on: picked.includes(m.id) }"
            :aria-pressed="picked.includes(m.id)" :disabled="!ddzCanInvite(m) || (picked.length === 2 && !picked.includes(m.id))"
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
      <button v-else type="button" class="ui-btn primary go" :disabled="!ready" @click="send">邀请</button>
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

/* The base stakes: the duel's three keys, one step deeper per stake; the one chosen stays down. */
.stakes { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.stake { min-width: 0; display: flex; flex-direction: column; align-items: center; gap: 7px; }
.stake .ui-btn.key { width: 100%; min-width: 0; height: 40px; padding: 0; gap: 2px; font: 800 15px/1 var(--font-latin); color: var(--ink); }
.key .icon { color: var(--c-600); }
.stake .ui-btn.mid:not(:disabled) { --key-top: var(--c-100); --key-bottom: var(--c-200); --key-lip: var(--c-300); }
.stake .ui-btn.high:not(:disabled) { --key-top: var(--c-400); --key-bottom: var(--c-500); --key-lip: var(--c-600); }
.stake .ui-btn.on:not(:disabled) { --key-y: 2px; --key-lip-h: 1px; box-shadow: 0 0 0 2px var(--c-600); }
.stake small { font: 700 var(--fs-caption)/1 var(--font); color: var(--ink-2); white-space: nowrap; }
.key:disabled { color: var(--ink-3); }
.key:disabled .icon, .key:disabled + small { color: var(--ink-3); }

/* The room's members: a key each, with a face. A picked one stays down with a tick. */
.members { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; max-height: 164px; overflow: auto; padding: 2px 2px 5px; margin: -2px -2px -5px; }
.member { height: 44px; min-width: 0; padding: 0 12px 0 6px; justify-content: flex-start; gap: 8px; font-size: 13px; }
.member .face { border-radius: 50%; box-shadow: 0 0 0 2px #fff; }
.member span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.member .tick { margin-left: auto; flex: none; width: 18px; height: 18px; border-radius: 50%; background: var(--c-500); display: grid; place-items: center; color: #fff; }
.member:disabled .face { filter: grayscale(1); opacity: 0.7; }

.go { height: 42px; font-size: 15px; }
.blocked { margin: 0; height: 42px; display: grid; place-items: center; border-radius: var(--radius-key); background: var(--c-50); font: 800 var(--fs-body)/1.3 var(--font); color: var(--ink-2); text-align: center; }
</style>
