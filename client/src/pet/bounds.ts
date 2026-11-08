import { PET_BASE } from "../characters";
import { nameBand, plateSize } from "./plates";

/** Match the flex actor's actual children; names never grow wider than the pet. */
export function remotePetSize(scale: number, showNames: boolean, showPlates: boolean) {
  const plate = plateSize(scale);
  return {
    w: Math.max(PET_BASE.width * scale, 64),
    h: PET_BASE.height * scale + (showNames ? Math.max(nameBand(scale).pill, showPlates ? plate.height + 1 : 0) : 0),
  };
}
