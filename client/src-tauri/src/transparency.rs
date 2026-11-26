//! Puts the desk overlay's transparency back (Windows).
//!
//! The overlay is a transparent topmost window over the work area. tao makes it transparent once, when the window is
//! created (DwmEnableBlurBehindWindow with an empty region, tao's `on_create`), and WebView2 draws the page over a
//! transparent default background. Players report that a while into a full-screen game the game stops and everything
//! above the taskbar turns black, with the pet still drawn on top, until the app quits: one of the two has lost its
//! transparency, most likely when the graphics driver was reset. Both are set again here whenever that may have
//! happened: WebView2's GPU (or another) process exited, the display mode or composition changed, the pet was shown
//! again. Setting them again changes nothing while they hold. Each step is logged, so the next report comes with the
//! moments that led to it.

use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::WebviewWindow;
use webview2_com::Microsoft::Web::WebView2::Win32::{
    ICoreWebView2Controller, ICoreWebView2Controller2, ICoreWebView2ProcessFailedEventArgs2, COREWEBVIEW2_COLOR,
    COREWEBVIEW2_PROCESS_FAILED_KIND, COREWEBVIEW2_PROCESS_FAILED_KIND_BROWSER_PROCESS_EXITED,
    COREWEBVIEW2_PROCESS_FAILED_KIND_FRAME_RENDER_PROCESS_EXITED, COREWEBVIEW2_PROCESS_FAILED_KIND_GPU_PROCESS_EXITED,
    COREWEBVIEW2_PROCESS_FAILED_KIND_RENDER_PROCESS_EXITED,
    COREWEBVIEW2_PROCESS_FAILED_KIND_RENDER_PROCESS_UNRESPONSIVE,
    COREWEBVIEW2_PROCESS_FAILED_KIND_UTILITY_PROCESS_EXITED, COREWEBVIEW2_PROCESS_FAILED_REASON,
};
use webview2_com::{take_pwstr, ProcessFailedEventHandler};
use windows_core::{Interface, PWSTR};
use windows_sys::Win32::Foundation::HWND;
use windows_sys::Win32::Graphics::Dwm::{DwmEnableBlurBehindWindow, DWM_BB_BLURREGION, DWM_BB_ENABLE, DWM_BLURBEHIND};
use windows_sys::Win32::Graphics::Gdi::{CreateRectRgn, DeleteObject, RedrawWindow, RDW_FRAME, RDW_INVALIDATE};

/// When a restore runs after its cause: at once, and again once a restarted GPU process or a settled display mode
/// may have undone it.
const AGAIN: [Duration; 3] = [Duration::ZERO, Duration::from_secs(1), Duration::from_secs(3)];
/// A burst of causes (a display mode flipping back and forth) queues no more restores than this.
const MAX_PENDING: usize = 12;

/// Restores waiting for their time, with their cause. The hit-test thread runs them (`due`).
static PENDING: Mutex<Vec<(Instant, String)>> = Mutex::new(Vec::new());
static HAS_PENDING: AtomicBool = AtomicBool::new(false);
/// Causes not logged yet and when they came, and how many more came past `MAX_PENDING`. The hit-test thread logs them
/// (`due`): the window's message handler, which asks for most restores, does not wait for the log file.
static NOTED: Mutex<Vec<(Instant, String)>> = Mutex::new(Vec::new());
static UNNOTED: AtomicUsize = AtomicUsize::new(0);

/// Queues restores for [why]. Cheap and non-blocking, so the window's message handler may call it.
pub fn request(why: &str) {
    let now = Instant::now();
    if let Ok(mut noted) = NOTED.lock() {
        if noted.len() < MAX_PENDING {
            noted.push((now, why.to_string()));
        } else {
            UNNOTED.fetch_add(1, Ordering::Relaxed);
        }
    }
    if let Ok(mut pending) = PENDING.lock() {
        for after in AGAIN {
            if pending.len() < MAX_PENDING {
                pending.push((now + after, why.to_string()));
            }
        }
        HAS_PENDING.store(true, Ordering::Release);
    }
}

/// The cause of a restore whose time has come, taken off the queue. Logs the causes that came since the last call.
pub fn due() -> Option<String> {
    if !HAS_PENDING.load(Ordering::Acquire) {
        return None;
    }
    let now = Instant::now();
    let noted = NOTED.lock().map(|mut noted| std::mem::take(&mut *noted)).unwrap_or_default();
    for (at, why) in noted {
        applog!("overlay", "transparency to restore: {why} ({} ms ago)", now.saturating_duration_since(at).as_millis());
    }
    let unnoted = UNNOTED.swap(0, Ordering::Relaxed);
    if unnoted > 0 {
        applog!("overlay", "transparency to restore: {unnoted} more cause(s) not listed");
    }
    let mut pending = PENDING.lock().ok()?;
    let at = pending.iter().position(|(when, _)| *when <= now)?;
    let why = pending.remove(at).1;
    if pending.is_empty() {
        HAS_PENDING.store(false, Ordering::Release);
    }
    Some(why)
}

/// Sets the window's transparency and the web view's transparent background again, on the main thread.
pub fn restore(window: &WebviewWindow, why: &str) {
    let shown = window.is_visible().unwrap_or(false);
    let hwnd = match window.hwnd() {
        Ok(h) => h.0 as isize,
        Err(e) => {
            applog!("overlay", "transparency not restored ({why}): no window handle: {e}");
            return;
        }
    };
    let cause = why.to_string();
    let sent = window.with_webview(move |webview| {
        // SAFETY: Tauri runs this on the main thread with the overlay's live window and web view.
        let blur = unsafe { blur_behind(hwnd as HWND) };
        let background = unsafe { clear_background(&webview.controller()) };
        unsafe {
            RedrawWindow(hwnd as HWND, std::ptr::null(), std::ptr::null_mut(), RDW_INVALIDATE | RDW_FRAME);
        }
        applog!(
            "overlay",
            "transparency restored ({cause}, window {}): blur behind {}, web view background {}",
            if shown { "shown" } else { "hidden" },
            outcome(&blur),
            outcome(&background)
        );
    });
    if let Err(e) = sent {
        applog!("overlay", "transparency not restored ({why}): {e}");
    }
}

fn outcome(result: &Result<(), String>) -> String {
    match result {
        Ok(()) => "set".into(),
        Err(e) => format!("failed ({e})"),
    }
}

/// tao's own call (window.rs `on_create`): blur behind an empty region, which leaves the window fully transparent.
unsafe fn blur_behind(hwnd: HWND) -> Result<(), String> {
    let region = unsafe { CreateRectRgn(0, 0, -1, -1) };
    let bb = DWM_BLURBEHIND {
        dwFlags: DWM_BB_ENABLE | DWM_BB_BLURREGION,
        fEnable: 1,
        hRgnBlur: region,
        fTransitionOnMaximized: 0,
    };
    let hr = unsafe { DwmEnableBlurBehindWindow(hwnd, &bb) };
    unsafe { DeleteObject(region) };
    if hr < 0 {
        Err(format!("{hr:#010x}"))
    } else {
        Ok(())
    }
}

/// wry's transparent background (webview2/mod.rs `set_background_color` with alpha 0).
unsafe fn clear_background(controller: &ICoreWebView2Controller) -> Result<(), String> {
    let controller2: ICoreWebView2Controller2 = controller.cast().map_err(|e| e.to_string())?;
    unsafe { controller2.SetDefaultBackgroundColor(COREWEBVIEW2_COLOR { R: 0, G: 0, B: 0, A: 0 }) }
        .map_err(|e| e.to_string())
}

/// Logs each WebView2 process failure of [window]'s web view and queues restores after it.
pub fn watch_process_failures(window: &WebviewWindow) {
    let sent = window.with_webview(|webview| {
        let handler = ProcessFailedEventHandler::create(Box::new(|_, args| {
            let Some(args) = args else { return Ok(()) };
            let mut kind = COREWEBVIEW2_PROCESS_FAILED_KIND::default();
            // SAFETY: WebView2 calls this on the main thread with live event arguments.
            unsafe { args.ProcessFailedKind(&mut kind)? };
            let mut detail = String::new();
            if let Ok(args2) = args.cast::<ICoreWebView2ProcessFailedEventArgs2>() {
                let mut reason = COREWEBVIEW2_PROCESS_FAILED_REASON::default();
                let mut code = 0i32;
                let mut what = PWSTR::null();
                // SAFETY: as above; the description is a CoTaskMem string that take_pwstr frees (null gives "").
                unsafe {
                    let _ = args2.Reason(&mut reason);
                    let _ = args2.ExitCode(&mut code);
                    let _ = args2.ProcessDescription(&mut what);
                }
                let what = take_pwstr(what);
                let what = if what.is_empty() { what } else { format!(", {what}") };
                detail = format!(", reason {}, exit code {code:#x}{what}", reason.0);
            }
            let name = kind_name(kind);
            applog!("webview", "process failed: {name}{detail}");
            request(&format!("web view {name}"));
            Ok(())
        }));
        let mut token = 0i64;
        // SAFETY: on the main thread with the overlay's live controller; the handler stays registered for the
        // window's life.
        let added = unsafe {
            webview.controller().CoreWebView2().and_then(|core| core.add_ProcessFailed(&handler, &mut token))
        };
        if let Err(e) = added {
            applog!("webview", "process failures not watched: {e}");
        }
    });
    if let Err(e) = sent {
        applog!("webview", "process failures not watched: {e}");
    }
}

fn kind_name(kind: COREWEBVIEW2_PROCESS_FAILED_KIND) -> String {
    match kind {
        COREWEBVIEW2_PROCESS_FAILED_KIND_GPU_PROCESS_EXITED => "GPU process exited".into(),
        COREWEBVIEW2_PROCESS_FAILED_KIND_BROWSER_PROCESS_EXITED => "browser process exited".into(),
        COREWEBVIEW2_PROCESS_FAILED_KIND_RENDER_PROCESS_EXITED => "render process exited".into(),
        COREWEBVIEW2_PROCESS_FAILED_KIND_FRAME_RENDER_PROCESS_EXITED => "frame render process exited".into(),
        COREWEBVIEW2_PROCESS_FAILED_KIND_RENDER_PROCESS_UNRESPONSIVE => "render process unresponsive".into(),
        COREWEBVIEW2_PROCESS_FAILED_KIND_UTILITY_PROCESS_EXITED => "utility process exited".into(),
        other => format!("process kind {} exited", other.0),
    }
}
