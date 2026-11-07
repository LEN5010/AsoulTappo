//! Installs one exact version from its own GitHub release.
//!
//! The endpoint in tauri.conf.json is `releases/latest`, which GitHub never points at a pre-release,
//! so every beta was offered and then never found. This asks the release tagged `v<version>` instead.
use serde::Serialize;
use tauri::ipc::Channel;
use tauri_plugin_updater::UpdaterExt;

const RELEASE_BASE: &str = "https://github.com/LEN5010/AsoulTappo/releases/download";

#[derive(Clone, Serialize)]
#[serde(tag = "event", content = "data")]
pub enum InstallEvent {
    Started { content_length: Option<u64> },
    Progress { chunk_length: usize },
    Finished,
}

/// Only plain semver ends up in the URL: digits, dots, a `-pre.release`, no slashes or queries.
fn valid(version: &str) -> bool {
    let core = version.split_once('-').map_or(version, |(c, _)| c);
    !version.is_empty()
        && version.len() <= 64
        && core.split('.').count() == 3
        && core.split('.').all(|p| !p.is_empty() && p.bytes().all(|b| b.is_ascii_digit()))
        && version.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'.' || b == b'-')
}

#[tauri::command]
pub async fn install_version(
    app: tauri::AppHandle,
    version: String,
    on_event: Channel<InstallEvent>,
) -> Result<bool, String> {
    if !valid(&version) {
        return Err("bad version".into());
    }
    let url = format!("{RELEASE_BASE}/v{version}/latest.json")
        .parse()
        .map_err(|e: url::ParseError| e.to_string())?;
    let update = app
        .updater_builder()
        .endpoints(vec![url])
        .map_err(|e| e.to_string())?
        .timeout(std::time::Duration::from_secs(15))
        .build()
        .map_err(|e| e.to_string())?
        .check()
        .await
        .map_err(|e| e.to_string())?;
    // Missing, or not the version offered (the release still uploading): the caller opens the download page.
    let Some(update) = update.filter(|u| u.version == version) else {
        return Ok(false);
    };
    let mut started = false;
    update
        .download_and_install(
            |chunk, total| {
                if !started {
                    started = true;
                    let _ = on_event.send(InstallEvent::Started { content_length: total });
                }
                let _ = on_event.send(InstallEvent::Progress { chunk_length: chunk });
            },
            || {
                let _ = on_event.send(InstallEvent::Finished);
            },
        )
        .await
        .map_err(|e| e.to_string())?;
    Ok(true)
}

#[cfg(test)]
mod tests {
    use super::valid;

    #[test]
    fn versions_in_url() {
        assert!(valid("0.1.0-beta.6"));
        assert!(valid("1.2.3"));
        assert!(!valid("1.2"));
        assert!(!valid("1.2.3/../x"));
        assert!(!valid("1.2.3?a=b"));
        assert!(!valid("v1.2.3"));
        assert!(!valid(""));
    }
}
