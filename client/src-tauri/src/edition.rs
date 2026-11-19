//! Names that differ between the online edition and the standalone one (cargo feature `standalone`).
//!
//! Both can be installed and run side by side, so everything the system keys by name is kept apart: the
//! single-instance mutex and the "start as administrator" file (src/elevation.rs), the start-at-login entry
//! (src/autostart.rs), window titles and the tray. The log, the monitor preference and the web view's storage live
//! under folders named after the bundle identifier, which Tauri keeps apart by itself.

#[cfg(not(feature = "standalone"))]
mod names {
    /// `identifier` in tauri.conf.json.
    pub const IDENTIFIER: &str = "io.github.len5010.asoultappo";
    /// `productName` in tauri.conf.json: the NSIS uninstaller deletes the start-at-login value of this name.
    pub const PRODUCT_NAME: &str = "AsoulTappo";
    /// Shown in window titles and the tray.
    pub const DISPLAY_NAME: &str = "AsoulTappo";
    /// Links the About section may open in the system browser or mail app.
    pub const ABOUT_LINKS: &[&str] = &[
        "https://github.com/LEN5010/AsoulTappo",
        "https://space.bilibili.com/107261543",
        "mailto:len5010@qq.com",
        "https://len5010.top/dynamics/download?app=tappo",
        "https://len5010.top",
        "https://len5010.top/download",
        "https://len5010.me/sponsor/",
    ];
}

#[cfg(feature = "standalone")]
mod names {
    /// `identifier` in tauri.standalone.conf.json.
    pub const IDENTIFIER: &str = "io.github.len5010.asoultappo.offline";
    /// `productName` in tauri.standalone.conf.json.
    pub const PRODUCT_NAME: &str = "AsoulTappoOffline";
    pub const DISPLAY_NAME: &str = "AsoulTappo 单机版";
    /// Without the main site's pages: the standalone edition has no account and no downloads there.
    pub const ABOUT_LINKS: &[&str] = &[
        "https://github.com/LEN5010/AsoulTappo",
        "https://space.bilibili.com/107261543",
        "mailto:len5010@qq.com",
        "https://len5010.me/sponsor/",
    ];
}

pub use names::*;

#[cfg(test)]
mod tests {
    use super::*;

    /// The online edition's names are what installed copies already use: changing one would lose the player's
    /// start-at-login entry or let two instances run.
    #[cfg(not(feature = "standalone"))]
    #[test]
    fn online_names_stay_as_installed() {
        assert_eq!(IDENTIFIER, "io.github.len5010.asoultappo");
        assert_eq!(PRODUCT_NAME, "AsoulTappo");
        assert_eq!(DISPLAY_NAME, "AsoulTappo");
        assert_eq!(ABOUT_LINKS.len(), 7);
    }

    #[cfg(feature = "standalone")]
    #[test]
    fn standalone_names_differ_and_links_stay_off_the_main_site() {
        assert!(IDENTIFIER.ends_with(".offline"));
        assert_eq!(PRODUCT_NAME, "AsoulTappoOffline");
        assert!(ABOUT_LINKS.iter().all(|l| !l.contains("len5010.top")));
    }
}
