import { PET_BASE } from "../characters";
import { plateSize } from "./plates";

/** Match the flex actor's actual children, including the minimum-width nickname pill. */
export function remotePetSize(scale: number, showNames: boolean, showPlates: boolean) {
  const plate = plateSize(scale);
  return {
    w: Math.max(PET_BASE.width * scale, 64, showNames ? 120 : 0),
    h: PET_BASE.height * scale + (showNames ? Math.max(22, showPlates ? plate.height + 1 : 0) : 0),
  };
}
