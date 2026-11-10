// Telling a click on a pet from a drag that moves it.

/** Pointer travel (px) from the press at which the press becomes a drag. */
export const DRAG_PX = 4;

export const dragged = (dx: number, dy: number): boolean => Math.hypot(dx, dy) >= DRAG_PX;

/** A press that ends where it started (it never became a drag) and was released, not cancelled, is a click. */
export const isTap = (moved: boolean, event: string): boolean => !moved && event === "pointerup";
