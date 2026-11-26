// A pet's paws drawn straight onto its layers, without a render: another member's pet from the room's updates, the
// own pet from the input hook. What it sets is what PetView's template sets for the same pose given as props.
import { PET_BASE } from "../characters";

export interface PawPose { dx: number; dy: number; keyDown: boolean; left: boolean; right: boolean }

/**
 * The paw layers of the pet drawn in [el] at [scale]; the returned function puts them in a pose, the keyboard paw down
 * while [pressed]. The layers are looked up once: bind again when the pet is drawn anew.
 */
export function pawPainter(el: HTMLElement, scale: number): (pose: PawPose, pressed: boolean) => void {
  const mouse = [...el.querySelectorAll<HTMLElement>(".mouse")];
  const keyboard = el.querySelector<HTMLElement>(".kb");
  const left = el.querySelector<HTMLElement>(".click-left");
  const right = el.querySelector<HTMLElement>(".click-right");
  return (pose, pressed) => {
    const at = `translate(${pose.dx * scale}px, ${pose.dy * scale}px)`;
    for (const layer of mouse) layer.style.transform = at;
    if (keyboard) {
      keyboard.style.transform = `translateY(${(pressed ? PET_BASE.keyboard.pressOffset : 0) * scale}px)`;
      // The quick way down, the springy way back up (.kb.down in PetView).
      keyboard.classList.toggle("down", pressed);
    }
    // Not drawn at all while the button is up: a masked layer that travels with the mouse costs a frame each step.
    if (left) left.style.display = pose.left ? "block" : "none";
    if (right) right.style.display = pose.right ? "block" : "none";
  };
}
