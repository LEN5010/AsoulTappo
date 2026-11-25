// Draws the pictures of a series' box for the page: <series>/shop/poster.webp, the shelf as it stands (for the moment before
// the canvas draws, and for machines without WebGL 2), and <series>/shop/mini.webp, the box alone.
// usage: node poster.cjs <series>
// CLIENT is the address of the client's dev server; PLAYWRIGHT and CHROMIUM name the local playwright-core directory and the
// headless Chromium executable.
const { chromium } = require(process.env.PLAYWRIGHT);
const fs = require("node:fs");
const path = require("node:path");
const [, , series] = process.argv;
const { CLIENT } = process.env;
const OUT = process.env.OUT ?? path.join(__dirname, "../../client/src/assets/photocards", series, "shop");
// The poster's size in design units (PhotoShelf.vue lays it out), and the mini's; device pixels to one of them.
const POSTER = [480, 580], MINI = [96, 120], DPR = 2;
const PAGE = `<!doctype html><script type="module" src="/@vite/client"></script>
<body style="margin:0"><div id="host" style="position:relative"></div>`;

async function draw([series, poster, mini]) {
  const { photoGl, mountScene } = await import("/src/photo/engine.ts");
  const { createShelf } = await import("/src/photo/shelf.ts");
  const { seriesArt } = await import("/src/photo/art.ts");
  const { photoItems } = await import("/src/photocards.ts");
  const { boxModel } = await import("/src/photo/painter.ts");
  const { camera, P } = await import("/src/photo/gl.ts");
  const host = document.getElementById("host");
  const { gl, kit, painter, canvas } = await photoGl();
  const art = seriesArt(series);
  const size = (w, h) => { host.style.width = `${w}px`; host.style.height = `${h}px`; };
  const out = {};

  size(...poster);
  const shelf = createShelf(gl, kit, painter, {
    art, cards: photoItems(series).map((i) => ({ card: i.card, signed: i.kind === "sign" })),
    rect: () => host.getBoundingClientRect(), place: () => ({ x: 0, y: 0, scale: 1 }), on() {},
  });
  await shelf.ready;
  const stand = mountScene(host, shelf);
  shelf.stand();
  shelf.update(0);
  shelf.draw();
  out.poster = canvas.toDataURL("image/webp", 0.92);
  stand.release();
  shelf.dispose();

  size(...mini);
  await kit.ink(series);
  let view = { w: 1, h: 1, px: 1 };
  const box = Object.assign(boxModel(series, P(0, 1, { rx: -9, ry: -26, s: 0.255 })), { lit: 1.06 });
  const alone = {
    busy: false,
    resize(w, h, dpr) { view = { w, h, px: dpr }; },
    update() {},
    draw() {
      gl.viewport(0, 0, gl.drawingBufferWidth, gl.drawingBufferHeight);
      gl.enable(gl.BLEND);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
      painter.begin({ vp: camera(view.w, view.h), px: view.px, clock: 0, lamp: [-30, -40, 60], room: [0, 0] });
      painter.solid();
      painter.box(box, box.lit);
    },
  };
  const small = mountScene(host, alone);
  alone.draw();
  out.mini = canvas.toDataURL("image/webp", 0.92);
  small.release();
  return out;
}

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM, args: ["--use-gl=angle", "--use-angle=metal", "--enable-gpu", "--ignore-gpu-blocklist"],
  });
  const page = await browser.newPage({ viewport: { width: 640, height: 640 }, deviceScaleFactor: DPR });
  page.on("pageerror", (e) => console.error(e.message));
  // Nothing but the dev server is reached.
  await page.route("**/*", (r) => {
    const url = new URL(r.request().url());
    if (url.pathname === "/__poster") {
      return r.fulfill({ contentType: "text/html", body: PAGE });
    }
    return url.protocol.startsWith("http") && url.origin !== new URL(CLIENT).origin ? r.abort() : r.continue();
  });
  await page.goto(`${CLIENT}/__poster`);
  const out = await page.evaluate(draw, [series, POSTER, MINI]);
  fs.mkdirSync(OUT, { recursive: true });
  for (const [name, url] of Object.entries(out)) {
    const bytes = Buffer.from(url.split(",")[1], "base64");
    fs.writeFileSync(path.join(OUT, `${name}.webp`), bytes);
    console.log(`${name}.webp`, bytes.length);
  }
  await browser.close();
})();
