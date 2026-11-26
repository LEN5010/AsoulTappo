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

/// The older and the current file, in that order, after flushing what is written.
fn read_all() -> std::io::Result<Vec<u8>> {
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
    Ok(out)
}

/// Copy the older and the current file, in that order, into one `.txt` in `to_dir`.
pub fn export(to_dir: &Path) -> std::io::Result<PathBuf> {
    let out = read_all()?;
    let path = to_dir.join(format!(
        "{}-log-{}.txt",
        crate::edition::PRODUCT_NAME,
        chrono::Local::now().format("%Y%m%d-%H%M%S")
    ));
    std::fs::write(&path, out)?;
    Ok(path)
}

/// The latest part of the log, at most `max` bytes, for a feedback the player sends it with; "" before the log started.
pub fn tail(max: usize) -> String {
    read_all().map(|bytes| tail_of(bytes, max)).unwrap_or_default()
}

/// The last `max` bytes of `bytes`, from the first whole line on when cut.
fn tail_of(mut bytes: Vec<u8>, max: usize) -> String {
    if bytes.len() > max {
        bytes.drain(..bytes.len() - max);
        match bytes.iter().position(|&b| b == b'\n') {
            Some(end) => drop(bytes.drain(..=end)),
            None => bytes.clear(),
        }
    }
    String::from_utf8_lossy(&bytes).into_owned()
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

#[cfg(test)]
mod tests {
    use super::tail_of;

    #[test]
    fn tail_keeps_whole_lines_within_the_limit() {
        let log = b"first line\nsecond line\nthird\n".to_vec();
        assert_eq!(tail_of(log.clone(), 100), "first line\nsecond line\nthird\n");
        assert_eq!(tail_of(log.clone(), 14), "third\n");
        assert_eq!(tail_of(log, 3), "");
    }

    #[test]
    fn tail_never_splits_a_character() {
        let log = "开始\n桌宠\n".as_bytes().to_vec();
        assert_eq!(tail_of(log, 8), "桌宠\n");
    }

    #[test]
    fn tail_reads_whole_lines_from_rotated_log_files() {
        use super::{tail, Log, CURRENT, LOG, PREVIOUS};
        use std::fs;

        let dir = std::env::temp_dir().join(format!("asoultappo-tail-{}", std::process::id()));
        fs::create_dir_all(&dir).unwrap();
        let previous = dir.join(PREVIOUS);
        let current = dir.join(CURRENT);
        // The fixture owns both files. Other tests may log while these bytes are being checked.
        let saved = LOG.lock().unwrap().replace(Log { dir: dir.clone(), file: None, written: 0 });
        fs::write(&previous, b"").unwrap();
        fs::write(&current, b"").unwrap();
        assert_eq!(tail(100), "");

        fs::write(&current, b"short\n").unwrap();
        assert_eq!(tail(100), "short\n");
        fs::write(&current, format!("{}\nlast\n", "x".repeat(32_768))).unwrap();
        assert_eq!(tail(8), "last\n");

        // The rotated file ends inside 桌. Decode only after joining the two byte ranges.
        let text = "前文\n桌宠\n";
        let split = "前文\n".len() + 1;
        fs::write(&previous, &text.as_bytes()[..split]).unwrap();
        fs::write(&current, &text.as_bytes()[split..]).unwrap();
        assert_eq!(tail(10), "桌宠\n");
        assert_eq!(tail(6), "");

        fs::write(&previous, b"old\r\n").unwrap();
        fs::write(&current, b"one\ntwo\r\nthree").unwrap();
        assert_eq!(tail(100), "old\r\none\ntwo\r\nthree");
        assert_eq!(tail(13), "two\r\nthree");
        assert_eq!(tail(6), "three");
        assert_eq!(tail(4), "");

        *LOG.lock().unwrap() = saved;
        fs::remove_dir_all(dir).unwrap();
    }
}
