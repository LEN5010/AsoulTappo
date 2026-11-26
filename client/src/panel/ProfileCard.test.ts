import { createSSRApp } from "vue";
import { renderToString } from "vue/server-renderer";
import { expect, it } from "vitest";
import ProfileCard from "./ProfileCard.vue";

interface Handlers {
  list: { value: unknown };
  drag: { value: { from: number; to: number } | null };
  pressPin: (e: object, i: number) => void;
  move: (e: object) => void;
  release: (e: object) => Promise<void>;
  openPin: (card: object) => void;
}

/** The own card's handlers with two pinned cards side by side, 60 px wide and 10 apart. */
async function card(reorder: string[][] = [], opened: unknown[] = []) {
  let handlers!: Handlers;
  const emit = (name: string, arg: unknown) => {
    if (name === "reorder") reorder.push(arg as string[]);
    if (name === "open") opened.push(arg);
  };
  await renderToString(createSSRApp({
    setup() {
      handlers = ProfileCard.setup!(
        { editable: true, showcase: [{ id: "a" }, { id: "b" }] } as never,
        { emit, expose() {}, attrs: {}, slots: {} } as never,
      ) as unknown as Handlers;
      return () => null;
    },
  }));
  handlers.list.value = {
    children: [{ offsetLeft: 0, offsetWidth: 60 }, { offsetLeft: 70, offsetWidth: 60 }],
    getBoundingClientRect() {},
  };
  return handlers;
}

const target = { setPointerCapture() {} };

it("drags a pinned card to the next slot while the button is held, and opens nothing on letting go", async () => {
  const reorder: string[][] = [];
  const opened: unknown[] = [];
  const h = await card(reorder, opened);
  h.pressPin({ pointerId: 1, button: 0, buttons: 1, clientX: 30, clientY: 10 }, 0);
  h.move({ pointerId: 1, buttons: 1, clientX: 33, clientY: 10, currentTarget: target });
  expect(h.drag.value).toBeNull();
  h.move({ pointerId: 1, buttons: 1, clientX: 100, clientY: 10, currentTarget: target });
  expect(h.drag.value).toMatchObject({ from: 0, to: 1 });
  await h.release({ pointerId: 1 });
  expect(h.drag.value).toBeNull();
  expect(reorder).toEqual([["b", "a"]]);
  h.openPin({ id: "b" });
  expect(opened).toEqual([]);
});

it("opens a card pressed and let go without moving", async () => {
  const opened: unknown[] = [];
  const h = await card([], opened);
  h.pressPin({ pointerId: 1, button: 0, buttons: 1, clientX: 30, clientY: 10 }, 0);
  h.move({ pointerId: 1, buttons: 1, clientX: 32, clientY: 11, currentTarget: target });
  await h.release({ pointerId: 1 });
  h.openPin({ id: "a" });
  expect(opened).toEqual([{ id: "a" }]);
});

it("forgets a press let go outside the cards: the next hover with no button down drags nothing", async () => {
  const h = await card();
  // Pressed at the card's edge, moved off it by less than 5 px, let go between the cards: the button never hears it.
  h.pressPin({ pointerId: 1, button: 0, buttons: 1, clientX: 59, clientY: 10 }, 0);
  h.move({ pointerId: 1, buttons: 0, clientX: 97, clientY: 10, currentTarget: target });
  expect(h.drag.value).toBeNull();
  // Nor does a later one with the button down again, without a press on a card first.
  h.move({ pointerId: 1, buttons: 1, clientX: 120, clientY: 10, currentTarget: target });
  expect(h.drag.value).toBeNull();
});

it("drops a drag under way whose release was missed, keeping the order", async () => {
  const reorder: string[][] = [];
  const h = await card(reorder);
  h.pressPin({ pointerId: 1, button: 0, buttons: 1, clientX: 30, clientY: 10 }, 0);
  h.move({ pointerId: 1, buttons: 1, clientX: 100, clientY: 10, currentTarget: target });
  expect(h.drag.value).toMatchObject({ from: 0, to: 1 });
  h.move({ pointerId: 1, buttons: 0, clientX: 110, clientY: 10, currentTarget: target });
  expect(h.drag.value).toBeNull();
  await h.release({ pointerId: 1 });
  expect(reorder).toEqual([]);
});
