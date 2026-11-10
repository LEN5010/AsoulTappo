// The capture window (src/CaptureApp.vue) draws the own pet in a regular window, which recording and
// screenshot software can pick where it skips the desk overlay. The desk opens and closes it after
// settings.captureOpen and tells it what the pet looks like and is doing, so that window needs no settings,
// player or room of its own.
import { invoke } from "@tauri-apps/api/core";
import { emitTo, listen } from "@tauri-apps/api/event";
import { watch } from "vue";
import type { EmoteFrame } from "../pet/EmotePlayer";
import type { ComboFrame } from "../pet/TapCombo";
import { counter } from "../stores/counter";
import { draws } from "../stores/player";
import { localPet } from "../stores/room";
import { settings } from "../stores/settings";
import { shardCombo } from "../stores/shardPop";

export interface CaptureView {
  character: string;
  /** How far the mouse paw follows the cursor; null while it stays put. */
  sensitivity: number | null;
  /** "#rrggbb" */
  bg: string;
  /** The strip under the pet; null while it is folded away on the desk. */
  bar: { count: number; view: "today" | "total"; draws: number } | null;
  emote: EmoteFrame | null;
  /** Shards earned while typing. */
  combo: ComboFrame | null;
  /** Shards a scratch card or a duel just paid. */
  win: ComboFrame | null;
}

// Frames are copied field by field so that a frame changed in place is seen as well.
const view = (): CaptureView => ({
  character: settings.character,
  sensitivity: settings.mouseFollow ? settings.mouseSensitivity : null,
  bg: settings.captureBg,
  bar: settings.barFolded ? null : {
    count: settings.tapView === "today" ? counter.today : counter.total, view: settings.tapView, draws: draws.value,
  },
  emote: localPet.emote && { ...localPet.emote },
  combo: settings.shardPop && shardCombo.value ? { ...shardCombo.value } : null,
  win: localPet.win && { ...localPet.win },
});

export async function startCapture(): Promise<() => void> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const send = () => {
    timer = undefined;
    if (settings.captureOpen) void emitTo("capture", "capture:view", view());
  };
  // The window asks once it listens; its close button reports here so the setting follows; the size it is
  // dragged to is the size it opens with next time.
  const unReady = await listen("capture:ready", send, { target: "main" });
  const unClosed = await listen("capture:closed", () => { settings.captureOpen = false; }, { target: "main" });
  let sized: ReturnType<typeof setTimeout> | undefined;
  const unSize = await listen<[number, number]>("capture:size", ({ payload: [w, h] }) => {
    // Sent all through a drag; kept once it has settled.
    clearTimeout(sized);
    sized = setTimeout(() => { settings.captureW = Math.round(w); settings.captureH = Math.round(h); }, 400);
  }, { target: "main" });
  // The count and the combo change with every tap: what changed within a frame goes out together.
  const stopView = watch(view, () => { if (settings.captureOpen) timer ??= setTimeout(send, 16); });
  const stopOpen = watch(() => settings.captureOpen, (open) => {
    invoke("set_capture_window", { open, width: settings.captureW, height: settings.captureH })
      .catch(() => { if (open) settings.captureOpen = false; });
  }, { immediate: true });
  return () => { unReady(); unClosed(); unSize(); stopView(); stopOpen(); clearTimeout(timer); clearTimeout(sized); };
}
