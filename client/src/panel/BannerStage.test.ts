import { afterEach, expect, it, vi } from "vitest";
import { createSSRApp, type Ref } from "vue";
import { renderToString } from "vue/server-renderer";
import { characters } from "../characters";
import { manifest } from "../manifest";
import { setEconomy, type Banner } from "../stores/economy";
import { reducedMotion } from "../stores/theme";
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

interface Stage {
  raised: Ref<boolean>; showcased: Ref<boolean>; soleShow: Ref<boolean>; posterArt: Ref<string>; washArt: Ref<string>; titleArt: Ref<string>;
  pvArt: Ref<string>; pvOn: Ref<boolean>; pvEnd: () => void; peek: Ref<unknown>;
  memories: Ref<{ kind: string; src: string }[]>;
}

async function stage(banner: Banner): Promise<Stage> {
  setEconomy({ ...exampleEconomy, resonance: { ...exampleEconomy.resonance, banners: [banner], held: banner.items } });
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

const pool = (id: string, item: string, rates: Banner["rates"]): Banner =>
  ({ id, name: id, start: 0, end: 4e9, items: [item], rates, share: 50 });

it("spreads the official poster of the skin on show over the left, and sits the skin on the paper", async () => {
  const s = await stage(pool("heart-trail", "char:心宜2026生日", { skin: 0.3 }));
  expect(s.raised.value).toBe(false);
  expect(s.showcased.value).toBe(true);
  expect(s.posterArt.value).toBe(characters["心宜2026生日"]!.poster);
  // With a single item the paper's middle shows it: no standee repeats it, and it does not peek over the paper.
  expect(s.soleShow.value).toBe(true);
  expect(s.peek.value).toBe(null);
  const card = await stage({ ...pool("birthday", "char:心宜2025生日", { skin: 0.3 }), name: "生日" });
  expect(card.peek.value).not.toBe(null);
});

it("plays the PV of the skin on show where the poster spreads, until it ends", async () => {
  const s = await stage(pool("heart-trail", "char:心宜2026生日", { skin: 0.3 }));
  expect(s.pvArt.value).toBe(characters["心宜2026生日"]!.pv);
  expect(s.pvOn.value).toBe(true);
  // The clip ending, failing or stalling brings the poster in.
  s.pvEnd();
  expect(s.pvOn.value).toBe(false);
  // Without a clip, or with motion reduced, the poster is all there is.
  const birthday = await stage(pool("birthday", "char:心宜2025生日", { skin: 0.3 }));
  expect(birthday.pvArt.value).toBe("");
  expect(birthday.pvOn.value).toBe(false);
  reducedMotion.value = true;
  try {
    const calm = await stage(pool("heart-trail", "char:心宜2026生日", { skin: 0.3 }));
    expect(calm.pvOn.value).toBe(false);
  } finally {
    reducedMotion.value = false;
  }
});

it("names the pool with the poster's title lettering only where the lettering reads the pool's name", async () => {
  const lettering = characters["心宜2026生日"]!.posterTitle!.src;
  const named = await stage({ ...pool("heart-trail", "char:心宜2026生日", { skin: 0.3 }), name: "心之轨迹" });
  expect(named.titleArt.value).toBe(lettering);
  const other = await stage({ ...pool("rerun", "char:心宜2026生日", { skin: 0.3 }), name: "复刻共鸣" });
  expect(other.titleArt.value).toBe("");
  const plain = await stage({ ...pool("birthday", "char:心宜2025生日", { skin: 0.3 }), name: "心之轨迹" });
  expect(plain.titleArt.value).toBe("");
  // Its pale lines are drawn for the poster: where the poster does not spread, the name is set in type.
  const dealt = await stage({ ...pool("heart-dealt", "char:心宜2026生日", { limited: 6 }), name: "心之轨迹" });
  expect(dealt.showcased.value).toBe(false);
  expect(dealt.titleArt.value).toBe("");
});

it("lays the member's cards and emotes out as a scrapbook beside the poster, and nowhere else", async () => {
  const s = await stage(pool("heart-trail", "char:心宜2026生日", { skin: 0.3 }));
  const photos = s.memories.value.filter((m) => m.kind === "photo");
  const stickers = s.memories.value.filter((m) => m.kind === "sticker");
  const cards = manifest.cards.filter((c) => c.characters.includes("心宜"));
  const emotes = manifest.emoteSets.filter((set) => set.character === "心宜").flatMap((set) => set.emotes);
  expect(photos).toHaveLength(Math.min(6, cards.length));
  expect(stickers).toHaveLength(Math.min(6, emotes.length));
  // Her own cards come first.
  const own = cards.filter((c) => c.characters.length === 1).map((c) => c.id);
  expect(own.length).toBeGreaterThan(0);
  expect(photos.slice(0, own.length).every((p) => own.some((id) => p.src.includes(id)))).toBe(true);
  const birthday = await stage(pool("birthday", "char:心宜2025生日", { skin: 0.3 }));
  expect(birthday.memories.value).toEqual([]);
  const forms = await stage(pool("forms", "char:嘉然然龙", { limited: 6 }));
  expect(forms.memories.value).toEqual([]);
});

it("keeps the pearl card and its wash for a skin without a poster", async () => {
  const birthday = await stage(pool("birthday", "char:心宜2025生日", { skin: 0.3 }));
  expect(birthday.posterArt.value).toBe("");
  expect(birthday.washArt.value).toBe(characters["心宜2025生日"]!.bgSmall);
  expect(birthday.showcased.value).toBe(false);
  expect(birthday.soleShow.value).toBe(false);
  // A pool that raises the limited tier deals its cards instead of the pearl card.
  const forms = await stage(pool("forms", "char:嘉然然龙", { limited: 6 }));
  expect(forms.raised.value).toBe(true);
  expect(forms.posterArt.value).toBe("");
  expect(forms.washArt.value).toBe(characters["嘉然然龙"]!.bgSmall);
  expect(forms.showcased.value).toBe(false);
});
