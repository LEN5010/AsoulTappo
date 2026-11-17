import { reactive } from "vue";
import type { InputEvent } from "../composables/tauri";
import { MouseMotion } from "../MouseMotion";

/**
 * Paw pose and press edges from global input. The capture window can use them without the player or the room.
 */
export class PetPose {
  readonly pet = reactive({ keyDown: false, left: false, right: false, dx: 0, dy: 0, formPress: 0 });
  private keysHeld = 0;
  private motion = new MouseMotion(this.pet);

  /** [sensitivity]: how far the mouse paw follows the cursor; null leaves it where it is. */
  input(e: InputEvent, sensitivity: number | null): void {
    const pet = this.pet;
    switch (e.kind) {
      case "key_down":
        this.keysHeld += 1;
        pet.keyDown = true;
        pet.formPress += 1;
        break;
      case "key_up":
        this.keysHeld = Math.max(0, this.keysHeld - 1);
        pet.keyDown = this.keysHeld > 0;
        break;
      case "mouse_down":
        if (e.button === "left") pet.left = true;
        else if (e.button === "right") pet.right = true;
        pet.formPress += 1;
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
