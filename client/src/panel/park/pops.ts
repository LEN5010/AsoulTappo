// +n over the coins held in the panel's top bar (ParkChips): today's free coin, and coins just bought.
import { ref } from "vue";

const POP_MS = 1100;
export const coinPops = ref<{ id: number; n: number }[]>([]);
let popId = 0;

export function popCoins(n: number): void {
  const id = ++popId;
  coinPops.value = [...coinPops.value, { id, n }];
  setTimeout(() => (coinPops.value = coinPops.value.filter((p) => p.id !== id)), POP_MS);
}
