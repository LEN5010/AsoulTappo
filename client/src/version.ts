/** This build's version, sent with every request so the server can refuse versions below its minimum. */
export const APP_VERSION: string = typeof __APP_VERSION__ === "string" ? __APP_VERSION__ : "0.0.0";
