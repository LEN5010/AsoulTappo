/** Keep only a small look-ahead window; decoding all full-size draw art at once is unnecessary. */
export function createImagePreloader(limit = 2) {
  let wanted = new Set<string>();
  const active = new Map<string, { image: HTMLImageElement; cancelled: boolean }>();
  const ready = new Map<string, HTMLImageElement>();
  const release = (image: HTMLImageElement) => image.removeAttribute("src");
  function pump() {
    for (const url of wanted) {
      if (active.size >= limit) break;
      if (active.has(url) || ready.has(url)) continue;
      const image = new Image();
      const job = { image, cancelled: false };
      active.set(url, job);
      image.src = url;
      void image.decode().catch(() => {}).then(() => {
        active.delete(url);
        if (wanted.has(url) && !job.cancelled) ready.set(url, image);
        else release(image);
        pump();
      });
    }
  }
  function setWindow(urls: string[]) {
    wanted = new Set(urls.filter(Boolean).filter((url, i, all) => all.indexOf(url) === i).slice(0, limit));
    for (const [url, image] of ready) if (!wanted.has(url)) { release(image); ready.delete(url); }
    // Keep cancelled work in active until decode settles, so switching windows cannot exceed the cap.
    for (const [url, job] of active) if (!wanted.has(url) && !job.cancelled) {
      job.cancelled = true;
      release(job.image);
    }
    pump();
  }
  return { setWindow, clear: () => setWindow([]) };
}
