<script setup lang="ts">
// Watching a race (protocol/PROTOCOL.md 团子赛跑): the page of the race's own window (RaceApp.vue; the browser preview
// floats it over the desk page, pet/RaceFrame.vue). The race page only takes bets and lists the past races; this is
// where a race is seen. It follows the live race (raceFeed.ts) or, with [replay], plays that finished race again on a
// clock of its own (race.ts replayTime), at 1× or 2×.
// The bar on top moves the window and says what is on: the map, live or a replay, the round. Under it the board
// (RaceTrack) fills the stage; beside it the field in the order it stands, each with its skill, its die's faces, how
// far along it is and my coins on it, and under those my bets. The strip under the board is the order of play, each
// tuanzi under its die: the opening's dice, then each round's five thrown together, the one whose turn it is raised.
// Between races the board shows the next race's map with the time to its start; at the finish the tuanzi fly from
// their squares onto a podium over the board.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { manifest } from "../../manifest";
import { economy } from "../../stores/economy";
import { parkTry } from "../../stores/park";
import { reducedMotion } from "../../stores/theme";
import Icon from "../../ui/Icon.vue";
import { EASE_OUT } from "../../ui/motion";
import ParkCoin from "./ParkCoin.vue";
import RaceDie, { type Toss } from "./RaceDie.vue";
import RaceTrack from "./RaceTrack.vue";
import TuanziToken from "./TuanziToken.vue";
import { COIN_SMALL } from "./coin";
import { shortDay } from "./lottery";
import {
  chinaDay, DICE_TOSS, FORM_NAMES, hits, KIND_NAMES, OPEN_ROLL_MS, openingAt, playhead, playLength, rankOf, replayAt,
  replayTime, ROUND, roundAt, roundDice, roundsOf, SKILL_NAMES, skillText, spots, stacksAt, staggered, stageOf, trackOf,
  type Race, type ReplayClock,
} from "./race";
import { isFinished, isPlaying, raceClock, useRaceFeed } from "./raceFeed";

/** [replay]: the finished race to play, 0 for the live one. */
const props = defineProps<{ replay?: number }>();
const emit = defineEmits<{ close: []; drag: [e: PointerEvent] }>();

const CFG = computed(() => economy.value?.park?.race);
/** The members in manifest order: the lanes before a race's own are drawn. */
const MEMBERS = manifest.characters.map((c) => c.id);
/** How long the last round's cue stays up, ms. */
const CUE_MS = 2600;
/** The faces of the order's die. */
const ORDER_FACES = [1, 2, 3, 4, 5, 6];
const fmt = (n: number) => Math.abs(n).toLocaleString("en-US");
const character = (m: string) => manifest.characters.find((c) => c.id === m);
const nameOf = (m: string) => character(m)?.name ?? m;
const colorOf = (m: string) => character(m)?.color;
const x = (n: number) => `×${n.toFixed(1)}`;

const feed = useRaceFeed();
const { now, serverNow, race, loadError } = feed;
onMounted(feed.start);
onBeforeUnmount(feed.stop);

// ---------------------------------------------------------------- the race on the board
/** A finished race played again: the race, its day, its clock, and a count of jumps that starts the board afresh. */
const played = ref<{ race: Race; day: string; clock: ReplayClock; n: number } | null>(null);
const replayError = ref("");
/** Asks for race [id] and plays it from its start; 0 goes back to the live race. */
async function load(id: number) {
  replayError.value = "";
  if (!id) {
    played.value = null;
    return;
  }
  const have = [race.value, feed.last.value].find((r) => r?.id === id && r.phase === "done" && r.moves?.length);
  let r = have ?? null;
  if (!r) {
    const reply = await parkTry<{ race: Race }>("GET", `/api/park/race/replay/${id}`);
    if (!reply.ok) {
      replayError.value = reply.error.message;
      return;
    }
    r = reply.data.race;
  }
  played.value = { race: r, day: chinaDay(r.startsAt), clock: replayAt(r, 0, Date.now(), 1), n: (played.value?.n ?? 0) + 1 };
}
watch(() => props.replay ?? 0, load, { immediate: true });

/** The race on the board and its time: the replay's while one plays, else the live race at the server's time. */
const stage = computed(() => played.value?.race ?? race.value);
const stageNow = computed(() => {
  const p = played.value;
  return p ? replayTime(p.race, p.clock, now.value) : serverNow.value;
});
const speed = computed(() => played.value?.clock.speed ?? 1);
const playing = computed(() => isPlaying(stage.value, stageNow.value));
const finished = computed(() => isFinished(stage.value, stageNow.value));
const track = computed(() => trackOf(stage.value?.setup, CFG.value?.track ?? 24));
/** The board starts afresh on every replay jump, and back on the live race. */
const trackKey = computed(() => (played.value ? `r${played.value.race.id}-${played.value.n}` : `live${race.value?.id ?? 0}`));

/** Moves the replay to [from] ms into the race (0: from the start, the end: its result). */
function seek(from: number) {
  const p = played.value;
  if (p) played.value = { ...p, clock: replayAt(p.race, from, Date.now(), p.clock.speed), n: p.n + 1 };
}
/** Plays the replay at [k]×, on from where it is. */
function setSpeed(k: number) {
  const p = played.value;
  if (!p) return;
  const at = replayTime(p.race, p.clock, Date.now()) - p.race.startsAt * 1000;
  played.value = { ...p, clock: replayAt(p.race, at, Date.now(), k) };
}
const toEnd = () => played.value && seek(playLength(played.value.race));
const progress = computed(() => {
  const p = played.value;
  return p ? Math.min(1, (stageNow.value - p.race.startsAt * 1000) / Math.max(1, playLength(p.race))) : 0;
});
/** The live race is under way while a replay plays: a key goes to it. */
const liveOn = computed(() => !!played.value && feed.live.value);

/** What is over the board: nothing while a race runs, the wait for the next one, or the podium. */
const view = computed<"run" | "wait" | "podium">(() => {
  if (finished.value) return "podium";
  if (played.value || playing.value || stage.value?.phase === "starting") return "run";
  return "wait";
});
const wait = computed(() => {
  const r = race.value;
  const t = serverNow.value / 1000;
  if (r?.phase === "void") return { label: "本场取消", time: "" };
  if (r?.phase === "betting") return { label: "下注中", time: raceClock(r.startsAt - t) };
  const next = feed.data.value?.nextAt;
  return next ? { label: "下一场", time: raceClock(next - t) } : null;
});

// ---------------------------------------------------------------- the field as it stands
const head = computed(() => {
  const r = stage.value;
  return r?.start && r.moves?.length ? playhead(r, stageNow.value) : null;
});
const stacks = computed(() => {
  const r = stage.value;
  return r?.start && r.moves && head.value ? stacksAt(r.start, r.moves, head.value) : null;
});
/*
 * The lists below move their rows when the order changes (TransitionGroup). A list that draws again while its rows
 * are on the way starts their move afresh from where they are, so what the lists read must stand still between the
 * clock's ticks: the values that follow the clock are turned into text first, which only changes when they do.
 */
/** First to last (the ranking once it is in, the board's order while it runs, the lanes before), and each one's square. */
const standing = computed(() => {
  const r = stage.value;
  const order = finished.value && r?.ranking ? r.ranking : stacks.value ? rankOf(stacks.value) : r?.start ?? MEMBERS;
  const squares: Record<string, number> = {};
  if (stacks.value) for (const [m, s] of Object.entries(spots(stacks.value))) squares[m] = s.square;
  return JSON.stringify({ order, squares, led: !!stacks.value });
});
const field = computed(() => JSON.parse(standing.value) as { order: string[]; squares: Record<string, number>; led: boolean });
const order = computed(() => field.value.order);
const squares = computed(() => field.value.squares);
/** How far along [m] is, 0 to 1. */
const along = (m: string) => (finished.value && order.value[0] === m ? 1 : Math.min(1, (squares.value[m] ?? 0) / track.value));
const skillOf = (m: string) => stage.value?.setup.skills?.[m];
/** A member's skill, or its form on races from before skills: the name and what it does. */
function traitOf(m: string): { name: string; text: string } | null {
  const skill = skillOf(m);
  if (skill) return { name: SKILL_NAMES[skill.id] ?? skill.id, text: skillText(skill) };
  const form = stage.value?.setup.forms?.[m];
  return form ? { name: FORM_NAMES[form] ?? form, text: "" } : null;
}
const diceOf = (m: string) => stage.value?.setup.dice?.[m] ?? CFG.value?.dice ?? [];
const mineOn = (m: string) => stage.value?.mine.filter((b) => b.member === m).reduce((n, b) => n + b.coins, 0) ?? 0;

// ---------------------------------------------------------------- the order of play and its dice
/** The opening (the dice for the order) while it plays. */
const opening = computed(() => (stage.value && playing.value ? openingAt(stage.value, stageNow.value) : null));
/** The order of play: the manifest's until the opening has settled it; none for a race from before the opening. */
const seats = computed<string[]>(() => {
  const r = stage.value;
  if (r?.order && (!opening.value || opening.value.lined)) return r.order;
  return r?.order || !r?.moves ? MEMBERS : [];
});
/** A throw on the race's time as the wall clock plays it (a replay at 2× throws twice as fast). */
const atSpeed = (toss: Toss): Toss => {
  const k = speed.value;
  return k === 1 ? toss : { ...toss, ms: toss.ms / k, delay: (toss.delay ?? 0) / k, at: (toss.at ?? 0) / k };
};
/** A seat's die: its face, keyed so each throw remounts it once; the throw while it is in the air. */
interface SeatDie { key: string; face: number; toss: Toss | null; out: boolean }
/**
 * A member's die in the opening: the face it shows, keyed by the round it was last thrown in; the throw while its
 * round is in the air (staggered among those throwing), dimmed once its place is settled.
 */
function openingDie(m: string): SeatDie | null {
  const o = opening.value;
  const rolls = stage.value?.rolls;
  if (!o || !rolls || o.round < 0) return null;
  const k = o.rolling.indexOf(m);
  let thrown = o.round;
  while (thrown > 0 && !rolls[thrown].some((r) => r.m === m)) thrown--;
  if (k >= 0 && o.tumbling) {
    const face = rolls[o.round][k].face;
    const { delay, ms } = staggered(OPEN_ROLL_MS, k, o.rolling.length);
    const toss = reducedMotion.value ? null : atSpeed({ ms, delay, at: o.since, pool: ORDER_FACES, seed: MEMBERS.indexOf(m), height: 95 });
    return { key: `${m}o${thrown}`, face, toss, out: false };
  }
  return { key: `${m}o${thrown}`, face: o.faces[m] ?? 0, toss: null, out: k < 0 && !o.lined };
}
/** The round whose dice are out, once the opening is over. */
const round = computed(() => (stage.value?.moves && playing.value && !opening.value ? roundAt(stage.value, stageNow.value) : null));
/**
 * A member's die in a round: the five thrown together at the round's start (staggered, landing by DICE_TOSS of
 * rollMs), lying in the row after; dimmed once its move is done.
 */
function roundDie(m: string): SeatDie | null {
  const r = stage.value;
  const ra = round.value;
  if (!r || !ra) return null;
  const dice = roundDice(r, ra.round);
  const k = dice.findIndex((d) => d.m === m);
  if (k < 0) return null;
  const len = (r.rollMs ?? 0) * DICE_TOSS;
  const { delay, ms } = staggered(len, k, dice.length);
  const toss = reducedMotion.value || ra.since >= len
    ? null
    : atSpeed({ ms, delay, at: ra.since, pool: diceOf(m), seed: ra.round * ROUND + k, height: 110 });
  const i = ra.round * ROUND + k;
  const done = !!head.value && i < (r.moves?.length ?? 0) && i < head.value.done && head.value.current !== i;
  return { key: `${m}r${ra.round}`, face: dice[k].face, toss, out: done };
}
/** The throws in the air, by member: read as a die comes up and not followed, since they change with every tick. */
const tosses: { now: Record<string, Toss | null> } = { now: {} };
const diceText = computed(() => {
  const air: Record<string, Toss | null> = {};
  const shown = seats.value.map((m) => {
    const d = opening.value ? openingDie(m) : roundDie(m);
    air[m] = d?.toss ?? null;
    return d ? { m, key: d.key, face: d.face, out: d.out, air: !!d.toss } : { m };
  });
  tosses.now = air;
  return JSON.stringify(shown);
});
/** A seat's die as the row shows it; `air`: its throw is in `tosses`. */
const seatDice = computed(() =>
  Object.fromEntries((JSON.parse(diceText.value) as { m: string; key?: string; face?: number; out?: boolean; air?: boolean }[])
    .map((d) => [d.m, d.key ? d : null])),
);
/** Whose turn it is in the step under way, and whether it still waits for its die. */
const mover = computed(() => {
  const r = stage.value;
  const h = head.value;
  return r?.moves && h && h.current >= 0 ? r.moves[h.current].m : "";
});
const moverWaits = computed(() => !!mover.value && !!head.value && stageOf(head.value.part) !== "walk");
/** The last round's dice have just been thrown. */
const lastRound = computed(() => {
  const r = stage.value;
  const ra = round.value;
  if (!r || !ra || roundsOf(r) < 2 || ra.round !== roundsOf(r) - 1) return false;
  return ra.since < CUE_MS;
});
/** What the bar says is on. */
const status = computed(() => {
  if (opening.value) return "掷骰定序";
  if (round.value) return `第 ${round.value.round + 1} 轮`;
  return "";
});

// ---------------------------------------------------------------- my bets and the result
/** My bets on the race on the board, one a selection: the coins in all, and whether it won once the race is run. */
const tickets = computed(() => {
  const r = stage.value;
  const out: { key: string; kind: string; member: string; odds: number[]; coins: number; won: boolean }[] = [];
  for (const b of r?.mine ?? []) {
    const key = `${b.kind}${b.member}`;
    const t = out.find((o) => o.key === key);
    if (t) {
      t.coins += b.coins;
      if (!t.odds.includes(b.odds)) t.odds.push(b.odds);
    } else out.push({ key, kind: KIND_NAMES[b.kind], member: b.member, odds: [b.odds], coins: b.coins, won: finished.value && !!r?.ranking && hits(b.kind, b.member, r.ranking) });
  }
  for (const t of out) t.odds.sort((a, b) => b - a);
  return out;
});
const oddsList = (odds: number[]) =>
  (odds.length > 2 ? `×${odds[0].toFixed(1)}–${odds[odds.length - 1].toFixed(1)}` : odds.map(x).join(" "));
const ranking = computed(() => (finished.value ? stage.value?.ranking ?? [] : []));
/** A place lights up when one of my bets on the tuanzi in it won; one I bet on that won nothing greys out. */
function lit(place: number): boolean {
  const m = ranking.value[place];
  return !!m && !!stage.value?.mine.some((b) => b.member === m && hits(b.kind, b.member, ranking.value));
}
const missed = (place: number) => !!stage.value?.mine.some((b) => b.member === ranking.value[place]) && !lit(place);
const won = computed(() => (finished.value ? stage.value?.result?.won ?? 0 : 0));

// ---------------------------------------------------------------- the finish
/*
 * At the finish each tuanzi flies from its square on the board onto the podium (FLIP), the steps rising under them.
 * Without motion the podium is simply there.
 */
const stageEl = ref<HTMLElement | null>(null);
let flipFrom: Map<string, DOMRect> | null = null;
watch(view, (to, from) => {
  flipFrom = null;
  if (from !== "run" || to !== "podium" || reducedMotion.value || !stageEl.value) return;
  flipFrom = new Map();
  for (const el of stageEl.value.querySelectorAll<HTMLElement>(".tz[data-m]")) {
    const token = el.querySelector(".tuanzi-token");
    if (token) flipFrom.set(el.dataset.m!, token.getBoundingClientRect());
  }
  void nextTick(flyToPodium);
}, { flush: "pre" });

function flyToPodium() {
  const from = flipFrom;
  flipFrom = null;
  const root = stageEl.value?.querySelector<HTMLElement>(".podium");
  if (!from || !root) return;
  root.querySelectorAll<HTMLElement>(".place").forEach((place, i) => {
    const token = place.querySelector<HTMLElement>("[data-m]");
    const was = token && from.get(token.dataset.m!);
    if (token && was) {
      const to = token.getBoundingClientRect();
      if (to.width) {
        const move = `translate(${was.left - to.left}px, ${was.top - to.top}px) scale(${was.width / to.width})`;
        token.animate([{ transform: move, transformOrigin: "0 0" }, { transform: "none", transformOrigin: "0 0" }],
          { duration: 720, delay: i * 70, easing: EASE_OUT, fill: "backwards" });
      }
    }
    place.querySelector<HTMLElement>(".step")?.animate(
      [{ transform: "scaleY(0)", transformOrigin: "50% 100%" }, { transform: "none", transformOrigin: "50% 100%" }],
      { duration: 520, delay: 160 + i * 70, easing: EASE_OUT, fill: "backwards" },
    );
  });
}

function onBarDown(e: PointerEvent) {
  if (e.button === 0 && !(e.target as HTMLElement).closest("button")) emit("drag", e);
}
// Escape closes it, and only it: in the browser preview the panel under the frame hears the same key.
function onKey(e: KeyboardEvent) {
  if (e.key !== "Escape") return;
  e.stopPropagation();
  emit("close");
}
onMounted(() => window.addEventListener("keydown", onKey, true));
onBeforeUnmount(() => window.removeEventListener("keydown", onKey, true));
</script>

<template>
  <section class="watch" :class="{ calm: reducedMotion }" aria-label="团子赛跑">
    <div class="sheet">
    <header class="bar" @pointerdown="onBarDown">
      <h1>团子赛跑</h1>
      <span v-if="stage?.setup.map" class="map">{{ stage.setup.map.name }}</span>
      <span v-if="played" class="mode"><Icon name="play" :size="12" />回放 {{ shortDay(played.day) }}</span>
      <span v-else-if="view === 'run'" class="mode live"><i class="dot" aria-hidden="true"></i>直播</span>
      <span v-if="status" class="round">{{ status }}</span>
      <span class="grow"></span>
      <template v-if="played">
        <i class="progress" aria-hidden="true"><i :style="{ width: `${progress * 100}%` }"></i></i>
        <button
          type="button" class="ui-btn small ghost speed-key" :class="{ on: speed === 2 }" :aria-pressed="speed === 2"
          @click="setSpeed(speed === 2 ? 1 : 2)"
        >2×</button>
        <button v-if="!finished" type="button" class="ui-btn small ghost" aria-label="跳到结果" @click="toEnd">
          <Icon name="skip" :size="16" />
        </button>
        <button v-else type="button" class="ui-btn small ghost" aria-label="再看一遍" @click="seek(0)">
          <Icon name="refresh" :size="16" />
        </button>
        <button v-if="liveOn" type="button" class="ui-btn small live-key" @click="played = null">
          <i class="dot" aria-hidden="true"></i>直播
        </button>
      </template>
      <button type="button" class="ui-btn small ghost" aria-label="关闭" @click="emit('close')"><Icon name="close" :size="16" /></button>
    </header>

    <div ref="stageEl" class="stage">
      <RaceTrack
        :key="trackKey" class="lap" :race="stage" :t="stageNow" :rate="speed" :track="track" :members="MEMBERS"
        :caption="stage?.setup.map?.name" :cleared="view === 'podium'"
      />
      <p v-if="loadError || replayError" class="ui-error note" role="alert">{{ replayError || loadError }}</p>
      <Transition name="card">
        <div v-if="view === 'wait' && wait" class="card wait" role="status">
          <small>{{ wait.label }}</small>
          <b v-if="wait.time">{{ wait.time }}</b>
        </div>
        <div v-else-if="view === 'podium'" class="card result">
          <ol class="podium" aria-label="本场名次">
            <li
              v-for="(m, i) in ranking" :key="m" class="place" :class="[`p${i + 1}`, { lit: lit(i), missed: missed(i) }]"
              :title="nameOf(m)"
            >
              <TuanziToken :member="m" :size="i === 0 ? 72 : i < 3 ? 48 : 32" :grey="missed(i)" :data-m="m" />
              <span class="step">{{ i + 1 }}</span>
            </li>
          </ol>
          <p v-if="won > 0" class="net" role="status" :aria-label="`+${fmt(won)} 驼币`">
            <ParkCoin class="net-coin" fill :tilt="false" /><b>+{{ fmt(won) }}</b>
          </p>
          <p v-if="!played && wait?.time" class="next">{{ wait.label }} <b>{{ wait.time }}</b></p>
        </div>
      </Transition>
    </div>

    <aside class="side">
      <TransitionGroup tag="ol" name="rank" class="field" aria-label="名次">
        <li v-for="(m, i) in order" :key="m" class="runner" :class="{ turn: mover === m, first: i === 0 && field.led }">
          <b class="no">{{ i + 1 }}</b>
          <TuanziToken class="face" :member="m" :size="48" />
          <span class="who">
            <span class="line">
              <i class="hue" :style="{ background: colorOf(m) }" aria-hidden="true"></i>
              <span class="name">{{ nameOf(m) }}</span>
              <span v-if="traitOf(m)" class="trait" :title="traitOf(m)!.text || undefined">{{ traitOf(m)!.name }}</span>
            </span>
            <span v-if="skillOf(m)" class="does">{{ traitOf(m)!.text }}</span>
            <i class="along" aria-hidden="true"><i :style="{ width: `${along(m) * 100}%` }"></i></i>
          </span>
          <span class="tail">
            <span class="form" :aria-label="`骰子 ${diceOf(m).join(' ')}`">
              <RaceDie v-for="(f, k) in diceOf(m)" :key="k" :face="f" :color="colorOf(m)" />
            </span>
            <span v-if="mineOn(m)" class="mine"><img :src="COIN_SMALL" alt="" draggable="false" />{{ mineOn(m) }}</span>
          </span>
        </li>
      </TransitionGroup>
      <ul v-if="tickets.length" class="tickets" aria-label="我的押注">
        <li v-for="t in tickets" :key="t.key" class="ticket" :class="{ won: t.won }">
          <TuanziToken :member="t.member" :size="24" />
          <small>{{ t.kind }}</small><b>{{ oddsList(t.odds) }}</b>
          <span class="coin"><img :src="COIN_SMALL" alt="" draggable="false" />{{ t.coins }}</span>
        </li>
      </ul>
    </aside>

    <footer class="deck">
      <TransitionGroup v-if="seats.length && view === 'run'" tag="ol" name="seat" class="lineup" aria-label="出场顺序">
        <li
          v-for="m in seats" :key="m" class="seat"
          :class="{ turn: mover === m, waiting: mover === m && moverWaits }" :title="nameOf(m)"
        >
          <span class="slot">
            <RaceDie
              v-if="seatDice[m]" :key="seatDice[m]!.key" class="seat-die" :class="{ out: seatDice[m]!.out }"
              :face="seatDice[m]!.face!" :toss="seatDice[m]!.air ? tosses.now[m] : null" :color="colorOf(m)"
            />
          </span>
          <span class="head"><TuanziToken :member="m" :size="48" /></span>
        </li>
      </TransitionGroup>
      <p v-if="lastRound" class="cue" role="status">最后一轮</p>
    </footer>
    </div>
  </section>
</template>

<style scoped>
/*
 * The window's face: the bar across the top, the board's stage with the order of play under it, the field down the
 * right. It fills its box (the window, or the preview's frame) and is the size container the parts follow.
 */
.watch {
  position: absolute;
  inset: 0;
  overflow: hidden;
  border-radius: var(--radius-l);
  background: var(--c-50);
  font-family: var(--font);
  color: var(--ink);
  container: watch / size;
}
.sheet {
  display: grid;
  grid-template: "bar bar" 46px "stage side" minmax(0, 1fr) "deck side" 104px / minmax(0, 1fr) 286px;
  height: 100%;
}

/* ---- the bar: coral, the window's handle */
.bar {
  grid-area: bar;
  position: relative;
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 8px 0 18px;
  background: var(--grad-sky);
  box-shadow: 0 1px 0 rgba(var(--c-900-rgb), 0.12);
  user-select: none;
}
.bar h1 {
  margin: 0;
  font: 800 var(--fs-section)/1 var(--font);
  letter-spacing: 0.04em;
  color: var(--ink);
}
.map,
.mode,
.round {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  font: 800 var(--fs-label)/1 var(--font);
  white-space: nowrap;
}
.map {
  background: var(--surface);
  color: var(--ink);
}
.mode,
.round {
  background: rgba(var(--c-900-rgb), 0.12);
  color: var(--ink);
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
  animation: beat 1.2s var(--ease-out) infinite;
}
@keyframes beat {
  50% { opacity: 0.25; }
}
.grow {
  flex: 1 1 auto;
}
.progress {
  flex: 0 1 220px;
  min-width: 40px;
  height: 4px;
  border-radius: 2px;
  background: rgba(var(--c-900-rgb), 0.16);
  overflow: hidden;
}
.progress > i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--surface);
}
.speed-key {
  min-width: 40px;
  font: 800 var(--fs-number)/1 var(--font-latin);
}
.speed-key.on:not(:disabled) {
  --key-top: var(--surface);
  --key-bottom: var(--surface);
}
.live-key {
  gap: 6px;
}

/* ---- the stage: the board as large as it fits, what is between races on a card over it */
.stage {
  grid-area: stage;
  position: relative;
  min-width: 0;
  min-height: 0;
  padding: 10px 18px 0;
  display: flex;
}
.lap {
  flex: 1 1 auto;
}
.note {
  position: absolute;
  left: 50%;
  top: 14px;
  z-index: 6;
  margin: 0;
  translate: -50% 0;
  box-shadow: var(--shadow-paper);
}
.card {
  position: absolute;
  left: 50%;
  top: 50%;
  z-index: 6;
  translate: -50% -50%;
  display: flex;
  flex-direction: column;
  align-items: center;
  border-radius: var(--radius-l);
  background: var(--surface);
  box-shadow: var(--shadow-paper), 0 18px 44px -18px rgba(var(--c-900-rgb), 0.5);
}
.card-enter-active {
  transition: opacity 320ms var(--ease-out), scale 320ms var(--ease-pop);
}
.card-leave-active {
  transition: opacity 200ms var(--ease-in);
}
.card-enter-from {
  opacity: 0;
  scale: 0.9;
}
.card-leave-to {
  opacity: 0;
}
.wait {
  gap: 6px;
  min-width: 168px;
  padding: 16px 28px 18px;
}
.wait small {
  font: 800 var(--fs-label)/1 var(--font);
  color: var(--ink-2);
}
.wait b {
  font: 800 44px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}

/* ---- finished: the podium, the last two on the floor beside it, and what my bets won */
.result {
  gap: 10px;
  padding: 26px 34px 18px;
}
.podium {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.place {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  width: 92px;
  --tuanzi-size: 64px;
}
/* Second on the left, the winner in the middle, third on the right; the last two stand on the floor beside. */
.place.p1 { order: 2; --tuanzi-size: 96px; width: 112px; }
.place.p2 { order: 1; }
.place.p3 { order: 3; }
.place.p4,
.place.p5 {
  width: 56px;
  --tuanzi-size: 40px;
}
.place.p4 { order: 4; margin-left: 12px; }
.place.p5 { order: 5; }
.step {
  display: grid;
  place-items: center;
  width: 100%;
  height: 20px;
  border-radius: var(--radius-s) var(--radius-s) 0 0;
  background: var(--c-100);
  font: 800 var(--fs-heading)/1 var(--font-latin);
  color: var(--ink-3);
}
.p1 .step { height: 64px; font-size: 28px; }
.p2 .step { height: 44px; }
.p3 .step { height: 30px; }
.p4 .step,
.p5 .step {
  font-size: var(--fs-number);
}
.place.lit .step {
  background: var(--c-500);
  color: var(--ink);
}
.place.missed .step {
  opacity: 0.6;
}
.net {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  color: var(--c-700);
}
.net-coin {
  --size: 36px;
}
.net b {
  font: 800 40px/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  animation: win-pop 600ms var(--ease-pop) both;
}
@keyframes win-pop {
  0% { transform: scale(0.6); opacity: 0; }
}
.next {
  margin: 0;
  font: 700 var(--fs-label)/1 var(--font);
  color: var(--ink-2);
}
.next b {
  font: 800 var(--fs-number)/1 var(--font-latin);
  font-variant-numeric: tabular-nums;
  color: var(--ink);
}

/* ---- the field down the right: a sheet of paper, first on top */
.side {
  grid-area: side;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
  padding: 12px 12px 12px 0;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.runner {
  position: relative;
  display: grid;
  grid-template-columns: 18px 44px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  min-height: 62px;
  padding: 6px 10px 6px 8px;
  box-sizing: border-box;
  border-radius: var(--radius-m);
  background: var(--surface);
  box-shadow: var(--shadow-paper);
  transition: background 240ms var(--ease-out), box-shadow 240ms var(--ease-out);
}
.rank-move {
  transition: transform 520ms var(--ease-in-out);
}
/* Whose turn it is: the row latched in coral. */
.runner.turn {
  background: var(--c-200);
  box-shadow: 0 0 0 2px var(--c-500), var(--shadow-paper);
}
.no {
  text-align: center;
  font: 800 var(--fs-heading)/1 var(--font-latin);
  color: var(--ink-3);
}
.runner.first .no {
  color: var(--c-700);
}
.runner .face {
  --tuanzi-size: 44px;
}
.who {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.line {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
}
.hue {
  flex: none;
  width: 3px;
  height: 12px;
  border-radius: 1px;
}
.name {
  font: 800 var(--fs-body)/1.1 var(--font);
  color: var(--ink);
  white-space: nowrap;
}
.trait {
  flex: none;
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--c-500);
  font: 800 var(--fs-caption)/1.1 var(--font);
  color: var(--ink);
  white-space: nowrap;
}
.does {
  overflow: hidden;
  font: 700 var(--fs-caption)/1.1 var(--font);
  color: var(--ink-2);
  text-overflow: ellipsis;
  white-space: nowrap;
}
/* How far along: a thin bar, the member's place on the track. */
.along {
  display: block;
  height: 3px;
  border-radius: 2px;
  background: var(--c-100);
  overflow: hidden;
}
.along > i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--c-500);
  transition: width 480ms var(--ease-out);
}
.tail {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 5px;
}
.form {
  display: flex;
  gap: 2px;
}
.form .race-die {
  --s: 12px;
  --die-shadow: none;
}
.mine {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font: 800 var(--fs-strong)/1 var(--font-latin);
  color: var(--ink);
}
.mine img {
  width: 15px;
  height: 15px;
}
/* My bets: paper tickets under the field, the winners coral once the race is run. */
.tickets {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
  overflow: hidden;
}
.ticket {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 30px;
  padding: 0 9px 0 5px;
  box-sizing: border-box;
  border-radius: var(--radius-s);
  background: var(--surface);
  border-left: 3px dotted var(--c-300);
  box-shadow: 0 1px 2px rgba(var(--c-900-rgb), 0.12), 0 3px 6px -3px rgba(var(--c-900-rgb), 0.2);
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
.ticket.won {
  background: var(--c-500);
  border-left-color: #fff;
}
.ticket.won small,
.ticket.won .coin {
  color: var(--ink);
}

/*
 * ---- under the board: the lineup, a row of seats in the order of play, first to move on the left: each a die in the
 * member's colour over its tuanzi.
 */
.deck {
  grid-area: deck;
  position: relative;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding: 0 18px 10px;
}
.lineup {
  --seat: 58px;
  --die-size: calc(var(--seat) * 0.62);
  --face: calc(var(--seat) * 0.66);
  display: flex;
  align-items: flex-end;
  gap: 22px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.seat {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: calc(var(--seat) * 0.12);
  width: var(--seat);
}
/* The die rests on the seat's top; it rises when its tuanzi's turn comes, and fades once that move is done. */
.slot {
  display: grid;
  place-items: end center;
  width: var(--die-size);
  height: var(--die-size);
}
.seat-die {
  --s: var(--die-size);
  transition: opacity 280ms var(--ease-out), translate 280ms var(--ease-pop), scale 280ms var(--ease-pop);
}
.seat-die.out {
  opacity: 0.35;
}
.seat.turn .seat-die {
  translate: 0 calc(var(--seat) * -0.16);
  scale: 1.08;
  filter: drop-shadow(0 0 calc(var(--seat) * 0.08) rgba(var(--c-500-rgb), 0.9));
}
.seat .head {
  display: grid;
  place-items: center;
  width: var(--seat);
  height: calc(var(--seat) * 0.82);
  border-radius: 999px;
  background: var(--c-100);
  --tuanzi-size: var(--face);
  transition: translate 280ms var(--ease-pop), background 280ms var(--ease-out), box-shadow 280ms var(--ease-out);
}
.seat.turn .head {
  translate: 0 -4px;
  background: var(--c-500);
  box-shadow: var(--shadow-backlight);
}
.seat.waiting .head {
  animation: seat-glow 1s var(--ease-in-out) infinite alternate;
}
@keyframes seat-glow {
  from { box-shadow: 0 0 0 0 rgba(var(--c-500-rgb), 0.6); }
  to { box-shadow: 0 0 0 7px rgba(var(--c-500-rgb), 0); }
}
.seat-move {
  transition: transform 640ms var(--ease-in-out);
}
/* The last round: a coral tag stamped at the deck's right. */
.cue {
  position: absolute;
  right: 18px;
  bottom: 34px;
  margin: 0;
  padding: 4px 12px;
  border-radius: 999px;
  background: var(--c-500);
  box-shadow: var(--shadow-backlight);
  font: 800 var(--fs-body)/1.2 var(--font);
  color: var(--ink);
  white-space: nowrap;
  animation: cue 2.6s var(--ease-out) both;
}
@keyframes cue {
  0% { opacity: 0; transform: scale(1.6); }
  14% { opacity: 1; transform: scale(0.94); }
  22% { transform: scale(1); }
  85% { opacity: 1; transform: scale(1); }
  100% { opacity: 0; transform: scale(1); }
}

.calm .dot,
.calm .net b,
.calm .cue,
.calm .seat.waiting .head {
  animation: none;
}
.calm .rank-move,
.calm .seat-move,
.calm .seat .head,
.calm .seat-die,
.calm .along > i,
.calm .card-enter-active,
.calm .card-leave-active {
  transition: none;
}

/* A low window: the deck and the rows close up. */
@container watch (max-height: 640px) {
  .sheet {
    grid-template-rows: 46px minmax(0, 1fr) 88px;
  }
  .lineup {
    --seat: 48px;
  }
  .runner {
    min-height: 54px;
  }
  .does {
    display: none;
  }
}
@container watch (max-width: 940px) {
  .sheet {
    grid-template-columns: minmax(0, 1fr) 236px;
  }
  .form {
    display: none;
  }
}
</style>
