import { createSSRApp } from "vue";
import { renderToString } from "vue/server-renderer";
import { expect, it } from "vitest";
import { duel, type DuelState } from "../stores/room";
import DuelBubble from "./DuelBubble.vue";

const result = (won: boolean): DuelState => ({
  id: "d1", other: { id: "friend", nick: "朋友", character: "乃琳" }, sent: true, bet: 15000, prize: 25000,
  phase: "result", answered: false, round: 1, sec: 10, until: 0, hand: "rock", shown: { mine: "rock", theirs: "scissors" },
  won, reason: "",
});

it("writes what a win paid into the result, and nothing extra for a loss", async () => {
  duel.value = result(true);
  const won = await renderToString(createSSRApp(DuelBubble));
  expect(won).toMatch(/赢了<span class="gain"[^>]*><svg[\s\S]*?<\/svg>\+25,000<\/span>/);
  duel.value = result(false);
  const lost = await renderToString(createSSRApp(DuelBubble));
  expect(lost).toContain("输了");
  expect(lost).not.toContain("gain");
  expect(lost).not.toContain("+25,000");
  duel.value = null;
});

it("draws the hands face to face, an empty slot for a hand never thrown, and equal hand keys", async () => {
  duel.value = { ...result(true), shown: { mine: "scissors", theirs: null } };
  const html = await renderToString(createSSRApp(DuelBubble));
  expect(html.match(/class="icon hand mine"/g)).toHaveLength(1);
  expect(html).not.toContain("hand theirs");
  expect(html).toContain('<i class="none"');
  expect(html).not.toContain("—");
  duel.value = { ...result(false), phase: "throw", hand: "paper", shown: { mine: "rock", theirs: "rock" } };
  const throwing = await renderToString(createSSRApp(DuelBubble));
  expect(throwing).toContain("平局");
  expect(throwing.match(/hand-key/g)).toHaveLength(3);
  expect(throwing).toMatch(/class="on ui-btn hand-key" aria-pressed="true" title="布"/);
  expect(throwing).toMatch(/aria-label="布"/);
  expect(throwing.match(/disabled/g)).toHaveLength(2); // the other two hands
  duel.value = null;
});
