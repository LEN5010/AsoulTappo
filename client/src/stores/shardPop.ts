// "+N" shards over the local pet while typing. Reports reach the server in batches, so the shards each
// counted tap earns are predicted here from the same curve; the server's count of today's taps
// (status.income.taps) corrects the prediction whenever a status arrives.
import { ref, watch } from "vue";
import { tapShards } from "../income";
import { manifest } from "../manifest";
import { TapCombo, type ComboFrame } from "../pet/TapCombo";
import { status } from "./player";
import { settings } from "./settings";

/** China Standard Time, where the server's day starts. */
const DAY_OFFSET_MS = 8 * 3600_000;
const chinaDay = (now: number) => Math.floor((now + DAY_OFFSET_MS) / 86_400_000);
/** The same day as the server writes it, YYYY-MM-DD. */
const dayName = (now: number) => new Date(now + DAY_OFFSET_MS).toISOString().slice(0, 10);

export const shardCombo = ref<ComboFrame | null>(null);
const combo = new TapCombo((f) => (shardCombo.value = f));

let day = chinaDay(Date.now());
let taps = 0;
let minute = -1;
let minuteTaps = 0;
let carry = 0;

/** More than unreported taps can explain: the server's day started over. */
const RESET_GAP = 1000;

// Local taps run ahead of the server until their batch lands, so a slightly smaller count is not taken back.
// A count for another day than the local one (sent before midnight, or a clock off by minutes) is skipped.
watch(() => [status.value?.income.taps, status.value?.income.day] as const, ([server, serverDay]) => {
  if (typeof server !== "number") return;
  const now = Date.now();
  if (serverDay && serverDay !== dayName(now)) return;
  if (chinaDay(now) !== day) {
    day = chinaDay(now);
    taps = 0;
  }
  if (server > taps || taps - server > RESET_GAP) taps = server;
}, { immediate: true });

watch(() => settings.shardPop, (on) => {
  if (!on) {
    combo.stop();
    shardCombo.value = null;
  }
});

/** One counted tap of the local pet. */
export function popShards(now = Date.now()): void {
  // Servers without tap income send no count: nothing to predict.
  if (typeof status.value?.income.taps !== "number") return;
  const today = chinaDay(now);
  if (today !== day) {
    day = today;
    taps = 0;
  }
  const m = Math.floor(now / 60_000);
  if (m !== minute) {
    minute = m;
    minuteTaps = 0;
  }
  if (minuteTaps >= manifest.economy.income.tapsPerMinute) return;
  minuteTaps += 1;
  carry += tapShards(taps + 1) - tapShards(taps);
  taps += 1;
  const whole = Math.floor(carry + 1e-9);
  if (whole < 1) return;
  carry -= whole;
  if (settings.shardPop) combo.add(whole);
}
