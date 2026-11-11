// The user agreement and the privacy policy, shown at start until accepted and from the settings page.
// The Markdown files are the only copy; the font subset reads them too (scripts/build_ui_assets.py).
import privacy from "./privacy.md?raw";
import terms from "./terms.md?raw";

/**
 * The texts' version. Change it whenever either text changes in substance: every player is asked again at the
 * next start, and nothing reaches the server until they agree.
 */
export const TERMS_VERSION = "2026-11-11";

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
