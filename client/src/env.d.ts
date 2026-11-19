/// <reference types="vite/client" />
declare const __APP_VERSION__: string;
/** True in the standalone edition (src/edition.ts); set by vite.config.ts. */
declare const __STANDALONE__: boolean;
declare module "*.vue" {
  import type { DefineComponent } from "vue";
  const component: DefineComponent<object, object, unknown>;
  export default component;
}
