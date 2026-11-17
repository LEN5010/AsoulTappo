<script setup lang="ts">
// 团子赛跑 (protocol/PROTOCOL.md 团子赛跑): the page takes the bets and lists the past races; a race is watched in a
// window of its own (RaceWatch.vue; stores/ui.ts openRaceWindow). While the page is shown it follows the live race
// (raceFeed.ts). The odds move with the coins staked until the start; a bet sends the odds the player saw and locks
// them, and when they have dropped meanwhile the slip shows the new ones to confirm. The countdown, the rules key and
// the host (the latest champion) go up in the park's coral band (band.ts).
// On top is the bill: the map of the race taking bets, small, and beside it what is on: once the race has started,
// the key that opens its window; else the result of the race before with the key that plays it again; and the switch
// for the pet's word when a race starts (pet/RaceBubble.vue). Under it the five runners as keys, each with its odds to
// win, its die, its skill and my coins on it. The bet slip is the bottom bar: a runner picked, its three kinds, the
// stake and the bet key; nothing picked, 往期 and my tickets. 往期 lists the latest finished races
// (GET /api/park/race/history); one picked plays in the race's window.
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from "vue";
import { manifest } from "../../manifest";
import { economy } from "../../stores/economy";
import { online } from "../../stores/player";
import { loadPark, park, parkTry } from "../../stores/park";
import { settings } from "../../stores/settings";
import { reducedMotion } from "../../stores/theme";
import { openRaceWindow } from "../../stores/ui";
import { ACHAO } from "../../ui/achao";
import Icon from "../../ui/Icon.vue";
import { useBand } from "./band";
import RaceDie from "./RaceDie.vue";
import RaceRules from "./RaceRules.vue";
import RaceTrack from "./RaceTrack.vue";
import ParkCoin from "./ParkCoin.vue";
import TuanziToken from "./TuanziToken.vue";
import { COIN_SMALL } from "./coin";
import { shortDay } from "./lottery";
import {
  FORM_NAMES, hits, KIND_NAMES, SKILL_NAMES, skillText, trackOf, tuanziArt, type Race, type RaceKind, type RacePast,
} from "./race";
import { raceClock, useRaceFeed } from "./raceFeed";

// ParkPage opens the sections only once the server's economy is known.
const CFG = economy.value!.park!.race!;
/** The members in manifest order: the lanes before a race's own are drawn. */
const MEMBERS = manifest.characters.map((c) => c.id);
const KINDS = CFG.kinds;
/** How long a win counts up on the bill, ms. */
const COUNT_MS = 1200;
const fmt = (n: number) => Math.abs(n).toLocaleString("en-US");
const character = (m: string) => manifest.characters.find((c) => c.id === m);
const nameOf = (m: string) => character(m)?.name ?? m;
const x = (n: number | undefined) => (n === undefined ? "" : `×${n.toFixed(1)}`);

const feed = useRaceFeed();
const { data, loadError, serverNow, race, last, phase } = feed;
const poll = feed.poll;
/** The live race has finished, and its result is in. */
const liveFinished = feed.finished;
/** The live race is out: its window is the place to be. */
const live = feed.live;
onMounted(feed.start);
onActivated(feed.start);
onDeactivated(feed.stop);
onBeforeUnmount(feed.stop);

// ---------------------------------------------------------------- the countdown
const countdown = computed<{ label: string; time: string }>(() => {
  const r = race.value;
  const t = serverNow.value / 1000;
  if (r?.phase === "betting") return { label: "开跑", time: raceClock(r.startsAt - t) };
  if (r && live.value) return { label: "比赛中", time: "" };
  return { label: "下一场", time: raceClock((data.value?.nextAt ?? t) - t) };
});
/** Winners come newest first. */
const champion = computed(() => data.value?.winners[0]?.member ?? "");
/** The rules sheet is open. */
const rules = ref(false);
useBand("race", () => ({
  ...(champion.value && tuanziArt(champion.value)
    ? { host: tuanziArt(champion.value), hostKind: "token" as const }
    : { host: ACHAO["观察"] }),
  timer: { label: countdown.value.label, time: countdown.value.time || undefined },
  info: { label: "规则", open: () => (rules.value = true) },
}));

// ---------------------------------------------------------------- the race's map and runners
/** The race's board with nobody on it: the map alone, for the bill. */
const preview = computed<Race | null>(() => (race.value ? { ...race.value, start: undefined, moves: undefined } : null));
/** A member's colour, for its dice. */
const colorOf = (m: string) => character(m)?.color;
/** The faces of the die a member rolls in the race: its form's, or the config's on races dealt before forms. */
const diceOf = (m: string) => race.value?.setup.dice?.[m] ?? CFG.dice;
/** A member's skill in the race taking bets, on races that deal them. */
const skillOf = (m: string) => race.value?.setup.skills?.[m];
/** A runner's key title: its name, and its skill or form on races that deal them. */
function runnerTitle(m: string): string {
  const skill = skillOf(m);
  if (skill) return `${nameOf(m)} · ${SKILL_NAMES[skill.id] ?? skill.id}：${skillText(skill)}`;
  const form = race.value?.setup.forms?.[m];
  return form ? `${nameOf(m)} · 状态${FORM_NAMES[form] ?? form}` : nameOf(m);
}

// ---------------------------------------------------------------- the odds board
const betting = computed(() => phase.value === "betting" && serverNow.value < (race.value?.startsAt ?? 0) * 1000);
const staked = computed(() => race.value?.mine.reduce((n, b) => n + b.coins, 0) ?? 0);
/** What the save may still stake on this race: the cap less its bets, unbounded without a cap. */
const left = computed(() => (CFG.maxCoins ? Math.max(0, CFG.maxCoins - staked.value) : Infinity));
/** The most the stake can be: what is left, and the coins held. */
const most = computed(() => Math.max(1, Math.min(left.value, park.value?.coins ?? left.value)));
const oddsOf = (kind: RaceKind, m: string) => race.value?.odds[kind]?.[m];
const coinsOn = (kind: RaceKind, m: string) => race.value?.pool[kind]?.[m] ?? 0;
/**
 * How much of [kind]'s market [m]'s coins hold, 0 to 1: the stake's weight in the odds (race.py odds_tenths), where
 * the house's depth counts as coins spread evenly, so a first coin on a quiet race shows as the small move it is.
 */
function share(kind: RaceKind, m: string): number {
  const n = MEMBERS.length;
  const all = Object.values(race.value?.pool[kind] ?? {}).reduce((a, c) => a + c, 0);
  return (n * coinsOn(kind, m)) / (n * all + CFG.depth);
}

/** Odds that just moved: up or down, and a count so the cell replays its tick. */
const ticks = ref<Record<string, { dir: "up" | "down"; n: number }>>({});
let seen: { id: number; odds: Race["odds"] } | null = null;
let tickCount = 0;
watch(race, (r) => {
  if (r && seen?.id === r.id && r.phase === "betting") {
    for (const k of KINDS) {
      for (const m of MEMBERS) {
        const was = seen.odds[k]?.[m];
        const is = r.odds[k]?.[m];
        if (was === undefined || is === undefined || was === is) continue;
        const n = ++tickCount;
        ticks.value = { ...ticks.value, [`${k}${m}`]: { dir: is > was ? "up" : "down", n } };
        setTimeout(() => {
          if (ticks.value[`${k}${m}`]?.n !== n) return;
          const { [`${k}${m}`]: _, ...rest } = ticks.value;
          ticks.value = rest;
        }, 1800);
      }
    }
  }
  seen = r ? { id: r.id, odds: r.odds } : null;
});
const tickOf = (kind: RaceKind, m: string) => ticks.value[`${kind}${m}`];

// ---------------------------------------------------------------- bets
const pick = ref<{ kind: RaceKind; member: string } | null>(null);
const stake = ref(1);
const busy = ref(false);
const betError = ref("");
/** The odds of the pick dropped while the bet was on its way: what they were, to confirm at the new ones. */
const repriced = ref<{ kind: RaceKind; member: string; was: number } | null>(null);
const confirming = computed(() =>
  !!repriced.value && repriced.value.kind === pick.value?.kind && repriced.value.member === pick.value?.member,
);

watch(() => race.value?.id, () => {
  pick.value = null;
  betError.value = "";
});
watch(() => [pick.value?.member, pick.value?.kind], () => (repriced.value = null));
watch(most, (n) => (stake.value = Math.max(1, Math.min(stake.value, n))));

/** A runner key: picks that runner (keeping the kind picked last, the win at first), or lets go of it. */
function chooseRunner(member: string) {
  if (!betting.value) return;
  pick.value = pick.value?.member === member ? null : { kind: pick.value?.kind ?? "win", member };
  stake.value = Math.max(1, Math.min(stake.value, most.value));
  betError.value = "";
}
function chooseKind(kind: RaceKind) {
  if (!betting.value || !pick.value) return;
  pick.value = { ...pick.value, kind };
  betError.value = "";
}

async function place() {
  const r = race.value;
  const p = pick.value;
  if (!r || !p || busy.value || !left.value) return;
  const odds = oddsOf(p.kind, p.member);
  busy.value = true;
  betError.value = "";
  const reply = await parkTry<{ race: Race }>("POST", "/api/park/race/bet", {
    race: r.id, kind: p.kind, member: p.member, coins: stake.value, odds,
  });
  busy.value = false;
  if (reply.ok) {
    if (data.value) data.value = { ...data.value, race: reply.data.race };
    pick.value = null;
    void poll();
  } else if (reply.error.code === "odds_changed" && typeof reply.error.detail.odds === "number" && data.value?.race) {
    // The new odds go on the slip; the player presses again to take them.
    const cur = data.value.race;
    const fresh = reply.error.detail.odds;
    data.value = {
      ...data.value,
      race: { ...cur, odds: { ...cur.odds, [p.kind]: { ...cur.odds[p.kind], [p.member]: fresh } } },
    };
    repriced.value = { kind: p.kind, member: p.member, was: odds ?? fresh };
  } else betError.value = reply.error.message;
}

/** My coins on [m] in the race on the track. */
const mineOn = (m: string) => race.value?.mine.filter((b) => b.member === m).reduce((n, b) => n + b.coins, 0) ?? 0;
/**
 * My bets as tickets, one per selection: the odds each bet locked (most first; a range when there are more than
 * two), the coins in all, and whether it won once the race is run.
 */
const tickets = computed(() => {
  const r = race.value;
  const out: { key: string; kind: RaceKind; member: string; odds: number[]; coins: number; won: boolean }[] = [];
  for (const b of r?.mine ?? []) {
    const key = `${b.kind}${b.member}`;
    const t = out.find((o) => o.key === key);
    if (t) {
      t.coins += b.coins;
      if (!t.odds.includes(b.odds)) t.odds.push(b.odds);
    } else out.push({ key, kind: b.kind, member: b.member, odds: [b.odds], coins: b.coins, won: false });
  }
  for (const t of out) {
    t.odds.sort((a, b) => b - a);
    if (liveFinished.value && r?.ranking) t.won = hits(t.kind, t.member, r.ranking);
  }
  return out;
});
const oddsList = (odds: number[]) =>
  odds.length > 2 ? `×${odds[0].toFixed(1)}–${odds[odds.length - 1].toFixed(1)}` : odds.map(x).join(" ");
/** Every bet of a ticket with its own odds, for its tooltip. */
const ticketTitle = (t: { kind: RaceKind; member: string }) =>
  (race.value?.mine ?? []).filter((b) => b.kind === t.kind && b.member === t.member)
    .map((b) => `${nameOf(b.member)} ${KIND_NAMES[b.kind]} ${x(b.odds)} · ${b.coins} 枚`).join("\n");
/** Why the bet key cannot be pressed, for its tooltip. */
const betBlock = computed(() => (!online.value ? "未连接" : ""));

// ---------------------------------------------------------------- results
/** The race whose result is on the bill: the live one once it has played, the one before while bets are open. */
const shown = computed<Race | null>(() => (liveFinished.value ? race.value : phase.value === "betting" ? last.value : null));
const shownRanking = computed(() => shown.value?.ranking ?? []);
/** It can be played again in the race's window. */
const replayable = computed(() => !!shown.value && (shown.value.replay ?? !!shown.value.moves?.length));
// The park's balance and today's result follow a race the save had bets in.
watch(() => (race.value?.phase === "done" && race.value.mine.length ? race.value.id : null), (id) => {
  if (id) void loadPark();
});
/** The coins my bets won on the race shown, counting up from 0 once the result is in. */
const won = computed(() => shown.value?.result?.won ?? 0);
const counted = ref(0);
let countFrame = 0;
watch(() => [shown.value?.id, won.value] as const, ([, to]) => {
  cancelAnimationFrame(countFrame);
  if (!to || reducedMotion.value) {
    counted.value = to;
    return;
  }
  const start = performance.now();
  counted.value = 0;
  const step = (t: number) => {
    const k = Math.min(1, (t - start) / COUNT_MS);
    counted.value = Math.round(to * (1 - (1 - k) ** 3));
    if (k < 1) countFrame = requestAnimationFrame(step);
  };
  countFrame = requestAnimationFrame(step);
}, { immediate: true });
onBeforeUnmount(() => cancelAnimationFrame(countFrame));

// ---------------------------------------------------------------- 往期
/** The 往期 list is open, and the races in it (loaded each time it opens). */
const pastOpen = ref(false);
const past = ref<RacePast[] | null>(null);
const slipEl = ref<HTMLElement | null>(null);

async function togglePast() {
  pastOpen.value = !pastOpen.value;
  if (!pastOpen.value) return;
  const reply = await parkTry<{ races: RacePast[] }>("GET", "/api/park/race/history");
  if (reply.ok) past.value = reply.data.races;
  else if (!past.value) past.value = [];
}
function onOutside(e: PointerEvent) {
  if (!slipEl.value?.contains(e.target as Node)) pastOpen.value = false;
}
watch(pastOpen, (open) => {
  if (open) document.addEventListener("pointerdown", onOutside, true);
  else document.removeEventListener("pointerdown", onOutside, true);
});
onBeforeUnmount(() => document.removeEventListener("pointerdown", onOutside, true));
function onSlipKey(e: KeyboardEvent) {
  if (e.key === "Escape" && pastOpen.value) {
    pastOpen.value = false;
    e.stopPropagation();
  }
}
/** Some day in the list has more than one race: the rows give the time as well. */
const pastTimed = computed(() => new Set((past.value ?? []).map((h) => h.day)).size < (past.value?.length ?? 0));
/** A row's day; with the China time of its start when the list has days of more than one race. */
function pastDay(h: RacePast): string {
  if (!pastTimed.value) return shortDay(h.day);
  const t = new Date((h.startsAt + 8 * 3600) * 1000);
  return `${shortDay(h.day)} ${t.getUTCHours()}:${String(t.getUTCMinutes()).padStart(2, "0")}`;
}
const pastNet = (net: number) => (net > 0 ? `+${fmt(net)}` : net < 0 ? `−${fmt(net)}` : "0");
/** Plays race [id] again in the race's window. */
function openReplay(id: number) {
  pastOpen.value = false;
  openRaceWindow(id);
}
</script>

<template>
  <section class="race" :class="{ calm: reducedMotion }" aria-label="团子赛跑">
    <p v-if="loadError" class="ui-error load-error" role="alert">{{ loadError }}</p>

    <!-- The bill: the race's map, and what is on: the way in once it has started, else the result before. -->
    <div class="bill" :class="{ live }">
      <RaceTrack class="mini" :race="preview" :t="0" :track="trackOf(race?.setup, CFG.track)" :members="MEMBERS" cleared />
      <div class="about">
        <h3 v-if="race?.setup.map">{{ race.setup.map.name }}<small class="sq-count">{{ race.setup.map.track }} 格</small></h3>
        <button
          v-if="live" type="button" class="ui-btn primary watch-key" :class="{ pulse: !reducedMotion }"
          @click="openRaceWindow()"
        >
          <i class="live-dot" aria-hidden="true"></i>观赛
        </button>
        <div v-else-if="shownRanking.length" class="before">
          <small>{{ liveFinished ? "本场" : "上一场" }}</small>
          <ol class="order" aria-label="名次">
            <li v-for="(m, i) in shownRanking" :key="m" class="champ" :title="nameOf(m)">
              <TuanziToken :member="m" :size="i === 0 ? 48 : 32" /><Icon v-if="i === 0" class="champ-crown" name="crown" :size="16" />
            </li>
          </ol>
          <span v-if="won > 0" class="last-net" :aria-label="`+${fmt(won)} 驼币`"><ParkCoin :size="22" :tilt="false" />+{{ fmt(counted) }}</span>
          <button v-if="replayable" type="button" class="ui-btn small again-key" aria-label="回放" @click="openReplay(shown!.id)">
            <Icon name="play" :size="15" />
          </button>
        </div>
        <label class="remind"><input v-model="settings.raceRemind" type="checkbox" class="ui-switch" />开赛提醒</label>
      </div>
    </div>

    <!-- The five runners, each with its odds to win: keys while bets are open. -->
    <div class="field-pane" :class="{ off: race?.phase === 'void' }">
      <p v-if="race?.phase === 'void'" class="void" role="status">本场取消，驼币已退回</p>
      <div class="runners" :class="{ dice: !!race?.setup.dice }" role="group" aria-label="团子">
              <button
                v-for="m in MEMBERS" :key="m" type="button" class="ui-btn runner" :data-runner="m"
                :class="{ on: pick?.member === m }" :aria-pressed="pick?.member === m"
                :disabled="!betting || !online || !left" :title="runnerTitle(m)" @click="chooseRunner(m)"
              >
                <TuanziToken class="face" :member="m" :size="72" :grey="race?.phase === 'void'" />
                <span class="tag">
                  <span class="who-name">
                    <i class="hue" :style="{ background: colorOf(m) }" aria-hidden="true"></i>
                    <span class="name">{{ nameOf(m) }}</span>
                  </span>
                  <span :key="`win${tickOf('win', m)?.n ?? 0}`" class="odds" :class="tickOf('win', m)?.dir">
                    <b>{{ x(oddsOf("win", m)) }}</b>
                    <svg v-if="tickOf('win', m)" class="arrow" viewBox="0 0 12 12" aria-hidden="true">
                      <path v-if="tickOf('win', m)!.dir === 'up'" d="M6 10.5V2M2.2 5.6 6 1.8l3.8 3.8" />
                      <path v-else d="M6 1.5V10M2.2 6.4 6 10.2l3.8-3.8" />
                    </svg>
                  </span>
                </span>
                <span v-if="race?.setup.dice" class="form" :aria-label="`骰子 ${diceOf(m).join(' ')}`">
                  <RaceDie v-for="(f, k) in diceOf(m)" :key="k" :face="f" :color="colorOf(m)" />
                </span>
                <span v-if="skillOf(m)" class="skill">{{ SKILL_NAMES[skillOf(m)!.id] ?? skillOf(m)!.id }}</span>
                <span v-if="mineOn(m)" class="mine"><img :src="COIN_SMALL" alt="" draggable="false" /><b>{{ mineOn(m) }}</b></span>
                <i class="runner-pool" aria-hidden="true"><i :style="{ width: `${share('win', m) * 100}%` }"></i></i>
              </button>
      </div>
    </div>

    <RaceRules v-if="rules" @close="rules = false" />

    <!--
      The bet slip. A runner picked: its three kinds (odds, and a thin bar of the coins on each), the stake and the bet
      key. Nothing picked: 往期 and my tickets on this race.
    -->
    <div ref="slipEl" class="park-actions slip" @keydown="onSlipKey">
      <template v-if="betting && pick && race">
        <span class="picked"><TuanziToken :member="pick.member" :size="32" />{{ nameOf(pick.member) }}</span>
        <span class="kinds" role="group" :aria-label="`${nameOf(pick.member)}的押法`">
          <button
            v-for="k in KINDS" :key="k" type="button" class="ui-btn kind-key"
            :class="{ on: pick.kind === k, repriced: confirming && pick.kind === k }" :aria-pressed="pick.kind === k"
            @click="chooseKind(k)"
          >
            <small>{{ KIND_NAMES[k] }}</small>
            <s v-if="confirming && pick.kind === k">{{ x(repriced!.was) }}</s>
            <span :key="`${k}${tickOf(k, pick.member)?.n ?? 0}`" class="odds" :class="tickOf(k, pick.member)?.dir">
              <b>{{ x(oddsOf(k, pick.member)) }}</b>
              <svg v-if="tickOf(k, pick.member)" class="arrow" viewBox="0 0 12 12" aria-hidden="true">
                <path v-if="tickOf(k, pick.member)!.dir === 'up'" d="M6 10.5V2M2.2 5.6 6 1.8l3.8 3.8" />
                <path v-else d="M6 1.5V10M2.2 6.4 6 10.2l3.8-3.8" />
              </svg>
            </span>
            <i class="pool" :title="`${coinsOn(k, pick.member)} 枚`"><i :style="{ width: `${share(k, pick.member) * 100}%` }"></i></i>
          </button>
        </span>
      </template>
      <template v-else>
      <button
        v-if="data?.winners.length" type="button" class="ui-btn small park-ledger-key" :aria-expanded="pastOpen"
        @click="togglePast"
      ><Icon name="clock" :size="15" /><span>往期</span></button>
      <span v-if="tickets.length" class="tickets" aria-label="我的押注">
        <span
          v-for="t in tickets" :key="t.key" class="ticket" :class="{ won: t.won }"
          :title="ticketTitle(t)"
        >
          <span class="ticket-paper">
            <i class="perf" aria-hidden="true"></i>
            <TuanziToken :member="t.member" :size="24" />
            <small>{{ KIND_NAMES[t.kind] }}</small><b>{{ oddsList(t.odds) }}</b>
            <span class="coin"><img :src="COIN_SMALL" alt="" draggable="false" />{{ t.coins }}</span>
          </span>
        </span>
      </span>
      </template>

      <div v-if="pastOpen" class="pop past ui-scroll">
        <ul v-if="past" class="history" :class="{ timed: pastTimed }">
          <li v-for="h in past" :key="h.id">
            <button type="button" class="past-row" :disabled="!h.replay" @click="openReplay(h.id)">
              <span class="day">{{ pastDay(h) }}</span>
              <span v-if="h.ranking" class="order">
                <span v-for="(m, i) in h.ranking" :key="m" class="champ" :title="nameOf(m)">
                  <TuanziToken :member="m" :size="24" /><Icon v-if="i === 0" class="champ-crown" name="crown" :size="11" />
                </span>
              </span>
              <span v-else class="order none">取消</span>
              <span class="stake">
                <template v-if="h.mine"><img :src="COIN_SMALL" alt="" draggable="false" />{{ h.mine.staked }}</template>
              </span>
              <span class="past-net" :class="{ on: (h.mine?.net ?? 0) > 0 }">
                <template v-if="h.mine">{{ h.phase === "void" ? "退回" : pastNet(h.mine.net) }}</template>
              </span>
              <Icon v-if="h.replay" class="past-play" name="play" :size="13" />
            </button>
          </li>
        </ul>
      </div>

      <div v-if="betting && (pick || !left)" class="park-actions-main">
        <span v-if="!left" class="full">本场已押满</span>
        <template v-else>
          <span class="stepper">
            <button type="button" class="ui-btn small step-key" :disabled="stake <= 1" aria-label="少押一枚" @click="stake--">
              <Icon name="minus" :size="14" />
            </button>
            <b>{{ stake }}</b>
            <button type="button" class="ui-btn small step-key" :disabled="stake >= most" aria-label="多押一枚" @click="stake++">
              <Icon name="plus" :size="14" />
            </button>
          </span>
          <button
            type="button" class="ui-btn primary bet-key" :class="{ pulse: !betBlock && !busy && !reducedMotion }"
            :disabled="busy || !!betBlock" :aria-busy="busy" :title="betBlock || undefined" @click="place"
          >
            <img class="coin" :src="COIN_SMALL" alt="" draggable="false" />
            <template v-if="confirming && pick">确认 {{ x(oddsOf(pick.kind, pick.member)) }}</template>
            <template v-else>押 {{ stake }} 枚</template>
          </button>
        </template>
      </div>
      <p v-if="betError" class="ui-error" role="alert">{{ betError }}</p>
    </div>
  </section>
</template>

<style scoped>
/* On the park's sheet, under the coral band: the bill, the runners filling the height, the slip the bottom bar. */
.race {
  display: flex;
  flex-direction: column;
}
.load-error {
  margin: 14px 22px 0;
}

/*
 * ---- the bill: a tonal --c-100 showcase mat across the top (never paper on paper!), the race's map small on its left
 */
.bill {
  flex: none;
  display: flex;
  align-items: stretch;
  gap: 18px;
  margin: 14px 22px 0;
  padding: 10px 18px 10px 10px;
  border-radius: var(--radius-l);
  background: var(--c-100);
}
.bill.live {
  background: linear-gradient(90deg, var(--c-100) 40%, var(--c-200));
}
.mini {
  flex: none;
  width: 320px;
  height: 178px;
  pointer-events: none;
}
.about {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: center;
  gap: 11px;
}
.about h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font: 800 var(--fs-section)/1.1 var(--font);
  color: var(--ink);
}
.about h3 .sq-count {
  padding: 2px 8px;
  border-radius: var(--radius-s);
  background: var(--surface);
  font: 800 var(--fs-label)/1.25 var(--font);
  color: var(--c-700);
}
/* The way in once the race is out: the page's main key, a dot beating on it. */
.watch-key {
  gap: 8px;
  min-width: 132px;
  height: 44px;
  font-size: var(--fs-section);
}
.live-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  animation: live-beat 1.2s var(--ease-out) infinite;
}
@keyframes live-beat {
  50% { opacity: 0.25; }
}
/* The race before: its order first to last, the winner crowned, what my bets won, and the key that plays it again. */
.before {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 10px;
  min-width: 0;
}
.before small {
  flex: none;
  font: 700 var(--fs-label)/1 var(--font);
  color: var(--ink-2);
}
.order {
  display: flex;
  align-items: flex-end;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.remind {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font: 700 var(--fs-label)/1 var(--font);
  color: var(--ink-2);
  cursor: pointer;
}

/*
 * ---- five runner keys standing in a row, each a tuanzi over its name and its odds to win. The pane is a size
 * container: the keys follow its width and height.
 */
.field-pane {
  container: infield / size;
  flex: 1 1 0;
  min-height: 132px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  margin: 14px 22px 12px;
}
.void {
  margin: 0;
  text-align: center;
  font: 800 var(--fs-strong)/1.3 var(--font);
  color: var(--ink-2);
}
.runners {
  /* The tuanzi on a key: as large as the paper's height and a fifth of its width allow, under it the name and the
   * odds. Spans wide under .bill so the showcase and the five keys read as one architectural block. */
  --face: clamp(26px, min(20cqw - 16px, 100cqh - 70px), 96px);
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: clamp(6px, 1.8cqw, 14px);
  width: min(100%, 880px);
}
/* With the race's die under the odds too. */
.runners.dice {
  --face: clamp(26px, min(20cqw - 16px, 100cqh - 88px), 96px);
}
/* A void race: its line over the runners, which give it the room. */
.field-pane.off .runners {
  --face: clamp(24px, min(20cqw - 16px, 100cqh - 108px), 96px);
}
.runner {
  flex-direction: column;
  gap: 0;
  min-width: 0;
  height: auto;
  padding: clamp(4px, 3cqh, 10px) 6px clamp(8px, 3.5cqh, 13px);
  box-shadow:
    inset 0 0 0 1px var(--c-100),
    0 var(--key-lip-h) 0 var(--key-lip),
    0 calc(var(--key-lip-h) + 1px) calc(var(--key-lip-h) * 2 + 2px) -3px rgba(var(--c-900-rgb), 0.25),
    var(--key-glow);
}
.runner .face {
  --tuanzi-size: var(--face);
  margin-bottom: 2px;
  transition: transform var(--dur-base) var(--ease-out);
}
.runner:hover:not(:disabled) .face {
  transform: translateY(-2px) scale(1.04);
}
/* Under the tuanzi its name (with 4px member bar) and odds to win: one line on a wide sheet, stacked on a narrow one. */
.tag {
  display: flex;
  flex-direction: column;
  align-items: center;
}
.who-name {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.hue {
  flex: none;
  width: 4px;
  height: 12px;
  border-radius: 2px;
}
@container infield (min-width: 440px) {
  .tag {
    flex-direction: row;
    align-items: baseline;
    gap: 5px;
  }
}
.runner .name {
  font: 700 var(--fs-label)/1.25 var(--font);
  color: var(--ink-2);
  white-space: nowrap;
}
.odds {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 2px;
}
.odds b {
  font: 800 var(--fs-section)/1.05 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}
/* Odds that just moved: an arrow beside them a moment, coral and up or grey and down, the number sliding in. */
.odds .arrow {
  width: 11px;
  height: 11px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2.4;
  stroke-linecap: round;
  stroke-linejoin: round;
  animation: tick-arrow 1.6s var(--ease-out) both;
}
.odds.up {
  color: var(--c-700);
}
.odds.up b {
  color: var(--c-700);
  animation: tick-num 500ms var(--ease-pop) both;
}
.odds.down {
  color: var(--ink-3);
}
.odds.down b {
  animation: tick-num-down 500ms var(--ease-pop) both;
}
@keyframes tick-arrow {
  0%, 75% { opacity: 1; }
  100% { opacity: 0; }
}
@keyframes tick-num {
  from { transform: translateY(6px); opacity: 0.2; }
}
@keyframes tick-num-down {
  from { transform: translateY(-6px); opacity: 0.2; }
}
/* The runner picked: latched in coral. */
.runner.on:not(:disabled) {
  --key-top: var(--c-100);
  --key-bottom: var(--c-200);
  --key-lip: var(--c-500);
  box-shadow:
    inset 0 0 0 2px var(--c-500),
    0 var(--key-lip-h) 0 var(--key-lip),
    0 calc(var(--key-lip-h) + 1px) calc(var(--key-lip-h) * 2 + 2px) -3px rgba(var(--c-900-rgb), 0.25);
}
.runner.on .name {
  color: var(--ink);
}
.runner:disabled .face {
  opacity: 0.85;
}
/* Crowd Win market-share bar along the runner key's foot. */
.runner-pool {
  position: absolute;
  left: 10px;
  right: 10px;
  bottom: 4px;
  height: 3px;
  border-radius: 2px;
  background: var(--c-100);
  overflow: hidden;
  pointer-events: none;
}
.runner.on:not(:disabled) .runner-pool {
  background: rgba(var(--c-900-rgb), 0.1);
}
.runner-pool > i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--c-400), var(--c-600));
  transition: width var(--dur-stage) var(--ease-out);
}
/* The faces of the runner's die this race, small, in its colour. */
.form {
  display: flex;
  gap: 2px;
  margin-top: 4px;
}
.form .race-die {
  --s: 13px;
  --die-shadow: none;
}
/* The runner's skill this race: a coral tab stuck on the key's other corner. */
.skill {
  position: absolute;
  top: -8px;
  left: -6px;
  z-index: 2;
  padding: 3px 7px;
  border-radius: 999px;
  background: var(--c-500);
  box-shadow: 0 0 0 2px var(--surface), var(--shadow-key);
  font: 800 var(--fs-caption)/1.1 var(--font);
  color: var(--ink);
  white-space: nowrap;
  rotate: -4deg;
}
/* The coins I have on a runner: a coin stuck on the key's corner. */
.mine {
  position: absolute;
  top: -8px;
  right: -6px;
  z-index: 2;
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px 7px 2px 2px;
  border-radius: 999px;
  background: var(--surface);
  box-shadow: var(--shadow-key);
}
.mine img {
  width: 18px;
  height: 18px;
}
.mine b {
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: var(--ink);
}
@container infield (max-height: 84px) {
  .who-name {
    display: none;
  }
  .runner-pool {
    bottom: 2px;
    height: 2px;
  }
}
@container infield (max-height: 104px) {
  .form {
    display: none;
  }
}
@container infield (max-width: 360px) {
  .odds b {
    font-size: var(--fs-strong);
  }
  .runner .name {
    font-size: var(--fs-caption);
  }
  .mine {
    top: -6px;
    right: -4px;
    padding-right: 5px;
  }
  .mine img {
    width: 14px;
    height: 14px;
  }
  .mine b {
    font-size: var(--fs-strong);
  }
  .form {
    gap: 1px;
  }
  .form .race-die {
    --s: 10px;
  }
}

/* ---- the slip */
.picked {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font: 800 var(--fs-number)/1 var(--font);
  color: var(--ink);
}
.kinds {
  display: flex;
  gap: 8px;
}
.kind-key {
  gap: 5px;
  padding: 0 12px;
  overflow: hidden;
}
/* Latched on the slip's tonal strip: a step darker than the strip, so it still reads as down. */
.kind-key.on:not(:disabled) {
  --key-top: var(--c-300);
  --key-bottom: var(--c-300);
  --key-lip: var(--c-600);
}
.kind-key small {
  font: 700 var(--fs-label)/1 var(--font);
  color: var(--ink-2);
}
.kind-key .odds b {
  font-size: var(--fs-number);
}
/* The odds dropped on the way: the old ones struck out, the new ones flare once. */
.kind-key s {
  font: 700 var(--fs-label)/1 var(--font-latin);
  color: var(--ink-3);
}
.kind-key.repriced .odds b {
  color: var(--c-700);
  animation: tick-num-down 500ms var(--ease-pop) both;
}
/* The coins on the kind: a thin bar along the key's foot, as long as their weight in the odds. */
.pool {
  position: absolute;
  left: 8px;
  right: 8px;
  bottom: 4px;
  height: 3px;
  border-radius: 2px;
  background: rgba(var(--c-900-rgb), 0.08);
  overflow: hidden;
}
.pool > i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--c-600);
  transition: width var(--dur-stage) var(--ease-out);
}
.champ {
  position: relative;
  line-height: 0;
}
.champ-crown {
  position: absolute;
  left: 50%;
  top: -5px;
  translate: -50% 0;
  color: var(--gold);
  filter: drop-shadow(0 1px 0 #fff) drop-shadow(0 -1px 0 #fff) drop-shadow(1px 0 0 #fff) drop-shadow(-1px 0 0 #fff);
}
.champ-crown :deep(path) {
  fill: var(--gold-soft);
}
/* My bets: notched paper stubs, the winners coral once the race is run. */
.tickets {
  display: flex;
  gap: 6px;
  -webkit-mask-image: linear-gradient(90deg, #000 calc(100% - 18px), transparent);
  mask-image: linear-gradient(90deg, #000 calc(100% - 18px), transparent);
  min-width: 0;
  max-width: 100%;
  overflow-x: auto;
  scrollbar-width: none;
  padding: 2px 2px 4px;
}
.ticket {
  flex: none;
  display: inline-flex;
  filter: drop-shadow(0 1px 1px rgba(var(--c-900-rgb), 0.14)) drop-shadow(0 2px 4px rgba(var(--c-900-rgb), 0.12));
}
.ticket-paper {
  --x: 8px;
  --bite: 3.2px;
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 30px;
  padding: 0 9px 0 13px;
  box-sizing: border-box;
  border-radius: var(--radius-s);
  background: var(--surface);
  -webkit-mask:
    radial-gradient(circle at var(--x) 0, transparent var(--bite), #000 calc(var(--bite) + 0.5px)),
    radial-gradient(circle at var(--x) 100%, transparent var(--bite), #000 calc(var(--bite) + 0.5px));
  -webkit-mask-composite: source-in;
  mask:
    radial-gradient(circle at var(--x) 0, transparent var(--bite), #000 calc(var(--bite) + 0.5px)),
    radial-gradient(circle at var(--x) 100%, transparent var(--bite), #000 calc(var(--bite) + 0.5px));
  mask-composite: intersect;
}
.ticket .perf {
  position: absolute;
  top: 5px;
  bottom: 5px;
  left: var(--x);
  width: 3px;
  margin-left: -1.5px;
  background: radial-gradient(circle, var(--c-400) 1.1px, transparent 1.5px) 50% 0 / 3px 5px repeat-y;
}
.ticket small {
  font: 700 var(--fs-label)/1 var(--font);
  color: var(--ink-2);
}
.ticket b {
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: var(--ink);
}
.ticket .coin {
  display: inline-flex;
  align-items: center;
  gap: 1px;
  margin-left: 2px;
  font: 800 var(--fs-strong)/1 var(--font-latin);
  color: var(--ink-2);
}
.ticket .coin img {
  width: 14px;
  height: 14px;
}
.ticket.won .ticket-paper {
  background: var(--c-500);
}
.ticket.won .perf {
  background: radial-gradient(circle, #fff 1.1px, transparent 1.5px) 50% 0 / 3px 5px repeat-y;
}
.ticket.won small,
.ticket.won .coin {
  color: var(--ink);
}
.last-net {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font: 800 var(--fs-number)/1 var(--font-latin);
  color: var(--c-700);
}
.stepper {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.step-key {
  width: 28px;
  padding: 0;
  --key-lip-h: 2px;
}
.stepper b {
  min-width: 22px;
  text-align: center;
  font: 800 22px/1 var(--font-latin);
  color: var(--ink);
}
.full {
  font: 700 var(--fs-body)/1 var(--font);
  color: var(--ink-2);
}
.bet-key {
  min-width: 112px;
}
.bet-key .coin {
  width: 18px;
  height: 18px;
}
/* A refused bet floats over the board's lower edge above the bet key, so the bar keeps its height and the board its
   size. */
.slip .ui-error {
  position: absolute;
  right: 22px;
  bottom: calc(100% + 8px);
  max-width: calc(100% - 44px);
  margin: 0;
  box-shadow: var(--shadow-paper);
}
/* The tickets scroll sideways rather than push the bet key onto a second line. */
.slip > .tickets {
  flex: 1 1 0;
  min-width: 0;
}
/* The key that plays the finished race on the bill again: a crisp mini key after its result. */
.again-key {
  width: 30px;
  padding: 0;
  --key-lip-h: 2px;
}
.again-key svg,
.past-play {
  color: var(--c-700);
}

/* ---- 往期: the latest races rise from the slip, one a row; a row with a replay is a key */
.pop {
  position: absolute;
  z-index: 3;
  margin: 0;
  padding: 10px 8px;
  box-sizing: border-box;
  overflow-y: auto;
  border-radius: var(--radius-m);
  background: var(--surface);
  box-shadow: var(--shadow-paper), 0 10px 28px -12px rgba(var(--c-900-rgb), 0.3);
}
.past {
  left: 16px;
  bottom: calc(100% + 8px);
  width: 440px;
  max-width: calc(100% - 32px);
  max-height: 260px;
}
.history {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.past-row {
  display: grid;
  grid-template-columns: 4.6em minmax(0, 1fr) 48px 44px 14px;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: 36px;
  padding: 4px 8px;
  border: 0;
  border-radius: var(--radius-s);
  background: none;
  font: 700 var(--fs-label)/1 var(--font);
  color: var(--ink-3);
  text-align: left;
  cursor: pointer;
}
.timed .past-row {
  grid-template-columns: 8.4em minmax(0, 1fr) 48px 44px 14px;
}
.past-row:not(:disabled):hover,
.past-row:focus-visible {
  background: var(--c-100);
}
.past-row:disabled {
  cursor: default;
}
.past-row .order {
  display: flex;
  gap: 4px;
}
.past-row .order.none {
  color: var(--ink-3);
}
.past-row .champ-crown {
  top: -4px;
}
.past-row .stake {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
  font: 800 var(--fs-strong)/1 var(--font-latin);
  color: var(--ink-2);
}
.past-row .stake img {
  width: 13px;
  height: 13px;
}
.past-net {
  text-align: right;
  font: 800 var(--fs-strong)/1 var(--font-latin);
  color: var(--ink-3);
}
.past-net.on {
  color: var(--c-700);
}

.calm .pool > i,
.calm .runner-pool > i,
.calm .runner .face {
  transition: none;
}
.calm .runner:hover:not(:disabled) .face {
  transform: none;
}
.calm .odds .arrow,
.calm .odds b,
.calm .kind-key.repriced .odds b,
.calm .live-dot {
  animation: none;
}

/* A low panel: the map gives the runners its height. */
@container panel (max-height: 560px) {
  .mini {
    width: 250px;
    height: 132px;
  }
}
/* Narrow panels: shrink the map preview, stack the kind keys, and keep the slip on one line. */
@container panel (max-width: 840px) {
  .mini {
    width: 224px;
    height: 126px;
  }
  .kind-key {
    flex-direction: column;
    gap: 1px;
    min-width: 50px;
    padding: 0 8px 3px;
  }
  .kind-key small {
    font-size: var(--fs-caption);
  }
  .kind-key .odds b {
    font-size: var(--fs-strong);
  }
  .kind-key s {
    display: none;
  }
  .pool {
    bottom: 3px;
    height: 2px;
  }
}
@container panel (max-width: 680px) {
  .bill {
    flex-direction: column;
    align-items: center;
    gap: 10px;
    padding: 10px 14px 12px;
  }
  .mini {
    width: min(100%, 260px);
    height: 124px;
  }
  .about {
    width: 100%;
    align-items: center;
    gap: 8px;
  }
  .before {
    justify-content: center;
  }
  .picked {
    display: none;
  }
  .kinds {
    gap: 6px;
  }
  .stepper {
    gap: 2px;
  }
  .bet-key {
    min-width: 0;
    padding: 0 14px;
  }
  .ticket small {
    display: none;
  }
}
</style>
