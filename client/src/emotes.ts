// Emote keys sent over the wire -> display glyph. Unknown keys are shown as text.
export const EMOTES: { key: string; glyph: string; label: string }[] = [
  { key: "heart", glyph: "❤️", label: "爱心" },
  { key: "clap", glyph: "👏", label: "鼓掌" },
  { key: "laugh", glyph: "😂", label: "笑哭" },
  { key: "party", glyph: "🎉", label: "庆祝" },
  { key: "cry", glyph: "😭", label: "大哭" },
  { key: "fire", glyph: "🔥", label: "火" },
  { key: "star", glyph: "⭐", label: "星星" },
  { key: "bread", glyph: "🍞", label: "小面包" },
];

export function emoteGlyph(key: string): string {
  return EMOTES.find((e) => e.key === key)?.glyph ?? key.slice(0, 4);
}
