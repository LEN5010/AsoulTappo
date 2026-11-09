//! Installs one exact version from its own GitHub release.
//!
//! The endpoint in tauri.conf.json is `releases/latest`, which GitHub never points at a pre-release,
//! so every beta was offered and then never found. This asks the release tagged `v<version>` instead.
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, Instant};

use serde::Serialize;
use tauri::ipc::Channel;
use tauri_plugin_updater::UpdaterExt;

const RELEASE_BASE: &str = "https://github.com/LEN5010/AsoulTappo/releases/download";
/// Limit for finding the release. Not set on the updater: its timeout also caps the whole download,
/// which fails every package that takes longer than that to arrive.
const CHECK_TIMEOUT: Duration = Duration::from_secs(15);
/// The download has no total limit; it fails after this long without receiving a byte.
const STALL_LIMIT: Duration = Duration::from_secs(60);
const STALL_POLL: Duration = Duration::from_secs(5);

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
    // The dialog shows one line for every failure; the log keeps which one it was.
    let result = install(app, &version, on_event).await;
    match &result {
        Err(e) => applog!("update", "{version}: {e}"),
        Ok(false) => applog!("update", "{version}: release not found, sending to the download page"),
        Ok(true) => {}
    }
    result
}

async fn install(app: tauri::AppHandle, version: &str, on_event: Channel<InstallEvent>) -> Result<bool, String> {
    if !valid(version) {
        return Err("bad version".into());
    }
    let url = format!("{RELEASE_BASE}/v{version}/latest.json")
        .parse()
        .map_err(|e: url::ParseError| e.to_string())?;
    let updater = app
        .updater_builder()
        .endpoints(vec![url])
        .map_err(|e| e.to_string())?
        .build()
        .map_err(|e| e.to_string())?;
    let update = tokio::time::timeout(CHECK_TIMEOUT, updater.check())
        .await
        .map_err(|_| "release check timed out".to_string())?
        .map_err(|e| e.to_string())?;
    // Missing, or not the version offered (the release still uploading): the caller opens the download page.
    let Some(update) = update.filter(|u| u.version == version) else {
        return Ok(false);
    };
    let start = Instant::now();
    // Milliseconds after `start` when the last chunk arrived.
    let last_chunk = AtomicU64::new(0);
    let mut started = false;
    let download = update.download_and_install(
        |chunk, total| {
            last_chunk.store(start.elapsed().as_millis() as u64, Ordering::Relaxed);
            if !started {
                started = true;
                let _ = on_event.send(InstallEvent::Started { content_length: total });
            }
            let _ = on_event.send(InstallEvent::Progress { chunk_length: chunk });
        },
        || {
            // Downloaded: verifying and starting the installer can take long (antivirus), and is not a stall.
            last_chunk.store(u64::MAX, Ordering::Relaxed);
            let _ = on_event.send(InstallEvent::Finished);
        },
    );
    let mut download = std::pin::pin!(download);
    loop {
        match tokio::time::timeout(STALL_POLL, download.as_mut()).await {
            Ok(done) => {
                done.map_err(|e| e.to_string())?;
                return Ok(true);
            }
            Err(_) => {
                let quiet = start.elapsed().saturating_sub(Duration::from_millis(last_chunk.load(Ordering::Relaxed)));
                // Dropping the future cancels the download.
                if quiet >= STALL_LIMIT {
                    return Err("download stalled".into());
                }
            }
        }
    }
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
