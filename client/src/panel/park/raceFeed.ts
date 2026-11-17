// The live race as the server gives it (protocol/PROTOCOL.md 团子赛跑). There is no push channel: while it runs the
// feed asks GET /api/park/race (every 10 s while bets are open, soon around the start and the end) and keeps the
// offset to the server's clock, so every client plays the same moment. The race page, the race's own window and the
// desk's start reminder each run one.
import { computed, ref } from "vue";
import { parkTry } from "../../stores/park";
import type { Race, RaceAnswer } from "./race";

/** How often the odds are asked for while bets are open, ms. */
const BETTING_POLL = 10_000;
/** How often the race is asked for while it is about to start, ms. */
const STARTING_POLL = 350;
/** How often the clock ticks, ms. */
const TICK = 100;

export const isPlaying = (r: Race | null, t: number) => !!r?.moves && !!r.endsAt && t < r.endsAt * 1000;
export const isFinished = (r: Race | null, t: number) => !!r?.ranking && !!r.endsAt && t >= r.endsAt * 1000;

/**
 * [quiet]: only the race's phases matter (the reminder): the odds are not followed, so while bets are open the next
 * question waits for the start.
 */
export function useRaceFeed(opts: { quiet?: boolean } = {}) {
  const data = ref<RaceAnswer | null>(null);
  const loadError = ref("");
  /** Server time minus local time, ms. */
  const offset = ref(0);
  const now = ref(Date.now());
  const serverNow = computed(() => now.value + offset.value);
  const race = computed(() => data.value?.race ?? null);
  const last = computed(() => data.value?.last ?? null);
  const phase = computed(() => race.value?.phase ?? null);
  const playing = computed(() => isPlaying(race.value, serverNow.value));
  const finished = computed(() => isFinished(race.value, serverNow.value));
  /** The race is out and under way: its order is being rolled, or it is playing. */
  const live = computed(() => phase.value === "starting" || playing.value);

  let active = false;
  let pollTimer: ReturnType<typeof setTimeout> | null = null;
  let clockTimer: ReturnType<typeof setInterval> | null = null;
  let loading = false;
  const hidden = () => typeof document !== "undefined" && document.visibilityState === "hidden";

  /** When to ask next: every 10 s while bets are open, soon around the start and the end, slowly otherwise. */
  function nextDelay(): number {
    const r = race.value;
    const t = serverNow.value;
    const until = (at: number) => at * 1000 - t + 300;
    if (!r || r.phase === "done" || r.phase === "void") {
      return Math.max(1000, Math.min(opts.quiet ? 60_000 : 5000, until(data.value?.nextAt ?? 0)));
    }
    if (r.phase === "betting") return Math.max(1000, Math.min(opts.quiet ? 600_000 : BETTING_POLL, until(r.startsAt)));
    if (r.phase === "running" && r.endsAt && t < r.endsAt * 1000) return Math.max(1000, until(r.endsAt));
    // Starting: the server starts the race on its next tick; the opening's dice come with it.
    return r.phase === "starting" ? STARTING_POLL : 1000;
  }

  async function poll() {
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = null;
    // A hidden window asks again once it shows (onVisible).
    if (!active || loading || hidden()) return;
    loading = true;
    const sent = Date.now();
    const reply = await parkTry<RaceAnswer>("GET", "/api/park/race");
    loading = false;
    if (reply.ok) {
      const got = Date.now();
      offset.value = reply.data.now * 1000 - (sent + got) / 2;
      data.value = reply.data;
      loadError.value = "";
    } else if (reply.error.status > 0) {
      loadError.value = reply.error.message;
    }
    if (active) pollTimer = setTimeout(poll, reply.ok ? nextDelay() : opts.quiet ? 60_000 : 5000);
  }

  function onVisible() {
    if (!hidden()) void poll();
  }
  function start() {
    if (active) return;
    active = true;
    void poll();
    clockTimer = setInterval(() => (now.value = Date.now()), opts.quiet ? 1000 : TICK);
    document.addEventListener("visibilitychange", onVisible);
  }
  function stop() {
    active = false;
    if (pollTimer) clearTimeout(pollTimer);
    if (clockTimer) clearInterval(clockTimer);
    pollTimer = null;
    clockTimer = null;
    document.removeEventListener("visibilitychange", onVisible);
  }

  return { data, loadError, now, serverNow, race, last, phase, playing, finished, live, poll, start, stop };
}

/** h:mm:ss, or m:ss under an hour: a day's race is most of a day away. */
export function raceClock(sec: number): string {
  const s = Math.max(0, Math.ceil(sec));
  const pad = (n: number) => String(n).padStart(2, "0");
  const h = Math.floor(s / 3600);
  return h ? `${h}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}` : `${Math.floor(s / 60)}:${pad(s % 60)}`;
}
