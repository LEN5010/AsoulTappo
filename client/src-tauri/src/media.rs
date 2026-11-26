//! Bundled pages and assets for the macOS webview, with byte ranges.
//!
//! Tauri's own `tauri://` handler answers every request with the whole file. WebKit loads a
//! video in ranges: without them each card video is sent in full several times over, cards stay
//! blank for seconds and the abandoned requests pile up. This handler takes the place of the
//! built-in one and answers `Range` requests with the part asked for.

use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};

use tauri::http::{header, Request, Response, StatusCode};
use tauri::{AppHandle, Runtime, UriSchemeContext, UriSchemeResponder};

/// Unpacked videos kept for the ranges that follow the first request.
const KEPT_VIDEOS: usize = 8;
static VIDEOS: Mutex<Vec<(String, Arc<Vec<u8>>)>> = Mutex::new(Vec::new());
static VIDEO_CACHE_GEN: AtomicU64 = AtomicU64::new(0);

enum AssetBytes {
    Owned(Vec<u8>),
    Shared(Arc<Vec<u8>>),
}

impl AssetBytes {
    fn len(&self) -> usize {
        match self {
            Self::Owned(v) => v.len(),
            Self::Shared(v) => v.len(),
        }
    }

    fn slice(&self, start: usize, end: usize) -> Vec<u8> {
        match self {
            Self::Owned(v) => v[start..=end].to_vec(),
            Self::Shared(v) => v[start..=end].to_vec(),
        }
    }

    fn into_vec(self) -> Vec<u8> {
        match self {
            Self::Owned(v) => v,
            Self::Shared(v) => v.as_ref().clone(),
        }
    }
}

/// Drops cached unpacked videos (e.g. when the panel is hidden) so their buffers are freed immediately.
pub fn clear_video_cache() {
    if let Ok(mut videos) = VIDEOS.lock() {
        VIDEO_CACHE_GEN.fetch_add(1, Ordering::AcqRel);
        videos.clear();
        videos.shrink_to_fit();
    }
}

pub fn serve<R: Runtime>(ctx: UriSchemeContext<'_, R>, request: Request<Vec<u8>>, responder: UriSchemeResponder) {
    let app = ctx.app_handle().clone();
    // Asset decompression and range copies are synchronous work; keep them off Tokio's async workers.
    tauri::async_runtime::spawn_blocking(move || {
        responder.respond(respond(&app, &request));
    });
}

fn respond<R: Runtime>(app: &AppHandle<R>, request: &Request<Vec<u8>>) -> Response<Vec<u8>> {
    let uri = request.uri().to_string();
    let path = uri.split(['?', '#']).next().unwrap_or_default();
    // Decoded as Tauri's own handler does: a file name with spaces or non-ASCII letters arrives escaped.
    let path = request_path(path);
    let Some((bytes, mime, csp)) = load(app, &path) else {
        return plain(StatusCode::NOT_FOUND);
    };

    let mut builder = Response::builder()
        .header(header::CONTENT_TYPE, mime)
        .header(header::ACCESS_CONTROL_ALLOW_ORIGIN, "tauri://localhost")
        .header(header::ACCEPT_RANGES, "bytes");
    if let Some(csp) = csp {
        builder = builder.header(header::CONTENT_SECURITY_POLICY, csp);
    }
    let total = bytes.len();
    let range = request.headers().get(header::RANGE).and_then(|v| v.to_str().ok());
    let response = match range.map(|r| parse_range(r, total as u64)) {
        None => builder.status(StatusCode::OK).body(bytes.into_vec()),
        Some(Some((start, end))) => builder
            .status(StatusCode::PARTIAL_CONTENT)
            .header(header::CONTENT_RANGE, format!("bytes {start}-{end}/{total}"))
            .body(bytes.slice(start as usize, end as usize)),
        Some(None) => builder
            .status(StatusCode::RANGE_NOT_SATISFIABLE)
            .header(header::CONTENT_RANGE, format!("bytes */{total}"))
            .body(Vec::new()),
    };
    response.unwrap_or_else(|_| plain(StatusCode::INTERNAL_SERVER_ERROR))
}

fn plain(status: StatusCode) -> Response<Vec<u8>> {
    let mut response = Response::new(Vec::new());
    *response.status_mut() = status;
    response
}

/// The asset's bytes, mime type and CSP header. Non-mp4 assets bypass the video cache with zero copy;
/// videos are unpacked once and deduplicated in `VIDEOS`.
fn load<R: Runtime>(app: &AppHandle<R>, path: &str) -> Option<(AssetBytes, String, Option<String>)> {
    if path.ends_with(".mp4") {
        let gen = VIDEO_CACHE_GEN.load(Ordering::Acquire);
        if let Some(bytes) = kept(path) {
            return Some((AssetBytes::Shared(bytes), "video/mp4".into(), None));
        }
        let asset = app.asset_resolver().get(path.to_string())?;
        let bytes = cache_video(path, asset.bytes, gen);
        return Some((AssetBytes::Shared(bytes), asset.mime_type, asset.csp_header));
    }
    let asset = app.asset_resolver().get(path.to_string())?;
    Some((AssetBytes::Owned(asset.bytes), asset.mime_type, asset.csp_header))
}

fn insert_video(videos: &mut Vec<(String, Arc<Vec<u8>>)>, path: &str, data: Vec<u8>) -> Arc<Vec<u8>> {
    if let Some(at) = videos.iter().position(|(p, _)| p == path) {
        let entry = videos.remove(at);
        let existing = entry.1.clone();
        videos.push(entry);
        return existing;
    }
    let bytes = Arc::new(data);
    if videos.len() >= KEPT_VIDEOS {
        videos.remove(0);
    }
    videos.push((path.to_string(), bytes.clone()));
    bytes
}

fn cache_video(path: &str, data: Vec<u8>, gen: u64) -> Arc<Vec<u8>> {
    if let Ok(mut videos) = VIDEOS.lock() {
        if VIDEO_CACHE_GEN.load(Ordering::Acquire) == gen {
            return insert_video(&mut videos, path, data);
        }
    }
    Arc::new(data)
}

fn kept(path: &str) -> Option<Arc<Vec<u8>>> {
    let mut videos = VIDEOS.lock().ok()?;
    let at = videos.iter().position(|(p, _)| p == path)?;
    // Most recently used last, so the oldest is dropped first.
    let entry = videos.remove(at);
    let bytes = entry.1.clone();
    videos.push(entry);
    Some(bytes)
}

/// The asset path of a `tauri://localhost/...` URI without query, percent-decoded.
fn request_path(uri: &str) -> String {
    let path = uri.strip_prefix("tauri://localhost").unwrap_or_default();
    percent_encoding::percent_decode_str(path).decode_utf8_lossy().into_owned()
}

/// The first and last byte of a single `bytes=` range within `len` bytes; `None` when it cannot be served.
fn parse_range(value: &str, len: u64) -> Option<(u64, u64)> {
    let spec = value.trim().strip_prefix("bytes=")?;
    if len == 0 || spec.contains(',') {
        return None;
    }
    let (first, last) = spec.split_once('-')?;
    let (first, last) = (first.trim(), last.trim());
    if first.is_empty() {
        // The last n bytes.
        let n: u64 = last.parse().ok()?;
        return (n > 0).then(|| (len.saturating_sub(n), len - 1));
    }
    let start: u64 = first.parse().ok()?;
    let end = if last.is_empty() { len - 1 } else { last.parse::<u64>().ok()?.min(len - 1) };
    (start <= end).then_some((start, end))
}

#[cfg(test)]
mod tests {
    use super::{parse_range, request_path};

    #[test]
    fn decodes_escaped_paths() {
        assert_eq!(request_path("tauri://localhost/assets/a.mp4"), "/assets/a.mp4");
        assert_eq!(request_path("tauri://localhost/assets/%E4%B9%83%E7%90%B3%20a.webp"), "/assets/乃琳 a.webp");
        assert_eq!(request_path("http://elsewhere/x"), "");
    }

    #[test]
    fn reads_the_three_range_forms() {
        assert_eq!(parse_range("bytes=0-1", 100), Some((0, 1)));
        assert_eq!(parse_range("bytes=10-", 100), Some((10, 99)));
        assert_eq!(parse_range("bytes=-20", 100), Some((80, 99)));
    }

    #[test]
    fn clips_the_end_to_the_file() {
        assert_eq!(parse_range("bytes=90-500", 100), Some((90, 99)));
        assert_eq!(parse_range("bytes=-500", 100), Some((0, 99)));
    }

    #[test]
    fn refuses_what_it_cannot_serve() {
        assert_eq!(parse_range("bytes=100-", 100), None);
        assert_eq!(parse_range("bytes=5-2", 100), None);
        assert_eq!(parse_range("bytes=0-1,5-6", 100), None);
        assert_eq!(parse_range("items=0-1", 100), None);
        assert_eq!(parse_range("bytes=0-1", 0), None);
    }
}
