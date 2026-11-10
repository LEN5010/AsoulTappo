// State of the local pet, driven by the global input hook. Shared by the desk pet and the
// live preview in the backpack page.
import { ref, watch } from "vue";
import type { InputEvent } from "../composables/tauri";
import { PetPose } from "../pet/PetPose";
import { TapGuard } from "../pet/TapGuard";
import { bumpCounter } from "./counter";
import { countInput, reportCooldown, status } from "./player";
import { inRoom, registerTap, syncMotion, youId } from "./room";
import { settings } from "./settings";
import { popShards } from "./shardPop";
import { noteActivity, windowVisible } from "./activity";

const pose = new PetPose();
export const pet = pose.pet;

watch(() => [pet.dx, pet.dy, pet.keyDown, pet.left, pet.right, inRoom.value, youId.value],
  () => syncMotion({ ...pet }), { flush: "sync" });

const guard = new TapGuard();
/** Presses this page received and what became of them, for the debug build's log (src/debugLog.ts). */
export const tapStats = { keys: 0, mouse: 0, counted: 0, blocked: 0 };
/** When inputs count again after going faster than a hand; in the past while they count. */
export const tapCooldown = ref(0);
// A cooldown the server called (another client, or a batch it measured) holds here too.
watch(() => status.value?.tapCooldown, (seconds) => {
  if (seconds) guard.cool(Date.now() + seconds * 1000);
  tapCooldown.value = guard.until;
});

function tap(): void {
  const was = guard.until;
  if (!guard.allow(Date.now())) {
    tapStats.blocked += 1;
    if (guard.until !== was) reportCooldown(guard.until);
    tapCooldown.value = guard.until;
    return;
  }
  tapStats.counted += 1;
  registerTap();
  countInput();
  bumpCounter();
  popShards();
}

export function onInput(e: InputEvent, count = true): void {
  noteActivity();
  // A hidden pet runs no inertia frames; keys and buttons still reach the room.
  pose.input(e, settings.mouseFollow && windowVisible.value ? settings.mouseSensitivity : null);
  if (e.kind !== "key_down" && e.kind !== "mouse_down") return;
  tapStats[e.kind === "key_down" ? "keys" : "mouse"] += 1;
  if (count) tap();
}

export function stopPet(): void { pose.stop(); }

watch(() => settings.mouseFollow, (enabled) => { if (!enabled) pose.stopMouse(); }, { flush: "sync" });
watch(windowVisible, (visible) => { if (!visible) pose.stopMouse(); }, { flush: "sync" });
