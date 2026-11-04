// Keyboard focus for overlays: keeps Tab inside `root` and remembers where focus came from.
const FOCUSABLE = "button:not(:disabled), input:not(:disabled), select:not(:disabled), a[href], [tabindex]:not([tabindex='-1'])";

export function trapTab(root: HTMLElement, e: KeyboardEvent): void {
  const items = [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => el.offsetParent !== null);
  if (!items.length) {
    e.preventDefault();
    root.focus();
    return;
  }
  const first = items[0]!;
  const last = items[items.length - 1]!;
  const active = document.activeElement;
  if (e.shiftKey && (active === first || active === root)) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && active === last) {
    e.preventDefault();
    first.focus();
  } else if (!root.contains(active)) {
    e.preventDefault();
    first.focus();
  }
}

/** Moves focus into `root`; the returned function hands it back. */
export function takeFocus(root: HTMLElement | undefined): () => void {
  const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  root?.focus({ preventScroll: true });
  return () => {
    if (previous?.isConnected) previous.focus({ preventScroll: true });
  };
}

/** Arrow keys for a row of single-select buttons: moves focus and picks the option. */
export function arrowSelect(e: KeyboardEvent, root: HTMLElement | undefined): void {
  const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
  if (!step || !root) return;
  const items = [...root.querySelectorAll<HTMLButtonElement>("button:not(:disabled)")];
  const at = items.indexOf(document.activeElement as HTMLButtonElement);
  if (at < 0) return;
  e.preventDefault();
  const next = items[(at + step + items.length) % items.length]!;
  next.focus();
  next.click();
}
