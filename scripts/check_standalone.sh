#!/bin/bash
# Cargo-level checks of the standalone edition (cargo feature `standalone`, client/src-tauri/tauri.standalone.conf.json).
#   scripts/check_standalone.sh               the standalone edition only (what CI runs)
#   scripts/check_standalone.sh --with-online the online edition first, as CI checks it
#
# Needs node and cargo. Set CARGO_NET_OFFLINE=true to run without network. When client/dist is missing (no front-end
# build yet), an empty placeholder page is put there for the duration of the run: generate_context! reads that folder.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
tauri="$root/client/src-tauri"
cd "$tauri"

placeholder=""
if [ ! -e ../dist ]; then
  mkdir -p ../dist
  printf '<!doctype html><title>placeholder</title>\n' > ../dist/index.html
  placeholder=1
  echo "client/dist is missing: using an empty placeholder page"
fi
cleanup() {
  if [ -n "$placeholder" ]; then rm -rf ../dist; fi
}
trap cleanup EXIT

if [ "${1:-}" = "--with-online" ]; then
  echo "== online edition: cargo check and tests"
  cargo check --all-targets --locked
  cargo test --lib --locked
fi

# The overlay replaces the whole window list (a JSON merge patch replaces arrays), so its main window must stay a copy
# of the online one apart from the title. The overlay goes to cargo as ASCII-only JSON: Git Bash on Windows may not
# pass other characters through the environment intact.
TAURI_CONFIG="$(node -e '
const fs = require("fs");
const base = JSON.parse(fs.readFileSync("tauri.conf.json", "utf8"));
const overlay = JSON.parse(fs.readFileSync("tauri.standalone.conf.json", "utf8"));
const strip = (windows) => JSON.stringify(windows.map(({ title, ...rest }) => rest));
if (strip(base.app.windows) !== strip(overlay.app.windows)) {
  console.error("tauri.standalone.conf.json: app.windows differs from tauri.conf.json in more than the title");
  process.exit(1);
}
process.stdout.write(JSON.stringify(overlay).replace(/[\u0080-￿]/g, (c) => "\\u" + c.charCodeAt(0).toString(16).padStart(4, "0")));
')"
export TAURI_CONFIG
standalone=(--locked --no-default-features --features standalone)

echo "== standalone edition: cargo check (as tauri build compiles it, with tauri/custom-protocol)"
cargo check --all-targets "${standalone[@]}" --features tauri/custom-protocol
echo "== standalone edition: cargo test"
cargo test --lib "${standalone[@]}"

# The targets the installers are built for. `--target all` would also list tauri's own reqwest, which it uses only on
# Android and iOS.
echo "== standalone edition: no HTTP or WebSocket client in the dependency tree"
for target in x86_64-pc-windows-msvc aarch64-apple-darwin x86_64-apple-darwin; do
  tree="$(cargo tree -e normal,build --prefix none --target "$target" "${standalone[@]}")"
  clients="$(grep -E '^(reqwest|hyper|hyper-util|hyper-rustls|h2|ureq|isahc|curl|attohttpc|minreq|rustls|native-tls|tokio-rustls|tungstenite|tokio-tungstenite|tauri-plugin-updater|tauri-plugin-http|tauri-plugin-websocket|tauri-plugin-upload) ' <<< "$tree" | sort -u || true)"
  if [ -n "$clients" ]; then
    echo "$target: the standalone edition depends on:" >&2
    echo "$clients" >&2
    exit 1
  fi
  echo "$target: none found"
done
