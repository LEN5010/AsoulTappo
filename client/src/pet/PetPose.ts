import { reactive } from "vue";
import type { InputEvent } from "../composables/tauri";
import { MouseMotion } from "../MouseMotion";

/**
 * Where a pet's paws are, from the global input events. It counts nothing and reads no other state, so a
 * window that only draws the pet (src/capture.ts) uses it without the player or the room.
 */
export class PetPose {
  readonly pet = reactive({ keyDown: false, left: false, right: false, dx: 0, dy: 0 });
  private keysHeld = 0;
  private motion = new MouseMotion(this.pet);

  /** [sensitivity]: how far the mouse paw follows the cursor; null leaves it where it is. */
  input(e: InputEvent, sensitivity: number | null): void {
    const pet = this.pet;
    switch (e.kind) {
      case "key_down":
        this.keysHeld += 1;
        pet.keyDown = true;
        break;
      case "key_up":
        this.keysHeld = Math.max(0, this.keysHeld - 1);
        pet.keyDown = this.keysHeld > 0;
        break;
      case "mouse_down":
        if (e.button === "left") pet.left = true;
        else if (e.button === "right") pet.right = true;
        break;
      case "mouse_up":
        if (e.button === "left") pet.left = false;
        else if (e.button === "right") pet.right = false;
        break;
      case "mouse_move":
        if (sensitivity !== null) this.motion.move(e.dx, e.dy, sensitivity);
        break;
    }
  }

  /** The mouse paw goes back to rest; keys and buttons stay as they are. */
  stopMouse(): void { this.motion.stop(); }

  stop(): void {
    this.motion.stop();
    this.keysHeld = 0;
    Object.assign(this.pet, { keyDown: false, left: false, right: false, dx: 0, dy: 0 });
  }
}
