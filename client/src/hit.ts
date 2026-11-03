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

/**
 * Report hit rectangles whenever they change: on `kick()` (next frame) and as a fallback
 * every `intervalMs` (for animations and late layout).
 */
export function startHitReporter(
  send: (rects: HitRect[]) => void,
  collect: () => HitRect[] = () => collectRects(),
  intervalMs = 200,
): { kick(): void; stop(): void } {
  let last: HitRect[] | null = null;
  let frame: number | null = null;
  const report = () => {
    frame = null;
    const rects = collect();
    if (last && sameRects(last, rects)) return;
    last = rects;
    send(rects);
  };
  const timer = setInterval(report, intervalMs);
  report();
  return {
    kick() {
      if (frame === null) frame = requestAnimationFrame(report);
    },
    stop() {
      clearInterval(timer);
      if (frame !== null) cancelAnimationFrame(frame);
    },
  };
}
