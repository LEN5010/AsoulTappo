import { effectScope, ref } from "vue";
import { describe, expect, it } from "vitest";
import type { Pos } from "../stores/desk";
import { centredShift } from "./centredShift";
import { ownBubbles } from "./ownBubbles";

describe("bubbles over the own pet", () => {
  const pet = { w: 268, h: 200 };
  const screen = { w: 1000, h: 800 };

  it("follow the pet while it is dragged and go back to where it stands on release", () => {
    const scope = effectScope();
    const rest: Pos = { x: 400, y: 400 };
    const drag = ref<Pos | null>(null);
    const b = scope.run(() => ownBubbles(() => drag.value ?? rest, () => pet, () => screen))!;
    const duel = b.place({ w: 212, h: 142 });

    expect(b.middle.value).toEqual({ x: 534, w: 1000 });
    expect(duel.value).toEqual({ shift: 0, below: false });

    // Dragged to the left edge: a 240px wide bubble centred on x 60 moves 68px to the right, as it does once let go.
    drag.value = { x: 60 - pet.w / 2, y: 100 };
    expect(b.middle.value).toEqual({ x: 60, w: 1000 });
    expect(centredShift(b.middle.value.x, 240, b.middle.value.w)).toBe(68);
    expect(duel.value).toEqual({ shift: 8 - (60 - 106), below: true });

    drag.value = null;
    expect(b.middle.value.x).toBe(534);
    expect(duel.value).toEqual({ shift: 0, below: false });
    scope.stop();
  });

  it("take a bubble size that changes as it shows", () => {
    const scope = effectScope();
    const width = ref(100);
    const b = scope.run(() => ownBubbles(() => ({ x: -100, y: 400 }), () => pet, () => screen))!;
    const pick = b.place(() => ({ w: width.value, h: 40 }));
    expect(pick.value.shift).toBe(centredShift(-100 + pet.w / 2, 100, 1000));
    width.value = 300;
    expect(pick.value.shift).toBe(centredShift(-100 + pet.w / 2, 300, 1000));
    scope.stop();
  });
});
