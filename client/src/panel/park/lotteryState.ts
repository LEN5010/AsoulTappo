// The lottery's state from the server and what follows from it: the clock, the next draw, the last draw and the
// stubs on the table. There is no push: while the page is open the state loads every POLL_MS, and every few seconds
// once the close or the draw is due.
import { computed, ref } from "vue";
import { status } from "../../stores/player";
import { parkTry } from "../../stores/park";
import { countdown, dayBefore, nextDraw, salesOpen, shortDay, winnersLine, type LotteryState } from "./lottery";

const POLL_MS = 20000;
/** After the close or the draw time, until the state shows it. */
const DUE_POLL_MS = 4000;

export function useLotteryState() {
  const state = ref<LotteryState | null>(null);
  const loadError = ref("");
  const now = ref(Date.now() / 1000);

  let loading = false;
  let loadedAt = 0;
  async function load() {
    if (loading) return;
    loading = true;
    loadedAt = Date.now();
    const player = status.value?.player;
    try {
      const r = await parkTry<LotteryState>("GET", "/api/park/lottery");
      if (player !== status.value?.player) return;
      if (r.ok) {
        state.value = r.data;
        loadError.value = "";
      } else if (!state.value && r.error.status > 0) {
        loadError.value = r.error.message;
      }
    } finally {
      loading = false;
    }
  }

  // ---- the clock: the countdown, the close on this machine's clock, and loading again on time
  let timer: ReturnType<typeof setInterval> | null = null;
  function tick() {
    now.value = Date.now() / 1000;
    const s = state.value;
    // Past the close the keys are off at once; the state loads right away, then often until the server agrees.
    const closing = !!s && s.open && now.value >= s.closeAt;
    const due = closing || (!!s && !s.drawn && now.value >= s.drawAt);
    if ((closing && loadedAt < s!.closeAt * 1000) || Date.now() - loadedAt >= (due ? DUE_POLL_MS : POLL_MS)) void load();
  }
  /** Starts the clock and loads, unless it already runs. */
  function startClock() {
    if (timer) return;
    now.value = Date.now() / 1000;
    void load();
    timer = setInterval(tick, 1000);
  }
  function stopClock() {
    if (timer) clearInterval(timer);
    timer = null;
  }
  const clockRunning = () => timer !== null;

  // ---- the next draw
  const drawTime = computed(() => (state.value ? nextDraw(state.value) : 0));
  const left = computed(() => countdown(drawTime.value, now.value));
  const waiting = computed(() => !!state.value && !state.value.drawn && now.value >= state.value.drawAt);
  /** Sales are over for today, by the server or by this machine's clock. */
  const closed = computed(() => !!state.value && !salesOpen(state.value, now.value));

  // ---- the last draw
  const last = computed(() => state.value?.last ?? null);
  const winning = computed(() => (last.value ? last.value.number.split("") : []));
  /** Today is drawn: the stubs on the table are the ones of the last draw, with their results. */
  const drawnHere = computed(() => !!last.value && last.value.day === state.value?.day);
  const lastName = computed(() => {
    const d = last.value?.day ?? "";
    const today = state.value?.day ?? "";
    return d === today ? "今日" : d === dayBefore(today) ? "昨日" : shortDay(d);
  });
  /**
   * The last draw's stubs, with their results, are on the table: today once it is drawn, and the day after it until the
   * first number of that day is bought, so a draw seen the next morning lights up the stubs it was played with.
   */
  const lastOnTable = computed(() => {
    const s = state.value;
    const d = last.value;
    if (!s || !d) return false;
    return drawnHere.value || (!!d.mine.length && !s.tickets.length && d.day === dayBefore(s.day));
  });
  /** My stubs: today's, or the last draw's with what each matched. */
  const table = computed(() => {
    const s = state.value;
    if (!s) return [];
    if (lastOnTable.value) return last.value!.mine;
    return s.tickets.map((number) => ({ number, tier: null, prize: 0 }));
  });
  /** The day of the stubs on the table, so a stub of one day is never reused for another. */
  const tableDay = computed(() => (lastOnTable.value ? last.value!.day : state.value?.day ?? ""));
  /** Today's tickets show with an empty place for each one still to buy, so a stub never moves when another is bought. */
  const showCount = computed(() => !lastOnTable.value || drawnHere.value);
  const slots = computed(() => (showCount.value ? Math.max(0, (state.value?.daily ?? 0) - table.value.length) : 0));

  /** The server's drawn days with their top prize winners, each with what I won that day (null: I had no tickets). */
  const past = computed(() => {
    const s = state.value;
    if (!s) return [];
    const mine = new Map(s.history.map((h) => [h.day, h.won]));
    return s.draws.map((d) => ({ ...d, winners: winnersLine(d.top), first: winnersLine(d.top, 1), won: mine.get(d.day) ?? null }));
  });
  /** The last draw's stubs when they are not on the table (today's stubs are): they go on top of 往期. */
  const lastAside = computed(() => (!lastOnTable.value && last.value?.mine.length ? last.value : null));
  const hasPast = computed(() => !!lastAside.value || past.value.length > 0);

  return {
    state, loadError, now, load, startClock, stopClock, clockRunning,
    drawTime, left, waiting, closed,
    last, winning, drawnHere, lastName, lastOnTable, table, tableDay, showCount, slots, past, lastAside, hasPast,
  };
}

/** One row of the board of past draws. */
export type PastDraw = ReturnType<typeof useLotteryState>["past"]["value"][number];
