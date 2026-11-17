import { reactive } from "vue";
import type { InputEvent, MouseButton } from "../composables/tauri";

/**
 * The keys and buttons a room is shown as held: those a hand pressed. A press other software sent (an auto-clicker,
 * a macro; InputEvent.injected, where the system tells) is left out, and so is its release, so the own pet still
 * moves to it on this desk while the partners see only the hand.
 *
 * A release does not say which press it ends. While software-sent keys are held, a key release is taken as one of
 * theirs first: they are let go within moments, and the counts come out even either way.
 */
export class ShownPresses {
  readonly state = reactive({ keyDown: false, left: false, right: false });
  private keys = 0;
  private sentKeys = 0;
  private sentButtons = new Set<MouseButton>();

  input(e: InputEvent): void {
    const state = this.state;
    switch (e.kind) {
      case "key_down":
        if (e.injected) this.sentKeys += 1;
        else this.keys += 1;
        break;
      case "key_up":
        if (this.sentKeys > 0) this.sentKeys -= 1;
        else this.keys = Math.max(0, this.keys - 1);
        break;
      case "mouse_down":
        if (e.injected) this.sentButtons.add(e.button);
        else if (e.button === "left") state.left = true;
        else if (e.button === "right") state.right = true;
        break;
      case "mouse_up":
        if (this.sentButtons.delete(e.button)) break;
        if (e.button === "left") state.left = false;
        else if (e.button === "right") state.right = false;
        break;
    }
    state.keyDown = this.keys > 0;
  }

  stop(): void {
    this.keys = this.sentKeys = 0;
    this.sentButtons.clear();
    Object.assign(this.state, { keyDown: false, left: false, right: false });
  }
}
