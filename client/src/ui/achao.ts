// 阿草, the alpaca: its sticker set, by name.
const files = import.meta.glob<string>("../assets/emotes/achao/*.webp", { eager: true, query: "?url", import: "default" });

export const ACHAO: Record<string, string> = Object.fromEntries(
  Object.entries(files).map(([path, src]) => [path.slice(path.lastIndexOf("/") + 1, -5), src]),
);
