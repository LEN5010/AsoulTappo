import { effectScope, nextTick, ref } from "vue";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type Entry = { target: object; isIntersecting: boolean };
let observers: FakeObserver[] = [];
class FakeObserver {
  targets = new Set<object>();
  constructor(public cb: (entries: Entry[]) => void) { observers.push(this); }
  observe(el: object) { this.targets.add(el); }
  unobserve(el: object) { this.targets.delete(el); }
  disconnect() { this.targets.clear(); }
  tell(el: object, isIntersecting: boolean) { this.cb([{ target: el, isIntersecting }]); }
}

beforeEach(() => {
  vi.resetModules();
  observers = [];
});
afterEach(() => vi.unstubAllGlobals());

describe("useInView", () => {
  it("follows each element through one shared observer while it is watched", async () => {
    vi.stubGlobal("IntersectionObserver", FakeObserver);
    const { useInView } = await import("./inView");
    const scope = effectScope();
    const a = ref<object | undefined>({});
    const b = ref<object | undefined>({});
    const watching = ref(true);
    const [inA, inB] = scope.run(() => [useInView(a, () => watching.value), useInView(b, () => true)])!;
    await nextTick();
    expect(observers).toHaveLength(1);
    const io = observers[0]!;
    expect(io.targets.size).toBe(2);
    // Nothing plays before the observer has told where the element is.
    expect(inA.value).toBe(false);
    io.tell(a.value!, true);
    expect(inA.value).toBe(true);
    expect(inB.value).toBe(false);
    io.tell(a.value!, false);
    io.tell(b.value!, true);
    expect([inA.value, inB.value]).toEqual([false, true]);

    // No longer watched: not observed, and off.
    io.tell(a.value!, true);
    watching.value = false;
    await nextTick();
    expect(io.targets.has(a.value!)).toBe(false);
    expect(inA.value).toBe(false);

    // A new element is observed in place of the old one.
    const old = b.value!;
    b.value = {};
    await nextTick();
    expect(io.targets.has(old)).toBe(false);
    expect(io.targets.has(b.value)).toBe(true);
    expect(inB.value).toBe(false);
    io.tell(old, true);
    expect(inB.value).toBe(false);

    scope.stop();
    expect(io.targets.size).toBe(0);
  });

  it("counts everything as in view where there is no IntersectionObserver", async () => {
    vi.stubGlobal("IntersectionObserver", undefined);
    const { useInView } = await import("./inView");
    const scope = effectScope();
    const inView = scope.run(() => useInView(ref({}), () => true))!;
    await nextTick();
    expect(inView.value).toBe(true);
    scope.stop();
  });
});
