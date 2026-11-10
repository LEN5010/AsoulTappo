import { describe, expect, it } from "vitest";
import { PetPose } from "./PetPose";

describe("PetPose", () => {
  it("holds the keyboard paw down until every key is up and tracks each mouse button", () => {
    const pose = new PetPose();
    pose.input({ kind: "key_down" }, null);
    pose.input({ kind: "key_down" }, null);
    pose.input({ kind: "key_up" }, null);
    expect(pose.pet.keyDown).toBe(true);
    pose.input({ kind: "key_up" }, null);
    pose.input({ kind: "key_up" }, null);
    expect(pose.pet.keyDown).toBe(false);
    pose.input({ kind: "mouse_down", button: "right" }, null);
    pose.input({ kind: "mouse_down", button: "middle" }, null);
    expect(pose.pet).toMatchObject({ left: false, right: true });
    pose.stop();
    expect(pose.pet).toEqual({ keyDown: false, left: false, right: false, dx: 0, dy: 0 });
  });
  it("leaves the mouse paw alone without a sensitivity", () => {
    const pose = new PetPose();
    // Would schedule a frame, which this environment does not have.
    expect(() => pose.input({ kind: "mouse_move", dx: 5, dy: 5 }, null)).not.toThrow();
    expect(pose.pet).toMatchObject({ dx: 0, dy: 0 });
  });
});
