// Card videos play with their own sound when settings.cardAudio is on.
import type { Directive } from "vue";
import { settings } from "../stores/settings";

/**
 * Starts [video] audible if the setting allows it. A webview that refuses audible playback without a
 * fresh click gets the video muted instead, and [onMuted] reports that so a sound toggle can follow.
 */
export function playCardVideo(video: HTMLVideoElement, onMuted?: () => void): void {
  video.muted = !settings.cardAudio;
  video.play().catch(() => {
    if (video.muted) return;
    video.muted = true;
    onMuted?.();
    void video.play().catch(() => {});
  });
}

/** `v-card-sound` on a card `<video>` without `autoplay`/`muted`. */
export const vCardSound: Directive<HTMLVideoElement> = {
  mounted: (video) => playCardVideo(video),
};
