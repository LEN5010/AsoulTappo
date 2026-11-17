import { reactive } from "vue";
import type { InputEvent } from "../composables/tauri";

/**
 * The keys and buttons a room is shown as held: those a hand pressed. A press other software sent (an auto-clicker,
 * a macro; InputEvent.injected, where the system tells) is left out, and so is its release, so the own pet still
 * moves to it on this desk while the partners see only the hand.
 */
export class ShownPresses {
  readonly state = reactive({ keyDown: false, left: false, right: false });
  private keys = 0;

  input(e: InputEvent): void {
    if ("injected" in e && e.injected) return;
    const state = this.state;
    switch (e.kind) {
      case "key_down":
        this.keys += 1;
        break;
      case "key_up":
        this.keys = Math.max(0, this.keys - 1);
        break;
      case "mouse_down":
        if (e.button === "left") state.left = true;
        else if (e.button === "right") state.right = true;
        break;
      case "mouse_up":
        if (e.button === "left") state.left = false;
        else if (e.button === "right") state.right = false;
        break;
    }
    state.keyDown = this.keys > 0;
  }

  stop(): void {
    this.keys = 0;
    Object.assign(this.state, { keyDown: false, left: false, right: false });
  }
}
