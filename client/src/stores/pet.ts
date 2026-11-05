// State of the local pet, driven by the global input hook. Shared by the desk pet and the
// live preview in the backpack page.
import { reactive, watch } from "vue";
import type { InputEvent } from "../composables/tauri";
import { MouseMotion } from "../MouseMotion";
import { bumpCounter } from "./counter";
import { countInput } from "./player";
import { inRoom, registerTap, syncMotion, youId } from "./room";
import { settings } from "./settings";

export const pet = reactive({ keyDown: false, left: false, right: false, dx: 0, dy: 0 });
let keysHeld = 0;
const motion = new MouseMotion(pet);

watch(() => [pet.dx, pet.dy, pet.keyDown, pet.left, pet.right, inRoom.value, youId.value],
  () => syncMotion({ ...pet }), { flush: "sync" });

function tap(): void {
  registerTap();
  countInput();
  bumpCounter();
}

export function onInput(e: InputEvent, count = true): void {
  switch (e.kind) {
    case "key_down":
      keysHeld += 1;
      pet.keyDown = true;
      if (count) tap();
      break;
    case "key_up":
      keysHeld = Math.max(0, keysHeld - 1);
      pet.keyDown = keysHeld > 0;
      break;
    case "mouse_down":
      if (e.button === "left") pet.left = true;
      else if (e.button === "right") pet.right = true;
      if (count) tap();
      break;
    case "mouse_up":
      if (e.button === "left") pet.left = false;
      else if (e.button === "right") pet.right = false;
      break;
    case "mouse_move":
      if (!settings.mouseFollow) break;
      motion.move(e.dx, e.dy, settings.mouseSensitivity);
      break;
  }
}

export function stopPet(): void {
  motion.stop();
}

watch(() => settings.mouseFollow, (enabled) => { if (!enabled) motion.stop(); }, { flush: "sync" });
