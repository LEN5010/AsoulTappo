// Character skin: the CSS variables that follow the selected character, and the theme's loading art.
import { characterColor, getTheme, resolveAsset } from "./manifest";

export interface Skin {
  vars: Record<string, string>;
  loading: string;
}

export function buildSkin(themeId: string, character: string, serverBase: string, appBase = "/"): Skin {
  return {
    vars: { "--char": characterColor(character) },
    loading: resolveAsset(getTheme(themeId).parts.loading, serverBase, appBase),
  };
}
