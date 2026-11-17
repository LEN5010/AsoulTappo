// State of the local pet, driven by the global input hook. Shared by the desk pet and the
// live preview in the backpack page.
import { ref, watch } from "vue";
import type { InputEvent } from "../composables/tauri";
import { PetPose } from "../pet/PetPose";
import { ShownPresses } from "../pet/ShownPresses";
import { DEFAULT_RULES, TapGuard } from "../pet/TapGuard";
import { economy } from "./economy";
import { bumpCounter } from "./counter";
import { countInput, reportCooldown, status } from "./player";
import { inRoom, registerTap, syncMotion, youId } from "./room";
import { settings } from "./settings";
import { popShards } from "./shardPop";
import { noteActivity, windowVisible } from "./activity";
import { noteAutoInput } from "./autoHint";

const pose = new PetPose();
export const pet = pose.pet;
// The room gets the hand's presses only: what other software sent moves the own pet and stays on this desk.
const shown = new ShownPresses();

watch(() => [pet.dx, pet.dy, shown.state.keyDown, shown.state.left, shown.state.right, inRoom.value, youId.value],
  () => syncMotion({ dx: pet.dx, dy: pet.dy, ...shown.state }), { flush: "sync" });

const guard = new TapGuard(() => economy.value?.tapGuard ?? DEFAULT_RULES);
/** Presses this page received and what became of them, for the debug build's log (src/debugLog.ts). */
export const tapStats = { keys: 0, mouse: 0, counted: 0, blocked: 0 };
/** When inputs count again after going faster than a hand; in the past while they count. */
export const tapCooldown = ref(0);
// A cooldown the server called (another client, or a batch it measured) holds here too.
watch(() => status.value?.tapCooldown, (seconds) => {
  if (seconds) guard.cool(Date.now() + seconds * 1000);
  tapCooldown.value = guard.until;
});

watch(() => status.value?.autoInput, (seconds) => noteAutoInput(seconds), { immediate: true });

function tap(injected?: boolean): void {
  const was = guard.until;
  if (!guard.allow(Date.now())) {
    tapStats.blocked += 1;
    if (guard.until !== was) reportCooldown(guard.until);
    tapCooldown.value = guard.until;
    return;
  }
  tapStats.counted += 1;
  // Counted and paid like any tap; the room's count is of hands.
  if (!injected) registerTap();
  countInput(injected);
  bumpCounter();
  popShards();
}

export function onInput(e: InputEvent, count = true): void {
  noteActivity();
  // A hidden pet runs no inertia frames; keys and buttons still reach the room.
  pose.input(e, settings.mouseFollow && windowVisible.value ? settings.mouseSensitivity : null);
  shown.input(e);
  if (e.kind !== "key_down" && e.kind !== "mouse_down") return;
  tapStats[e.kind === "key_down" ? "keys" : "mouse"] += 1;
  if (count) tap(e.injected);
}

export function stopPet(): void {
  pose.stop();
  shown.stop();
}

watch(() => settings.mouseFollow, (enabled) => { if (!enabled) pose.stopMouse(); }, { flush: "sync" });
watch(windowVisible, (visible) => { if (!visible) pose.stopMouse(); }, { flush: "sync" });
