//! The monitor the overlay was last moved to from the tray, kept across restarts.
//!
//! A monitor is remembered by its key, `name@x,y` (the system's display name and the origin of its
//! frame), not by its place in the monitor list: that order changes when a monitor is unplugged and
//! plugged back in. A monitor found by its whole key wins; otherwise one with the same name (moved in
//! the arrangement); otherwise the overlay starts on the primary monitor.

use std::path::PathBuf;
use tauri::Manager;

fn path(app: &tauri::AppHandle) -> Option<PathBuf> {
    app.path().app_config_dir().ok().map(|dir| dir.join("monitor"))
}

pub fn key(name: &str, x: f64, y: f64) -> String {
    format!("{name}@{x},{y}")
}

pub fn load(app: &tauri::AppHandle) -> Option<String> {
    let key = std::fs::read_to_string(path(app)?).ok()?;
    let key = key.trim();
    (!key.is_empty()).then(|| key.to_string())
}

pub fn save(app: &tauri::AppHandle, key: &str) -> std::io::Result<()> {
    let Some(path) = path(app) else {
        return Err(std::io::Error::new(std::io::ErrorKind::NotFound, "no app config dir"));
    };
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
    }
    std::fs::write(path, key)
}

fn name_of(key: &str) -> &str {
    key.rsplit_once('@').map_or(key, |(name, _)| name)
}

/// Index in `keys` of the monitor `saved` names, if one is there.
pub fn pick(keys: &[String], saved: &str) -> Option<usize> {
    keys.iter()
        .position(|k| k == saved)
        .or_else(|| keys.iter().position(|k| name_of(k) == name_of(saved)))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn keys(list: &[&str]) -> Vec<String> {
        list.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn the_whole_key_wins_then_the_name() {
        let now = keys(&["Built-in Retina Display@0,0", "DELL U2720Q@1512,-200"]);
        assert_eq!(pick(&now, "DELL U2720Q@1512,-200"), Some(1));
        // the same screen after it was moved in the arrangement
        assert_eq!(pick(&now, "DELL U2720Q@-2560,0"), Some(1));
        // unplugged: the caller falls back to the primary monitor
        assert_eq!(pick(&now, "LG HDR 4K@1512,0"), None);
    }

    #[test]
    fn the_list_order_does_not_matter() {
        let now = keys(&["DELL U2720Q@1512,-200", "Built-in Retina Display@0,0"]);
        assert_eq!(pick(&now, "DELL U2720Q@1512,-200"), Some(0));
    }

    #[test]
    fn two_monitors_of_one_model_are_told_apart_by_their_origin() {
        let now = keys(&["DELL U2720Q@0,0", "DELL U2720Q@2560,0"]);
        assert_eq!(pick(&now, "DELL U2720Q@2560,0"), Some(1));
        assert_eq!(pick(&now, "DELL U2720Q@0,0"), Some(0));
    }

    #[test]
    fn a_name_with_an_at_sign_keeps_it() {
        assert_eq!(name_of(&key("Studio @ Home", 0.0, 0.0)), "Studio @ Home");
    }
}
