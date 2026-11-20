import { expect, it, vi } from "vitest";
import { nextTick, ref } from "vue";
import { INVITE_SETTLE_MS, inviteKeys, useInviteKeys } from "./inviteKeys";

function clocked() {
  let ms = 1000;
  const keys = inviteKeys(() => ms);
  return { keys, pass: (n: number) => { ms += n; } };
}

it("answers the invite on screen when the key went down on it", () => {
  const { keys, pass } = clocked();
  keys.show("a");
  pass(INVITE_SETTLE_MS);
  keys.press();
  expect(keys.pick(true, true)).toBe("a");
  keys.press();
  expect(keys.pick(false, true)).toBe("a");
  expect(keys.pick(true, false)).toBe("a"); // by the keyboard: no key went down
});

it("drops a click whose key went down on an invite that another took the place of", () => {
  const { keys, pass } = clocked();
  keys.show("a");
  pass(INVITE_SETTLE_MS);
  keys.press();
  keys.show("b");
  pass(INVITE_SETTLE_MS);
  expect(keys.pick(true, true)).toBeNull();
  keys.press();
  keys.show(undefined);
  keys.show("b");
  pass(INVITE_SETTLE_MS);
  expect(keys.pick(false, true)).toBeNull(); // turning down an unseen table of the queue holds the save back too
});

it("answers a click whose key going down was not seen (a window in the background may swallow it)", () => {
  const { keys, pass } = clocked();
  keys.show("a");
  pass(INVITE_SETTLE_MS - 1);
  expect(keys.pick(true, true)).toBeNull(); // still the moment after it came up
  pass(1);
  expect(keys.pick(true, true)).toBe("a");
  // A press dropped with the invite it was on leaves the next click free.
  keys.press();
  keys.show("b");
  expect(keys.pick(false, true)).toBeNull();
  expect(keys.pick(false, true)).toBe("b");
});

it("takes no accept for a moment after the invite on screen changed, one coming up from none included", () => {
  const { keys, pass } = clocked();
  keys.show("a");
  keys.press();
  pass(INVITE_SETTLE_MS - 1);
  expect(keys.pick(true, true)).toBeNull();
  expect(keys.pick(true, false)).toBeNull();
  keys.press();
  expect(keys.pick(false, true)).toBe("a");
  keys.show("b");
  pass(INVITE_SETTLE_MS - 1);
  expect(keys.pick(true, false)).toBeNull();
  pass(1);
  keys.press();
  expect(keys.pick(true, true)).toBe("b");
  keys.show(undefined);
  expect(keys.pick(false, false)).toBeNull();
});

it("follows the invite a component shows", async () => {
  vi.useFakeTimers();
  try {
    const shown = ref<string | undefined>("a");
    const answer = vi.fn();
    const keys = useInviteKeys(() => shown.value, answer);
    vi.advanceTimersByTime(INVITE_SETTLE_MS);
    keys.press();
    shown.value = "b";
    await nextTick();
    vi.advanceTimersByTime(INVITE_SETTLE_MS);
    keys.answer(true, { detail: 1 } as MouseEvent);
    expect(answer).not.toHaveBeenCalled();
    keys.press();
    keys.answer(true, { detail: 1 } as MouseEvent);
    expect(answer).toHaveBeenCalledWith(true, "b");
  } finally {
    vi.useRealTimers();
  }
});
