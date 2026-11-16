// The reels: while spinning, each number key shows a window onto an endless column of digits. Cell 0 is what the key
// showed, later cells run through every digit, and the cell a reel stops on is given the digit it lands on. Two cells
// are in the window at a time; they are written straight to the DOM each frame (transform only).
import { nextTick, ref, type Ref } from "vue";
import { reelDigit } from "./lottery";
import type { Plays } from "./lotteryPlays";
import { onKeys, spotOf, type Spot } from "./lotterySpots";

/** A reel at full spin, in cells per ms, and the time it takes to get there from rest. */
const SPIN_SPEED = 0.02;
const SPIN_UP_MS = 160;
/** A reel slowing to a stop eases out from full spin over at least this long (up to 3 / SPIN_SPEED ms more). */
const SETTLE_MS = 420;
/** 机选: the keys spin at least this long, then stop left to right this far apart. */
const BUY_SPIN_MS = 260;
const BUY_STOP_GAP_MS = 110;

interface Reel {
  /** Cells travelled; cell k sits (pos - k) cells down from the window. */
  pos: number;
  from: string;
  /** When to start slowing (performance time), and the digit to land on. */
  stopAt: number | null;
  land: string;
  /** Slowing down: from p0 at t0 to the cell `end` over `ms`, easing out from full spin. */
  end: number;
  p0: number;
  t0: number;
  ms: number;
  done: boolean;
  /** The cell each of the two cell elements shows. */
  shown: [number, number];
}

export interface ReelsDeps {
  plays: Plays;
  keysEl: Ref<HTMLElement | undefined>;
  /** How the faces come onto the keys once the reels are gone. */
  faceIn: Ref<"" | "fade" | "still">;
  /** A key pressed down for a moment, as each reel lands. */
  press: (i: number) => void;
  /** The globe's air, on while the keys spin. */
  airOn: () => void;
  airOff: () => void;
}

export function useReels({ plays, keysEl, faceIn, press, airOn, airOff }: ReelsDeps) {
  const reeling = ref<"" | "buy">("");
  let reels: Reel[] = [];
  let reelCells: HTMLElement[][] = [];
  let reelFrame = 0;
  let reelStart = 0;
  let lastFrame = 0;
  let onLand: (i: number) => void = () => {};
  let onRest: () => void = () => {};

  function cellDigit(r: Reel, i: number, k: number): string {
    if (k === 0) return r.from;
    if (!r.ms) return reelDigit(k, i);
    if (k === r.end) return r.land;
    const d = reelDigit(k, i);
    // The cell before the stop never shows the digit it stops on.
    return k === r.end - 1 && d === r.land ? reelDigit(k + 5, i) : d;
  }
  function paint(i: number) {
    const r = reels[i];
    const els = reelCells[i];
    if (!r || !els || els.length < 2) return;
    const k0 = Math.floor(r.pos);
    for (const k of [k0, k0 + 1]) {
      const el = els[k % 2]!;
      if (r.shown[k % 2] !== k) {
        r.shown[k % 2] = k;
        const d = cellDigit(r, i, k);
        el.textContent = d;
        el.classList.toggle("void", !d);
        el.classList.remove("landed");
      }
      el.style.transform = `translateY(${(r.pos - k) * 100}%)`;
    }
  }
  function spin(t: number) {
    // A frame's time can be a little behind performance.now() taken at the start.
    const dt = Math.min(64, Math.max(0, t - lastFrame));
    lastFrame = Math.max(lastFrame, t);
    const v = SPIN_SPEED * Math.min(1, Math.max(0, t - reelStart) / SPIN_UP_MS);
    let running = false;
    reels.forEach((r, i) => {
      if (r.done) return;
      if (r.stopAt !== null && !r.ms && t >= r.stopAt) {
        r.p0 = r.pos;
        r.t0 = t;
        r.end = Math.ceil(r.pos + (SPIN_SPEED * SETTLE_MS) / 3);
        // An ease-out cubic starts at three times its average speed: start it at full spin.
        r.ms = (3 * (r.end - r.pos)) / SPIN_SPEED;
      }
      if (r.ms) {
        const u = Math.min(1, (t - r.t0) / r.ms);
        r.pos = r.p0 + (r.end - r.p0) * (1 - (1 - u) ** 3);
        if (u >= 1) {
          r.pos = r.end;
          r.done = true;
        }
      } else {
        r.pos += v * dt;
      }
      paint(i);
      if (r.done) {
        reelCells[i]?.[r.end % 2]?.classList.add("landed");
        onLand(i);
      } else {
        running = true;
      }
    });
    if (running) reelFrame = requestAnimationFrame(spin);
    else {
      reelFrame = 0;
      onRest();
    }
  }
  /** 机选: starts the three keys spinning from [from] while the balls blow in the globe. */
  function startReels(from: readonly string[]) {
    const g = plays.gen;
    reeling.value = "buy";
    reels = [0, 1, 2].map((i) => ({
      pos: 0, from: from[i] ?? "", stopAt: null, land: "", end: 0, p0: 0, t0: 0, ms: 0, done: false, shown: [-1, -1],
    }));
    onLand = () => {};
    onRest = () => {};
    reelStart = performance.now();
    airOn();
    // The reel windows are in the DOM after this render.
    void nextTick(() => {
      if (g !== plays.gen) return;
      reelCells = Array.from(keysEl.value?.querySelectorAll(".reel") ?? [], (el) => Array.from(el.children) as HTMLElement[]);
      reelStart = lastFrame = performance.now();
      reels.forEach((_, i) => paint(i));
      reelFrame = requestAnimationFrame(spin);
    });
  }
  /** The spinning keys stop on [digits] left to right, no sooner than BUY_SPIN_MS after they started. */
  function stopReels(digits: readonly string[], rest: () => void) {
    const t = Math.max(performance.now(), reelStart + BUY_SPIN_MS);
    reels.forEach((r, i) => {
      r.stopAt = t + i * BUY_STOP_GAP_MS;
      r.land = digits[i] ?? "";
    });
    onLand = press;
    onRest = () => {
      airOff();
      rest();
    };
  }
  /** The keys show their faces again: [face] says how they come in. */
  function endReels(face: "fade" | "still") {
    cancelAnimationFrame(reelFrame);
    reelFrame = 0;
    reels = [];
    reelCells = [];
    faceIn.value = face;
    reeling.value = "";
  }
  /** Where the digits the reels stopped on are on the keys. */
  function reelSpots(): Spot[] {
    return onKeys(keysEl.value, reels.map((r, i) => spotOf(reelCells[i]?.[r.end % 2], r.land)));
  }

  return { reeling, startReels, stopReels, endReels, reelSpots };
}
