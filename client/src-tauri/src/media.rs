//! Bundled pages and assets for the macOS webview, with byte ranges.
//!
//! Tauri's own `tauri://` handler answers every request with the whole file. WebKit loads a
//! video in ranges: without them each card video is sent in full several times over, cards stay
//! blank for seconds and the abandoned requests pile up. This handler takes the place of the
//! built-in one and answers `Range` requests with the part asked for.

use std::sync::{Arc, Mutex};

use tauri::http::{header, Request, Response, StatusCode};
use tauri::{AppHandle, Runtime, UriSchemeContext, UriSchemeResponder};

/// Unpacked videos kept for the ranges that follow the first request.
const KEPT_VIDEOS: usize = 8;
static VIDEOS: Mutex<Vec<(String, Arc<Vec<u8>>)>> = Mutex::new(Vec::new());

pub fn serve<R: Runtime>(ctx: UriSchemeContext<'_, R>, request: Request<Vec<u8>>, responder: UriSchemeResponder) {
    let app = ctx.app_handle().clone();
    tauri::async_runtime::spawn(async move {
        responder.respond(respond(&app, &request));
    });
}

fn respond<R: Runtime>(app: &AppHandle<R>, request: &Request<Vec<u8>>) -> Response<Vec<u8>> {
    let uri = request.uri().to_string();
    let path = uri.split(['?', '#']).next().unwrap_or_default();
    let path = path.strip_prefix("tauri://localhost").unwrap_or_default().to_string();
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
    let range = request.headers().get(header::RANGE).and_then(|v| v.to_str().ok());
    let response = match range.map(|r| parse_range(r, bytes.len() as u64)) {
        None => builder.status(StatusCode::OK).body(bytes.to_vec()),
        Some(Some((start, end))) => builder
            .status(StatusCode::PARTIAL_CONTENT)
            .header(header::CONTENT_RANGE, format!("bytes {start}-{end}/{}", bytes.len()))
            .body(bytes[start as usize..=end as usize].to_vec()),
        Some(None) => builder
            .status(StatusCode::RANGE_NOT_SATISFIABLE)
            .header(header::CONTENT_RANGE, format!("bytes */{}", bytes.len()))
            .body(Vec::new()),
    };
    response.unwrap_or_else(|_| plain(StatusCode::INTERNAL_SERVER_ERROR))
}

fn plain(status: StatusCode) -> Response<Vec<u8>> {
    let mut response = Response::new(Vec::new());
    *response.status_mut() = status;
    response
}

/// The asset's bytes, mime type and CSP header. Videos are unpacked once and kept.
fn load<R: Runtime>(app: &AppHandle<R>, path: &str) -> Option<(Arc<Vec<u8>>, String, Option<String>)> {
    if let Some(bytes) = kept(path) {
        return Some((bytes, "video/mp4".into(), None));
    }
    let asset = app.asset_resolver().get(path.to_string())?;
    let bytes = Arc::new(asset.bytes);
    if path.ends_with(".mp4") {
        if let Ok(mut videos) = VIDEOS.lock() {
            if videos.len() >= KEPT_VIDEOS {
                videos.remove(0);
            }
            videos.push((path.to_string(), bytes.clone()));
        }
    }
    Some((bytes, asset.mime_type, asset.csp_header))
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
    use super::parse_range;

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
