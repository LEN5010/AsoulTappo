// Card videos play with their own sound when settings.cardAudio is on, at settings.volume.
import type { Directive } from "vue";
import { settings } from "../stores/settings";
import { boost } from "./sfx";

/**
 * Starts [video] audible if the setting allows it. A webview that refuses audible playback without a
 * fresh click gets the video muted instead, and [onMuted] reports that so a sound toggle can follow.
 * [routed] is set for a video that plays through the shared output, which applies the volume itself.
 */
export function playCardVideo(video: HTMLVideoElement, onMuted?: () => void, routed = false): void {
  video.muted = !settings.cardAudio;
  if (!routed) video.volume = settings.volume;
  video.play().catch(() => {
    if (video.muted) return;
    video.muted = true;
    onMuted?.();
    void video.play().catch(() => {});
  });
}

/** `v-card-sound` on a card `<video>` without `autoplay`/`muted`; a value above 1 plays it louder. */
export const vCardSound: Directive<HTMLVideoElement, number | undefined> = {
  mounted: (video, binding) => {
    const routed = !!binding.value && binding.value !== 1 && boost(video, binding.value);
    playCardVideo(video, undefined, routed);
  },
};
