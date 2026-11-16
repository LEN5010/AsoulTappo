// The first showing of a draw, on the keys: the balls blow, then the drawn digits' balls drop into the windows one by
// one from the right, each lighting the digits of my stubs it matches and fading the stubs it rules out; then the
// stamps go down and the win counts up.
import { nextTick, ref, type ComputedRef, type Ref } from "vue";
import { countTo } from "./countTo";
import type { LotteryState } from "./lottery";
import type { Plays } from "./lotteryPlays";

/** The balls blow DRAW_FIRST_MS before the last digit's ball goes, each digit to its left DRAW_GAP_MS later. The
 * stamps go down DRAW_STAMP_MS after the first digit's ball is in; the keys go back no sooner than DRAW_HOLD_MS after
 * that. */
const DRAW_FIRST_MS = 1000;
const DRAW_GAP_MS = 950;
const DRAW_STAMP_MS = 180;
const DRAW_HOLD_MS = 650;
/** How long the win in the bar counts up, by the best tier won. */
const ROLL_MS: Record<1 | 2 | 3, number> = { 1: 400, 2: 650, 3: 900 };

export interface RevealDeps {
  plays: Plays;
  last: ComputedRef<LotteryState["last"] | null>;
  /** Today is drawn and shown: the keys come back still instead of fading in. */
  showDraw: ComputedRef<boolean>;
  faceIn: Ref<"" | "fade" | "still">;
  /** Ends whatever plays on the keys, before the reveal starts. */
  settle: () => void;
  layoutTube: () => void;
  airOn: () => void;
  airOff: () => void;
  /** Draws the ball of a digit out of the globe into window i; calls back once it is in. */
  sendBall: (i: number, d: string, done: () => void) => void;
}

export function useDrawReveal({ plays, last, showDraw, faceIn, settle, layoutTube, airOn, airOff, sendBall }: RevealDeps) {
  /** The day whose draw is showing; "" when none. */
  const reveal = ref("");
  /** Trailing digits of the draw at rest; 3 when nothing is playing. */
  const stopped = ref(3);
  /** The stamps and the result in the bar are out. */
  const stamped = ref(true);
  const wonShown = ref(0);
  let stopWon = () => {};

  function startReveal(day: string) {
    const d = last.value;
    if (!d) return;
    settle();
    reveal.value = day;
    stopped.value = 0;
    stamped.value = false;
    wonShown.value = 0;
    void nextTick(() => {
      layoutTube();
      airOn();
    });
    const number = d.number.split("");
    const land = () => {
      stopped.value++;
      if (stopped.value < 3) return;
      plays.later(DRAW_STAMP_MS, () => {
        stamped.value = true;
        const best = d.mine.some((t) => t.tier === "top") ? 3 : d.mine.some((t) => t.tier === "second") ? 2 : 1;
        const ms = d.won > 0 ? ROLL_MS[best] : 0;
        if (ms) stopWon = countTo(wonShown, d.won, ms);
        plays.later(Math.max(ms, DRAW_HOLD_MS), () => {
          faceIn.value = showDraw.value ? "still" : "fade";
          reveal.value = "";
          stopped.value = 3;
        });
      });
    };
    // From the right: the last digit's ball first; the air dies away once the third ball is on its way.
    [2, 1, 0].forEach((i, n) => plays.later(DRAW_FIRST_MS + n * DRAW_GAP_MS, () => {
      sendBall(i, number[i]!, land);
      if (n === 2) plays.later(350, airOff);
    }));
  }
  /** Back at rest: no draw showing, the stamps out, the win counter stopped. */
  function resetReveal() {
    stopWon();
    reveal.value = "";
    stopped.value = 3;
    stamped.value = true;
  }

  return { reveal, stopped, stamped, wonShown, startReveal, resetReveal };
}
