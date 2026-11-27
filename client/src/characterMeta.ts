// Lightweight member names and colors shared by every window without pulling in the 140 KB asset manifest.
export const MEMBER_NAMES = ["嘉然", "乃琳", "贝拉", "心宜", "思诺"] as const;

// Matches `Object.keys(characters)[0]` (lexicographical order of `./assets/characters/*`).
export const DEFAULT_CHARACTER = "乃琳";

export const MEMBER_COLORS: Readonly<Record<string, string>> = {
  嘉然: "#e799b0",
  乃琳: "#576690",
  贝拉: "#db7d74",
  心宜: "#c93773",
  思诺: "#7252c0",
};

/** Member a character or skin name belongs to: 贝拉山海经 -> 贝拉. */
export function memberNameOf(name: string): string {
  for (const member of MEMBER_NAMES) {
    if (name.startsWith(member)) return member;
  }
  return name;
}

/** Member accent color for a character or skin name. */
export function memberColorOf(name: string): string {
  return MEMBER_COLORS[memberNameOf(name)] ?? "#ff6b9d";
}
