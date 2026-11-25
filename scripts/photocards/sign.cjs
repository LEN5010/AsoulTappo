// Renders a signature SVG's last frame, black on white. usage: node sign.cjs <svg> <output png> <width> <height>
// PLAYWRIGHT and CHROMIUM name the local playwright-core directory and the headless Chromium executable.
const { chromium } = require(process.env.PLAYWRIGHT);
const { pathToFileURL } = require("node:url");
const [, , svg, out, w, h] = process.argv;
(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM });
  const page = await browser.newPage({ viewport: { width: Math.ceil(+w), height: Math.ceil(+h) } });
  await page.goto(pathToFileURL(svg).href);
  await page.evaluate(([w, h]) => {
    const s = document.documentElement;
    s.setAttribute("width", w);
    s.setAttribute("height", h);
    s.setAttribute("preserveAspectRatio", "none");
    s.style.background = "#fff";
    s.querySelectorAll(":scope > rect").forEach((r) => r.remove());
    const im = s.querySelector("image");
    if (im) {
      const r = document.createElementNS("http://www.w3.org/2000/svg", "rect"), m = s.querySelector("mask");
      for (const k of ["x", "y", "width", "height"]) r.setAttribute(k, m.getAttribute(k));
      r.setAttribute("fill", "#000");
      r.setAttribute("mask", "url(#reveal)");
      im.replaceWith(r);
    } else s.querySelector("g[stroke]").setAttribute("stroke", "#000");
    s.pauseAnimations();
    s.setCurrentTime(+s.dataset.duration + 1);
  }, [w, h]);
  await page.screenshot({ path: out, clip: { x: 0, y: 0, width: Math.ceil(+w), height: Math.ceil(+h) } });
  await browser.close();
})();
