// Names the player gives their own skins. They replace the skin's title in the album, the skin detail and the
// backpack, on this device: they are kept in the local settings and go nowhere else.
import { skinTitle } from "../manifest";
import { cleanSkinNote, settings } from "./settings";

export const skinNote = (name: string) => settings.skinNotes[name] ?? "";
/** The note when there is one, else the skin's own title. */
export const shownSkinName = (name: string) => skinNote(name) || skinTitle(name);

/** Saves [text] as the note of skin [name]; empty, or the skin's own title, removes it. */
export function setSkinNote(name: string, text: string): void {
  const note = cleanSkinNote(text);
  const rest = Object.fromEntries(Object.entries(settings.skinNotes).filter(([k]) => k !== name));
  settings.skinNotes = note && note !== skinTitle(name) ? { ...rest, [name]: note } : rest;
}
