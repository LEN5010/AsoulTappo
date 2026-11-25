// The photocards as the client has them: the list from its manifest; templates, pictures and signatures from its assets.
// The pages have to be served from the repository's root, or these paths do not resolve.
const ROOT = new URL("../../../client/src/", import.meta.url);
const SERIES = "asoul2026";
const ART = new URL(`assets/photocards/${SERIES}/`, ROOT).href;
export const OPEN = new URL("assets/photocards/open/", ROOT).href;
export const BOX = `${ART}box.webp`;
export const SFX = new URL("assets/sfx/", ROOT).href;
const IDS = { 嘉然: "diana", 贝拉: "bella", 乃琳: "eileen" };

const template = (id) => id.replace(/-\d+$/, "");
/** What is printed on a side, and its finishes. */
export const front = (id) => [`${ART}front/${id}.webp`, `${ART}mat/front-${template(id)}.webp`];
export const back = (name) => [`${ART}back/${name}.webp`, `${ART}mat/back-${name}.webp`];
export const sign = (member) => `${ART}sign/${member}.webp`;

/** Cards: id, kind, label, who is on it from left to right, size, back (several cards share one), and the colours of the
 * front's deep foil and of the back's lettering. Signatures, by member: box, its place on the card in texels; ms, how long
 * it takes to write; tip, the pen's path. */
export async function catalog() {
  const read = (path) => fetch(new URL(path, ROOT), { cache: "no-store" }).then((r) => r.json());
  const [manifest, art] = await Promise.all([read("data/manifest.json"), read(`assets/photocards/${SERIES}/cards.json`)]);
  const cards = manifest.photocards.find((s) => s.id === SERIES).cards.map(({ id, kind, characters }) => ({
    id, kind, label: `${kind === "group" ? "团体" : characters.join(" ")} ${id.match(/\d+$/)[0]}`,
    stand: art.stand[id] ?? characters.map((c) => IDS[c]), ...art.templates[template(id)],
  }));
  return { cards, signs: art.signs };
}
