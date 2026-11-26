// The overlay window covers the whole work area but must only take the mouse where
// something is drawn. Elements marked with `data-hit` are collected here and sent to
// the Rust side, which lets the cursor fall through everywhere else
// (see src-tauri/src/lib.rs, `spawn_hit_test`). With click-through on nothing takes the mouse but the elements marked
// `data-hit="keep"`: the bubbles with keys (a reminder, an invitation, a todo), which the player still has to answer.
// `data-hit-inset`: CSS px on the left and right of the element where it draws nothing and lets the mouse through.
export interface HitRect { x: number; y: number; w: number; h: number; keep?: true }

export function collectRects(root: ParentNode = document): HitRect[] {
  const out: HitRect[] = [];
  root.querySelectorAll<HTMLElement>("[data-hit]").forEach((el) => {
    const r = el.getBoundingClientRect();
    const inset = Math.max(0, Number(el.dataset.hitInset) || 0);
    const left = r.left + inset;
    const right = r.right - inset;
    if (right - left < 1 || r.height < 1) return;
    const x = Math.floor(left);
    const y = Math.floor(r.top);
    out.push({ x, y, w: Math.ceil(right) - x, h: Math.ceil(r.bottom) - y, ...(el.dataset.hit === "keep" ? { keep: true as const } : {}) });
  });
  return out;
}

export function sameRects(a: HitRect[], b: HitRect[]): boolean {
  return a.length === b.length &&
    a.every((r, i) => r.x === b[i].x && r.y === b[i].y && r.w === b[i].w && r.h === b[i].h && !r.keep === !b[i].keep);
}

/** Whether a hit target is among [nodes] or inside one of them. */
function hasHitNode(nodes: NodeList): boolean {
  for (let i = 0; i < nodes.length; i++) {
    const node = nodes[i];
    if (!(node instanceof Element)) continue;
    if (node.hasAttribute("data-hit") || (node.childElementCount > 0 && node.querySelector("[data-hit]"))) return true;
  }
  return false;
}

/**
 * Observe layout changes and sample only while a hit target is animating.
 * Style and class changes are watched on the hit targets and what holds them only, so the layers drawn inside a
 * target (a pet's paws, moving every frame) cost nothing here. While paused (a pet is dragged, and the native side
 * takes every click meanwhile) nothing is sampled; resuming measures again.
 * Each report carries the page's device pixel ratio: on Windows the webview multiplies the monitor
 * scale by the system text size, so the monitor scale alone misplaces the rectangles.
 */
export function startHitReporter(
  send: (rects: HitRect[], scale: number) => void,
  collect: () => HitRect[] = () => collectRects(),
  intervalMs?: number,
  readScale: () => number = () => globalThis.devicePixelRatio || 1,
): { kick(): void; setPaused(paused: boolean): void; stop(): void } {
  let last: HitRect[] | null = null;
  let lastScale = 0;
  let frame: number | null = null;
  let paused = false;
  let stopped = false;
  /** Hit targets came or went while paused: the observed elements are gathered again on resuming. */
  let stale = false;
  const animating = new Set<Element>();
  const kick = () => {
    if (paused || stopped) return;
    if (frame === null) frame = requestAnimationFrame(report);
  };
  const report = () => {
    frame = null;
    if (paused || stopped) return;
    const rects = collect();
    const scale = readScale();
    if (!last || !sameRects(last, rects) || scale !== lastScale) {
      last = rects;
      lastScale = scale;
      send(rects, scale);
    }
    if (animating.size) kick();
  };
  let resize: ResizeObserver | undefined;
  let structure: MutationObserver | undefined;
  let styles: MutationObserver | undefined;
  const observe = () => {
    resize?.disconnect();
    styles?.disconnect();
    const held = new Set<Element>();
    document.querySelectorAll("[data-hit]").forEach((el) => {
      resize?.observe(el);
      for (let at: Element | null = el; at && !held.has(at); at = at.parentElement) held.add(at);
    });
    for (const el of held) styles?.observe(el, { attributes: true, attributeFilter: ["style", "class"] });
    for (const el of animating) if (!el.isConnected) animating.delete(el);
  };
  const setPaused = (next: boolean) => {
    if (stopped || paused === next) return;
    paused = next;
    if (paused) {
      if (frame !== null) cancelAnimationFrame(frame);
      frame = null;
      return;
    }
    if (stale) {
      stale = false;
      observe();
    }
    kick();
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
    styles = new MutationObserver(kick);
    // Hit targets coming, going, or made and unmade with the attribute.
    structure = new MutationObserver((records) => {
      if (!records.some((r) => r.type === "attributes" || hasHitNode(r.addedNodes) || hasHitNode(r.removedNodes))) return;
      if (paused) {
        stale = true;
        return;
      }
      observe();
      kick();
    });
    structure.observe(document.documentElement, { subtree: true, childList: true, attributes: true, attributeFilter: ["data-hit"] });
    observe();
    window.addEventListener("resize", kick);
    for (const name of ["transitionrun", "transitionend", "transitioncancel", "animationstart", "animationend", "animationcancel"])
      document.addEventListener(name, animation, true);
  }
  report();
  return {
    kick,
    setPaused,
    stop() {
      stopped = true;
      clearInterval(timer);
      resize?.disconnect(); structure?.disconnect(); styles?.disconnect();
      if (frame !== null) cancelAnimationFrame(frame);
      frame = null;
      if (intervalMs === undefined) {
        window.removeEventListener("resize", kick);
        for (const name of ["transitionrun", "transitionend", "transitioncancel", "animationstart", "animationend", "animationcancel"])
          document.removeEventListener(name, animation, true);
      }
    },
  };
}
