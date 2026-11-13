// The park's coin pictures, bundled with the client: 256px for the big coin, 64px for small marks, and the
// stamp badges (the 64px coin in copper, silver and gold).
import { resolveAsset } from "../../manifest";

const base = import.meta.env.BASE_URL || "/";
export const COIN = resolveAsset("bundle:park/coin.webp", "", base);
export const COIN_SMALL = resolveAsset("bundle:park/coin-64.webp", "", base);
export const BADGE_ART = [1, 2, 3].map((n) => resolveAsset(`bundle:park/badge-${n}.webp`, "", base));
