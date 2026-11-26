import { effectScope, nextTick, ref } from "vue";
import { describe, expect, it } from "vitest";
import { bubblePlacement } from "./duelPick";
import { centredShift, useCentredShift, type PetMiddle } from "./centredShift";

describe("centredShift", () => {
  it("leaves a bubble that fits centred and moves one at a side edge just inside the screen", () => {
    expect(centredShift(500, 240, 1000)).toBe(0);
    // centred it would start at 60 - 120 = -60: moved right to start at 8
    expect(centredShift(60, 240, 1000)).toBe(68);
    // centred it would end at 980 + 120 = 1100: moved left to end at 992
    expect(980 + 120 + centredShift(980, 240, 1000)).toBe(992);
  });

  it("keeps the left edge of a bubble wider than the screen on it", () => {
    expect(300 - 200 + centredShift(300, 400, 300)).toBe(8);
  });

  it("is the shift the fixed-width bubbles get", () => {
    const pet = { w: 268, h: 200 };
    for (const x of [-14, 0, 300, 1453]) {
      const middle = x + pet.w / 2;
      expect(centredShift(middle, 320, 1707)).toBe(bubblePlacement({ x, y: 400 }, pet, { w: 320, h: 40 }, { w: 1707, h: 1067 }).shift);
    }
  });
});

describe("useCentredShift", () => {
  const run = (middle: () => PetMiddle | undefined) => {
    const scope = effectScope();
    const el = ref<HTMLElement | null>(null);
    const shift = scope.run(() => useCentredShift(el, middle))!;
    return { scope, el, shift, show: (width: number) => { el.value = { offsetWidth: width } as HTMLElement; } };
  };

  it("measures the bubble once it shows and follows the pet along the edge", async () => {
    const middle = ref<PetMiddle>({ x: 1600, w: 1707 });
    const { scope, shift, show, el } = run(() => middle.value);
    expect(shift.value).toBe(0);
    show(240);
    await nextTick();
    expect(shift.value).toBe(1707 - 8 - 240 - (1600 - 120));
    middle.value = { x: 800, w: 1707 };
    expect(shift.value).toBe(0);
    middle.value = { x: 70, w: 1707 };
    expect(shift.value).toBe(8 - (70 - 120));
    el.value = null;
    await nextTick();
    expect(shift.value).toBe(0);
    scope.stop();
  });

  it("stays centred without the pet's place", async () => {
    const { scope, shift, show } = run(() => undefined);
    show(240);
    await nextTick();
    expect(shift.value).toBe(0);
    scope.stop();
  });
});
