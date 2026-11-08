// The sidebar alpaca's speech: pages hand it a line, AlpacaEasterEgg shows it.
import { ref } from "vue";

export const alpacaLine = ref<{ text: string; at: number } | null>(null);

export function alpacaSay(text: string): void {
  alpacaLine.value = { text, at: Date.now() };
}
