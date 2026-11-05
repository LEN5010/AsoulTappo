// The overlay window covers the whole work area but must only take the mouse where
// something is drawn. Elements marked with `data-hit` are collected here and sent to
// the Rust side, which lets the cursor fall through everywhere else
// (see src-tauri/src/lib.rs, `spawn_hit_test`).
export interface HitRect { x: number; y: number; w: number; h: number }

export function collectRects(root: ParentNode = document): HitRect[] {
  const out: HitRect[] = [];
  root.querySelectorAll<HTMLElement>("[data-hit]").forEach((el) => {
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) return;
    const x = Math.floor(r.left);
    const y = Math.floor(r.top);
    out.push({ x, y, w: Math.ceil(r.right) - x, h: Math.ceil(r.bottom) - y });
  });
  return out;
}

export function sameRects(a: HitRect[], b: HitRect[]): boolean {
  return a.length === b.length && a.every((r, i) => r.x === b[i].x && r.y === b[i].y && r.w === b[i].w && r.h === b[i].h);
}

/** Observe layout changes and sample only while a hit target is animating. */
export function startHitReporter(
  send: (rects: HitRect[]) => void,
  collect: () => HitRect[] = () => collectRects(),
  intervalMs?: number,
): { kick(): void; stop(): void } {
  let last: HitRect[] | null = null;
  let frame: number | null = null;
  const animating = new Set<Element>();
  const kick = () => { if (frame === null) frame = requestAnimationFrame(report); };
  const report = () => {
    frame = null;
    const rects = collect();
    if (!last || !sameRects(last, rects)) { last = rects; send(rects); }
    if (animating.size) kick();
  };
  let resize: ResizeObserver | undefined;
  let mutations: MutationObserver | undefined;
  const observe = () => {
    resize?.disconnect();
    document.querySelectorAll("[data-hit]").forEach((el) => resize?.observe(el));
    for (const el of animating) if (!el.isConnected) animating.delete(el);
  };
  const animation = (event: Event) => {
    const el = event.target as Element;
    if (!el.matches("[data-hit]")) return;
    if (event.type === "transitionrun" || event.type === "animationstart") animating.add(el);
    else animating.delete(el);
    kick();
  };
  // Explicit intervals remain available for callers with an external layout source.
  const timer = intervalMs === undefined ? undefined : setInterval(report, intervalMs);
  if (intervalMs === undefined) {
    resize = new ResizeObserver(kick);
    mutations = new MutationObserver((records) => {
      let structure = false;
      let layout = false;
      for (const record of records) {
        if (record.type === "childList") {
          if ([...record.addedNodes, ...record.removedNodes].some((node) => node instanceof Element &&
            (node.matches("[data-hit]") || node.querySelector("[data-hit]")))) structure = true;
        } else if (record.target instanceof Element &&
          (record.target.matches("[data-hit]") || record.target.querySelector("[data-hit]"))) layout = true;
      }
      if (structure) observe();
      if (structure || layout) kick();
    });
    mutations.observe(document.documentElement, { subtree: true, childList: true, attributes: true,
      attributeFilter: ["style", "class", "data-hit"] });
    observe();
    window.addEventListener("resize", kick);
    for (const name of ["transitionrun", "transitionend", "transitioncancel", "animationstart", "animationend", "animationcancel"])
      document.addEventListener(name, animation, true);
  }
  report();
  return {
    kick,
    stop() {
      clearInterval(timer);
      resize?.disconnect(); mutations?.disconnect();
      if (frame !== null) cancelAnimationFrame(frame);
      if (intervalMs === undefined) {
        window.removeEventListener("resize", kick);
        for (const name of ["transitionrun", "transitionend", "transitioncancel", "animationstart", "animationend", "animationcancel"])
          document.removeEventListener(name, animation, true);
      }
    },
  };
}
