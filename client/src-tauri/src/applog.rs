//! Plain-text log that players export from the settings page.
//!
//! Lines go to `<app log dir>/asoultappo.log`. Past `MAX_BYTES` the file becomes
//! `asoultappo.old.log` and a new one starts, so at most about twice that is kept.
//! Like the rest of the app it never records which key was pressed: only counts,
//! states and errors.

use std::fs::{File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Mutex;

/// Debug build (`--features debug-log`): extra lines through `debuglog!`, and a larger file.
pub const DEBUG: bool = cfg!(feature = "debug-log");
const MAX_BYTES: u64 = if DEBUG { 8 * 1024 * 1024 } else { 1024 * 1024 };
const CURRENT: &str = "asoultappo.log";
const PREVIOUS: &str = "asoultappo.old.log";

struct Log {
    dir: PathBuf,
    file: Option<File>,
    written: u64,
}

impl Log {
    fn rotate(&mut self) {
        self.file = None;
        let _ = std::fs::rename(self.dir.join(CURRENT), self.dir.join(PREVIOUS));
        self.file = OpenOptions::new().create(true).append(true).open(self.dir.join(CURRENT)).ok();
        self.written = 0;
    }

    fn append(&mut self, line: &str) {
        if self.written + line.len() as u64 > MAX_BYTES {
            self.rotate();
        }
        if let Some(file) = self.file.as_mut() {
            if file.write_all(line.as_bytes()).is_ok() {
                self.written += line.len() as u64;
            }
        }
    }
}

static LOG: Mutex<Option<Log>> = Mutex::new(None);

/// Start writing to `dir` (created when missing). Lines written before this are dropped.
pub fn init(dir: PathBuf) {
    let _ = std::fs::create_dir_all(&dir);
    let path = dir.join(CURRENT);
    let written = std::fs::metadata(&path).map(|m| m.len()).unwrap_or(0);
    let file = OpenOptions::new().create(true).append(true).open(&path).ok();
    let mut log = LOG.lock().unwrap_or_else(|e| e.into_inner());
    *log = Some(Log { dir, file, written });
}

fn line(tag: &str, msg: &str) -> String {
    format!("{} [{tag}] {msg}\n", chrono::Local::now().format("%Y-%m-%d %H:%M:%S%.3f"))
}

/// Append one line: local time, `[tag]`, message.
pub fn write(tag: &str, msg: &str) {
    let line = line(tag, msg);
    let mut log = LOG.lock().unwrap_or_else(|e| e.into_inner());
    if let Some(log) = log.as_mut() {
        log.append(&line);
    }
}

/// For the panic hook: skips the line rather than wait, since the panic may have
/// happened while this thread held the lock.
pub fn write_now(tag: &str, msg: &str) {
    let line = line(tag, msg);
    if let Ok(mut log) = LOG.try_lock() {
        if let Some(log) = log.as_mut() {
            log.append(&line);
        }
    }
}

/// Copy the older and the current file, in that order, into one `.txt` in `to_dir`.
pub fn export(to_dir: &Path) -> std::io::Result<PathBuf> {
    let dir = {
        let mut log = LOG.lock().unwrap_or_else(|e| e.into_inner());
        let Some(log) = log.as_mut() else {
            return Err(std::io::Error::new(std::io::ErrorKind::NotFound, "log not started"));
        };
        if let Some(file) = log.file.as_mut() {
            let _ = file.flush();
        }
        log.dir.clone()
    };
    let mut out = Vec::new();
    for name in [PREVIOUS, CURRENT] {
        if let Ok(bytes) = std::fs::read(dir.join(name)) {
            out.extend(bytes);
        }
    }
    let path = to_dir.join(format!("AsoulTappo-log-{}.txt", chrono::Local::now().format("%Y%m%d-%H%M%S")));
    std::fs::write(&path, out)?;
    Ok(path)
}

/// `debuglog!("tag", "format {}", args)`: like `applog!`, only in the debug build.
#[macro_export]
macro_rules! debuglog {
    ($tag:expr, $($arg:tt)*) => {
        if $crate::applog::DEBUG {
            $crate::applog::write($tag, &format!($($arg)*))
        }
    };
}

/// `applog!("tag", "format {}", args)`: format and append one line.
#[macro_export]
macro_rules! applog {
    ($tag:expr, $($arg:tt)*) => {
        $crate::applog::write($tag, &format!($($arg)*))
    };
}
