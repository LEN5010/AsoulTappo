// The user agreement and the privacy policy, shown at start until accepted and from the settings page.
// The Markdown files are the only copy; the font subset reads them too (scripts/build_ui_assets.py).
import privacy from "./privacy.md?raw";
import terms from "./terms.md?raw";

/**
 * The texts' version. Change it whenever either text changes in substance: every player is asked again at the
 * next start, and nothing reaches the server until they agree.
 */
export const TERMS_VERSION = "2026-11-19";

/**
 * The statement every new version asks the player to confirm (panel/TermsDialog.vue): the app is free and not run
 * for profit. One paragraph a line.
 */
export const STATEMENT = [
  "AsoulTappo 是 A-SOUL 粉丝制作的非官方作品，免费提供，不以盈利为目的。",
  "碎片、驼币等游戏内容只能通过游玩获得，不出售。",
  "如果你是付费获得本软件的，请向卖家要求退款。",
];

/**
 * The standalone edition's statement (src/edition.ts), confirmed once per app version in place of the texts and the
 * statement above, which are about the server. A draft: replace the text here.
 */
export const STANDALONE_STATEMENT =
  "AsoulTappo 单机版是非官方的免费软件，不连接任何服务器，数据只保存在本机。A-SOUL 的标志、角色形象和视频版权归 A-SOUL 所有。";

export type DocName = "terms" | "privacy";
export const DOCS: Record<DocName, string> = { terms, privacy };

export type Block =
  | { kind: "heading"; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; items: string[] };

export interface Doc {
  title: string;
  blocks: Block[];
}

/**
 * The small part of Markdown the texts use: one `#` title, `##` headings, `- ` lists and paragraphs split by
 * blank lines. Everything stays plain text, so nothing in the files is rendered as markup.
 */
export function parseDoc(source: string): Doc {
  let title = "";
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: string[] | null = null;
  const end = () => {
    if (paragraph.length) blocks.push({ kind: "paragraph", text: paragraph.join("") });
    if (list) blocks.push({ kind: "list", items: list });
    paragraph = [];
    list = null;
  };
  for (const raw of source.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) end();
    else if (line.startsWith("## ")) { end(); blocks.push({ kind: "heading", text: line.slice(3).trim() }); }
    else if (line.startsWith("# ")) { end(); title = line.slice(2).trim(); }
    else if (line.startsWith("- ")) {
      if (paragraph.length) end();
      (list ??= []).push(line.slice(2).trim());
    } else if (list) {
      // A wrapped line continues the item above it.
      list[list.length - 1] += line;
    } else {
      paragraph.push(line);
    }
  }
  end();
  return { title, blocks };
}

/** Each text's `#` title, for dialog headers. */
export const DOC_TITLES: Record<DocName, string> = { terms: parseDoc(terms).title, privacy: parseDoc(privacy).title };
