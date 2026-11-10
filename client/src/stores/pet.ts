// State of the local pet, driven by the global input hook. Shared by the desk pet and the
// live preview in the backpack page.
import { reactive, ref, watch } from "vue";
import type { InputEvent } from "../composables/tauri";
import { MouseMotion } from "../MouseMotion";
import { TapGuard } from "../pet/TapGuard";
import { bumpCounter } from "./counter";
import { countInput, reportCooldown, status } from "./player";
import { inRoom, registerTap, syncMotion, youId } from "./room";
import { settings } from "./settings";
import { popShards } from "./shardPop";
import { noteActivity, windowVisible } from "./activity";

export const pet = reactive({ keyDown: false, left: false, right: false, dx: 0, dy: 0 });
let keysHeld = 0;
const motion = new MouseMotion(pet);

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
  switch (e.kind) {
    case "key_down":
      tapStats.keys += 1;
      keysHeld += 1;
      pet.keyDown = true;
      if (count) tap();
      break;
    case "key_up":
      keysHeld = Math.max(0, keysHeld - 1);
      pet.keyDown = keysHeld > 0;
      break;
    case "mouse_down":
      tapStats.mouse += 1;
      if (e.button === "left") pet.left = true;
      else if (e.button === "right") pet.right = true;
      if (count) tap();
      break;
    case "mouse_up":
      if (e.button === "left") pet.left = false;
      else if (e.button === "right") pet.right = false;
      break;
    case "mouse_move":
      // A hidden pet runs no inertia frames; keys and buttons still reach the room.
      if (!settings.mouseFollow || !windowVisible.value) break;
      motion.move(e.dx, e.dy, settings.mouseSensitivity);
      break;
  }
}

export function stopPet(): void {
  motion.stop();
  keysHeld = 0;
  Object.assign(pet, { keyDown: false, left: false, right: false, dx: 0, dy: 0 });
}

watch(() => settings.mouseFollow, (enabled) => { if (!enabled) motion.stop(); }, { flush: "sync" });
watch(windowVisible, (visible) => { if (!visible) motion.stop(); }, { flush: "sync" });
