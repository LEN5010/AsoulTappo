import { describe, expect, it } from "vitest";
import { ShownPresses } from "./ShownPresses";

describe("what a room is shown of the own presses", () => {
  it("shows a hand's keys and buttons as the pet's own pose does", () => {
    const shown = new ShownPresses();
    shown.input({ kind: "key_down" });
    shown.input({ kind: "mouse_down", button: "left", injected: false });
    expect(shown.state).toEqual({ keyDown: true, left: true, right: false });
    shown.input({ kind: "key_up" });
    shown.input({ kind: "mouse_up", button: "left" });
    expect(shown.state).toEqual({ keyDown: false, left: false, right: false });
  });

  it("leaves out a press other software sent, and its release", () => {
    const shown = new ShownPresses();
    for (let i = 0; i < 20; i++) {
      shown.input({ kind: "mouse_down", button: "left", injected: true });
      expect(shown.state.left).toBe(false);
      shown.input({ kind: "mouse_up", button: "left" });
    }
    shown.input({ kind: "key_down", injected: true });
    expect(shown.state.keyDown).toBe(false);
    shown.input({ kind: "key_up" });
    expect(shown.state).toEqual({ keyDown: false, left: false, right: false });
  });

  it("keeps showing the hand while an auto-clicker runs beside it", () => {
    const shown = new ShownPresses();
    shown.input({ kind: "key_down", injected: false });
    shown.input({ kind: "key_down", injected: true });
    expect(shown.state.keyDown).toBe(true);
    // One release for each press, in whichever order: the hand's key stays down until both are up.
    shown.input({ kind: "key_up" });
    expect(shown.state.keyDown).toBe(true);
    shown.input({ kind: "key_up" });
    expect(shown.state.keyDown).toBe(false);
    // A hand's click on the right button while the left one is being clicked for it.
    shown.input({ kind: "mouse_down", button: "left", injected: true });
    shown.input({ kind: "mouse_down", button: "right", injected: false });
    expect(shown.state).toEqual({ keyDown: false, left: false, right: true });
    shown.input({ kind: "mouse_up", button: "left" });
    shown.input({ kind: "mouse_up", button: "right" });
    expect(shown.state).toEqual({ keyDown: false, left: false, right: false });
  });

  it("forgets everything on a stop", () => {
    const shown = new ShownPresses();
    shown.input({ kind: "key_down" });
    shown.input({ kind: "key_down", injected: true });
    shown.stop();
    expect(shown.state.keyDown).toBe(false);
    shown.input({ kind: "key_up" });
    expect(shown.state.keyDown).toBe(false);
  });
});
