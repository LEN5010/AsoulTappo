// One <video> per card feeds every name plate wearing it: each plate copies the frames into its
// own canvas, so a room where several partners wear the same card decodes it once.

type Paint = (video: HTMLVideoElement) => void;
interface Feed { paints: Set<Paint>; stop(): void }

const feeds = new Map<string, Feed>();
let shelf: HTMLElement | null = null;

/** The videos stay in the document and inside the viewport, or the webview may stop decoding them. */
function shelfEl(): HTMLElement {
  if (!shelf) {
    shelf = document.createElement("div");
    shelf.setAttribute("aria-hidden", "true");
    Object.assign(shelf.style, {
      position: "fixed", right: "0", bottom: "0", width: "1px", height: "1px",
      overflow: "hidden", opacity: "0.01", pointerEvents: "none",
    });
    document.body.append(shelf);
  }
  return shelf;
}

function open(src: string): Feed {
  const video = document.createElement("video");
  video.muted = true;
  video.loop = true;
  video.playsInline = true;
  video.preload = "auto";
  video.src = src;
  shelfEl().append(video);
  const paints = new Set<Paint>();
  let live = true;
  const next = () => {
    if (!live) return;
    if ("requestVideoFrameCallback" in video) video.requestVideoFrameCallback(frame);
    else requestAnimationFrame(frame);
  };
  const frame = () => {
    if (!live) return;
    if (video.readyState >= 2) for (const paint of paints) paint(video);
    next();
  };
  next();
  void video.play().catch(() => {});
  return {
    paints,
    stop() {
      live = false;
      video.pause();
      video.removeAttribute("src");
      video.load();
      video.remove();
    },
  };
}

/** Calls `paint` with the video on every new frame of `src`; the returned function stops it. */
export function followVideo(src: string, paint: Paint): () => void {
  let feed = feeds.get(src);
  if (!feed) {
    feed = open(src);
    feeds.set(src, feed);
  }
  const own = feed;
  own.paints.add(paint);
  return () => {
    own.paints.delete(paint);
    if (own.paints.size || feeds.get(src) !== own) return;
    own.stop();
    feeds.delete(src);
  };
}
