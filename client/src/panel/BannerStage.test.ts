import { afterEach, expect, it, vi } from "vitest";
import { createSSRApp, type Ref } from "vue";
import { renderToString } from "vue/server-renderer";
import type { Item } from "../items";
import { manifest } from "../manifest";
import { setEconomy, type Banner } from "../stores/economy";
import { exampleEconomy } from "../test/economy";

// The stage's lifecycle is never run: there is no DOM here to mount it in.
vi.mock("vue", async (original) => ({
  ...(await original<typeof import("vue")>()),
  onMounted: () => {},
  onActivated: () => {},
  onDeactivated: () => {},
  onBeforeUnmount: () => {},
}));

afterEach(() => {
  vi.unstubAllGlobals();
  setEconomy(exampleEconomy);
});

interface Stage { dealt: Ref<Item[]>; dealing: Ref<boolean>; strip: Ref<{ item: Item }[]> }

async function stage(banner: Banner): Promise<Stage> {
  vi.stubGlobal("window", globalThis);
  vi.stubGlobal("requestAnimationFrame", () => 0);
  vi.stubGlobal("cancelAnimationFrame", () => {});
  vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} });
  const { default: BannerStage } = await import("./BannerStage.vue");
  let bindings!: Stage;
  await renderToString(createSSRApp({
    setup() {
      bindings = BannerStage.setup!({ banner, busy: false } as never, { emit() {}, expose() {}, attrs: {}, slots: {} } as never) as never;
      return () => null;
    },
  }));
  return bindings;
}

const cards = (series: (id: string) => boolean) => manifest.cards.filter((c) => series(c.series)).map((c) => `card:${c.id}`);
const WARDROBE = cards((s) => s.startsWith("wardrobe-"));
const NAODONG = cards((s) => s === "naodong");
/** A pool of skins that raises the limited tier's odds, as 形态共鸣 does. */
const FORMS: Banner = { id: "forms", name: "形态共鸣", start: 0, end: 4e9, items: ["char:嘉然然龙"], rates: { limited: 6 }, share: 50 };

it("deals the limited cards no limited pool keeps to itself, a member at a time", async () => {
  // A pool featuring the 脑洞波 cards is named: they are held until it ends, even before it starts.
  setEconomy({ ...exampleEconomy, resonance: { ...exampleEconomy.resonance, banners: [FORMS], held: [...NAODONG, "char:嘉然然龙"] } });
  const s = await stage(FORMS);
  expect(s.dealing.value).toBe(true);
  expect(s.dealt.value.map((i) => i.id).sort()).toEqual([...WARDROBE].sort());
  expect(s.strip.value.map((c) => c.item.id)).toEqual(s.dealt.value.map((i) => i.id));
  const members = s.dealt.value.slice(0, 3).map((i) => i.characters.join());
  expect(new Set(members).size).toBe(3);
  // Once that pool has ended they are in the tier with the 衣橱 cards.
  setEconomy({ ...exampleEconomy, resonance: { ...exampleEconomy.resonance, banners: [FORMS], held: ["char:嘉然然龙"] } });
  expect(s.dealt.value.map((i) => i.id).sort()).toEqual([...WARDROBE, ...NAODONG].sort());
});

it("deals none of a pool's own featured limited cards, and shows them on the pearl card when it has nothing else to deal", async () => {
  const naodong: Banner = { id: "naodong", name: "脑洞共鸣", start: 0, end: 4e9, items: NAODONG, rate: 1, pity: 100, rates: { limited: 2 } };
  setEconomy({ ...exampleEconomy, resonance: { ...exampleEconomy.resonance, banners: [naodong], held: NAODONG } });
  const s = await stage(naodong);
  expect(s.dealt.value.map((i) => i.id).sort()).toEqual([...WARDROBE].sort());
  // With every limited card held there is nothing to deal: no hand, no strip.
  setEconomy({
    ...exampleEconomy, resonance: { ...exampleEconomy.resonance, banners: [naodong], held: [...NAODONG, ...WARDROBE] },
  });
  expect(s.dealt.value).toEqual([]);
  expect(s.dealing.value).toBe(false);
  expect(s.strip.value).toEqual([]);
});
