// A press on a button that never became its click: [write] gets what was under the pointer when it came up, whether
// the button was still in the page and the page's own state ([state]). Clicks the system never handed to the page leave
// no trace here.

/** How long after the release a click still counts as the press's. */
const LOST_MS = 600;

/** A short name for [el]: its tag and first class. */
function describe(el: Element | null): string {
  if (!el) return "nothing";
  const cls = typeof el.className === "string" ? el.className.trim().split(/\s+/)[0] : "";
  return cls ? `${el.tagName.toLowerCase()}.${cls}` : el.tagName.toLowerCase();
}

export function watchLostClicks(write: (msg: string) => void, state: () => string = () => ""): () => void {
  let pressed: { button: HTMLButtonElement; timer?: ReturnType<typeof setTimeout> } | null = null;
  const forget = () => {
    clearTimeout(pressed?.timer);
    pressed = null;
  };
  const down = (e: PointerEvent) => {
    if (e.button !== 0) return;
    forget();
    const button = e.target instanceof Element ? e.target.closest("button") : null;
    if (button && !button.disabled) pressed = { button };
  };
  const up = (e: PointerEvent) => {
    const p = pressed;
    if (!p || e.button !== 0) return;
    const under = document.elementFromPoint(e.clientX, e.clientY);
    p.timer = setTimeout(() => {
      if (pressed !== p) return;
      pressed = null;
      const label = (p.button.getAttribute("aria-label") || p.button.textContent || "").trim().slice(0, 16);
      write(`click lost on ${describe(p.button)} (${label}), up on ${describe(under)}, `
        + `button ${p.button.isConnected ? "in page" : "gone"}, hidden ${document.hidden}${state()}`);
    }, LOST_MS);
  };
  const click = (e: MouseEvent) => {
    if (pressed && e.target instanceof Node && pressed.button.contains(e.target)) forget();
  };
  window.addEventListener("pointerdown", down, true);
  window.addEventListener("pointerup", up, true);
  window.addEventListener("click", click, true);
  return () => {
    forget();
    window.removeEventListener("pointerdown", down, true);
    window.removeEventListener("pointerup", up, true);
    window.removeEventListener("click", click, true);
  };
}
