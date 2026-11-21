fn main() {
    check_edition();
    tauri_build::build()
}

/// The cargo feature and the Tauri configuration must name the same edition. The standalone overlay
/// (tauri.standalone.conf.json) reaches this script through `TAURI_CONFIG`, set by `tauri build --config` or by hand
/// for `cargo check`. Without it the standalone code would ship under the online identifier, and the overlay without
/// the feature would give the online code the standalone identifier.
fn check_edition() {
    println!("cargo:rerun-if-env-changed=TAURI_CONFIG");
    let feature = std::env::var_os("CARGO_FEATURE_STANDALONE").is_some();
    let config = std::env::var("TAURI_CONFIG").unwrap_or_default();
    let overlay = config.contains("io.github.len5010.asoultappo.offline");
    if feature && !overlay {
        panic!(
            "--features standalone needs the standalone configuration: \
             tauri build --config src-tauri/tauri.standalone.conf.json, or TAURI_CONFIG=\"$(cat tauri.standalone.conf.json)\" for cargo"
        );
    }
    if overlay && !feature {
        panic!("tauri.standalone.conf.json needs `--no-default-features --features standalone`");
    }
}
