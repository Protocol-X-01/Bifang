use portable_pty::{native_pty_system, Child, CommandBuilder, MasterPty, PtySize};
use serde::Serialize;
use std::collections::VecDeque;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::{Arc, Condvar, Mutex};

const BUFFER_LIMIT: usize = 262_144;
const FRAME_LIMIT: usize = 16_384;
const INPUT_LIMIT: usize = 16_384;

#[derive(Serialize)]
pub struct TerminalOpened {
    pub id: u32,
    pub directory: String,
    pub program: String,
}

#[derive(Serialize)]
pub struct TerminalFrame {
    pub data: Vec<u8>,
    pub exited: bool,
    pub exit_code: Option<u32>,
}

#[derive(Default)]
struct OutputBuffer {
    bytes: VecDeque<u8>,
    eof: bool,
    closed: bool,
}

struct Session {
    id: u32,
    master: Mutex<Box<dyn MasterPty + Send>>,
    writer: Mutex<Box<dyn Write + Send>>,
    child: Mutex<Box<dyn Child + Send + Sync>>,
    output: Arc<(Mutex<OutputBuffer>, Condvar)>,
}

impl Session {
    fn stop(&self) -> Result<(), String> {
        let (buffer, notification) = &*self.output;
        if let Ok(mut output) = buffer.lock() {
            output.closed = true;
            notification.notify_all();
        }
        let mut child = self
            .child
            .lock()
            .map_err(|_| "Terminal process unavailable")?;
        if child
            .try_wait()
            .map_err(|_| "Could not inspect terminal process")?
            .is_none()
        {
            child
                .kill()
                .map_err(|_| "Could not stop terminal process")?;
            child
                .wait()
                .map_err(|_| "Could not reap terminal process")?;
        }
        Ok(())
    }
}

impl Drop for Session {
    fn drop(&mut self) {
        let _ = self.stop();
    }
}

#[derive(Default)]
pub struct TerminalEngine {
    session: Mutex<Option<Arc<Session>>>,
    sequence: AtomicU32,
}

fn dimensions(rows: u16, cols: u16) -> Result<PtySize, String> {
    if !(1..=300).contains(&rows) || !(1..=500).contains(&cols) {
        return Err("Terminal dimensions must be within 300 rows and 500 columns".into());
    }
    Ok(PtySize {
        rows,
        cols,
        pixel_width: 0,
        pixel_height: 0,
    })
}

fn shell_command(directory: &Path) -> Result<(CommandBuilder, String), String> {
    #[cfg(target_os = "android")]
    let (mut command, program) = {
        let mut command = CommandBuilder::new("/system/bin/sh");
        command.arg("-i");
        (command, "/system/bin/sh".to_string())
    };
    #[cfg(all(unix, not(target_os = "android")))]
    let (mut command, program) = {
        let program = if Path::new("/bin/bash").is_file() {
            "/bin/bash"
        } else {
            "/bin/sh"
        };
        let mut command = CommandBuilder::new(program);
        if program == "/bin/bash" {
            command.args(["--noprofile", "--norc", "-i"]);
        } else {
            command.arg("-i");
        }
        (command, program.to_string())
    };
    #[cfg(windows)]
    let (mut command, program) = {
        let root = std::env::var_os("SystemRoot").ok_or("Windows SystemRoot is unavailable")?;
        let program = PathBuf::from(root).join("System32/WindowsPowerShell/v1.0/powershell.exe");
        if !program.is_absolute() || !program.is_file() {
            return Err("The system PowerShell installation is unavailable".into());
        }
        let mut command = CommandBuilder::new(&program);
        command.args(["-NoLogo", "-NoProfile"]);
        (command, program.to_string_lossy().into_owned())
    };
    command.env_clear();
    for name in [
        "HOME",
        "USERPROFILE",
        "SystemRoot",
        "WINDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
    ] {
        if let Some(value) = std::env::var_os(name) {
            command.env(name, value);
        }
    }
    #[cfg(all(unix, not(target_os = "android")))]
    command.env("PATH", "/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin");
    #[cfg(target_os = "android")]
    {
        command.env("PATH", "/system/bin:/system/xbin");
        command.env("HOME", directory);
        command.env("TMPDIR", directory.join(".tmp"));
    }
    #[cfg(windows)]
    {
        let root = std::env::var("SystemRoot").map_err(|_| "Windows SystemRoot is unavailable")?;
        command.env(
            "PATH",
            format!("{root}\\System32;{root}\\System32\\WindowsPowerShell\\v1.0"),
        );
        command.env("PATHEXT", ".COM;.EXE;.BAT;.CMD");
    }
    command.env("TERM", "xterm-256color");
    command.env("COLORTERM", "truecolor");
    command.env("HISTFILE", "/dev/null");
    command.env("INPUTRC", "/dev/null");
    command.env("PS1", "Bifang $ ");
    #[cfg(target_os = "android")]
    command.env("PS1", "Bifang ${PWD##*/} $ ");
    command.cwd(directory);
    Ok((command, program))
}

impl TerminalEngine {
    pub fn open(
        &self,
        path: &str,
        rows: u16,
        cols: u16,
        confirmed: bool,
    ) -> Result<TerminalOpened, String> {
        if !confirmed {
            return Err("Explicit local terminal confirmation is required".into());
        }
        let size = dimensions(rows, cols)?;
        let requested = PathBuf::from(path);
        if !requested.is_absolute() {
            return Err("Select an absolute project directory".into());
        }
        let directory = requested
            .canonicalize()
            .map_err(|_| "Project directory is unavailable")?;
        if !directory.is_dir() {
            return Err("Select a project directory".into());
        }
        let mut active = self
            .session
            .lock()
            .map_err(|_| "Terminal state unavailable")?;
        if active.is_some() {
            return Err("Close the existing local terminal before opening another".into());
        }
        let previous = self
            .sequence
            .fetch_update(Ordering::Relaxed, Ordering::Relaxed, |value| {
                value.checked_add(1)
            })
            .map_err(|_| "Terminal session sequence exhausted; restart the application")?;
        let id = previous + 1;
        let (command, program) = shell_command(&directory)?;
        let pair = native_pty_system()
            .openpty(size)
            .map_err(|_| "The operating system could not create a PTY")?;
        let reader = pair
            .master
            .try_clone_reader()
            .map_err(|_| "Could not open terminal output")?;
        let writer = pair
            .master
            .take_writer()
            .map_err(|_| "Could not open terminal input")?;
        let child = pair
            .slave
            .spawn_command(command)
            .map_err(|_| "Could not start the system shell")?;
        drop(pair.slave);
        let output = Arc::new((Mutex::new(OutputBuffer::default()), Condvar::new()));
        let output_reader = Arc::clone(&output);
        let session = Arc::new(Session {
            id,
            master: Mutex::new(pair.master),
            writer: Mutex::new(writer),
            child: Mutex::new(child),
            output,
        });
        if std::thread::Builder::new()
            .name("bifang-pty-output".into())
            .spawn(move || read_output(reader, output_reader))
            .is_err()
        {
            session.stop()?;
            return Err("Could not start terminal output reader".into());
        }
        *active = Some(session);
        Ok(TerminalOpened {
            id,
            directory: directory.to_string_lossy().into_owned(),
            program,
        })
    }

    fn selected(&self, id: u32) -> Result<Arc<Session>, String> {
        self.session
            .lock()
            .map_err(|_| "Terminal state unavailable")?
            .as_ref()
            .filter(|session| session.id == id)
            .cloned()
            .ok_or("Terminal session is closed or changed".into())
    }

    pub fn write(&self, id: u32, data: Vec<u8>) -> Result<(), String> {
        if data.is_empty() || data.len() > INPUT_LIMIT {
            return Err("Terminal input must be between 1 and 16384 bytes".into());
        }
        let session = self.selected(id)?;
        let mut writer = session
            .writer
            .lock()
            .map_err(|_| "Terminal input unavailable")?;
        writer
            .write_all(&data)
            .map_err(|_| "Could not write to terminal")?;
        writer
            .flush()
            .map_err(|_| "Could not flush terminal input".to_string())
    }

    pub fn read(&self, id: u32) -> Result<TerminalFrame, String> {
        let session = self.selected(id)?;
        let status = session
            .child
            .lock()
            .map_err(|_| "Terminal process unavailable")?
            .try_wait()
            .map_err(|_| "Could not inspect terminal process")?;
        let (buffer, notification) = &*session.output;
        let mut output = buffer.lock().map_err(|_| "Terminal output unavailable")?;
        let count = output.bytes.len().min(FRAME_LIMIT);
        let data = output.bytes.drain(..count).collect();
        let exited = status.is_some() && output.eof && output.bytes.is_empty();
        notification.notify_all();
        Ok(TerminalFrame {
            data,
            exited,
            exit_code: status.map(|status| status.exit_code()),
        })
    }

    pub fn resize(&self, id: u32, rows: u16, cols: u16) -> Result<(), String> {
        let size = dimensions(rows, cols)?;
        self.selected(id)?
            .master
            .lock()
            .map_err(|_| "Terminal PTY unavailable")?
            .resize(size)
            .map_err(|_| "Could not resize terminal".to_string())
    }

    pub fn close(&self, id: u32) -> Result<(), String> {
        let mut active = self
            .session
            .lock()
            .map_err(|_| "Terminal state unavailable")?;
        if active.as_ref().is_some_and(|session| session.id == id) {
            let session = active.take().ok_or("Terminal state unavailable")?;
            drop(active);
            session.stop()?;
            return Ok(());
        }
        Err("Terminal session is closed or changed".into())
    }

    pub fn close_all(&self) {
        if let Ok(mut active) = self.session.lock() {
            if let Some(session) = active.take() {
                let _ = session.stop();
            }
        }
    }
}

fn read_output(mut reader: Box<dyn Read + Send>, output: Arc<(Mutex<OutputBuffer>, Condvar)>) {
    let (buffer, notification) = &*output;
    let mut chunk = [0u8; 8192];
    loop {
        let count = match reader.read(&mut chunk) {
            Ok(0) | Err(_) => break,
            Ok(count) => count,
        };
        let Ok(mut queue) = buffer.lock() else { return };
        while queue.bytes.len() + count > BUFFER_LIMIT && !queue.closed {
            let Ok(next) = notification.wait(queue) else {
                return;
            };
            queue = next;
        }
        if queue.closed {
            return;
        }
        queue.bytes.extend(&chunk[..count]);
    }
    if let Ok(mut queue) = buffer.lock() {
        queue.eof = true;
        notification.notify_all();
    }
}

impl Drop for TerminalEngine {
    fn drop(&mut self) {
        self.close_all();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{Duration, Instant};

    #[test]
    fn requires_confirmation_and_bounded_dimensions() {
        let engine = TerminalEngine::default();
        assert!(engine.open("/", 24, 80, false).is_err());
        assert!(engine.open("relative", 24, 80, true).is_err());
        assert!(dimensions(0, 80).is_err());
        assert!(dimensions(24, 501).is_err());
        assert!(engine.write(1, vec![0; INPUT_LIMIT + 1]).is_err());
        engine.sequence.store(u32::MAX, Ordering::Relaxed);
        for _ in 0..2 {
            let root = std::env::temp_dir();
            assert!(engine
                .open(root.to_str().unwrap(), 24, 80, true)
                .err()
                .unwrap()
                .contains("sequence exhausted"));
        }
    }

    #[test]
    fn shell_environment_does_not_copy_credentials_or_startup_hooks() {
        let (command, _) = shell_command(&std::env::temp_dir()).unwrap();
        for name in [
            "NEBIUS_API_KEY",
            "NVIDIA_API_KEY",
            "AWS_SECRET_ACCESS_KEY",
            "BASH_ENV",
            "ENV",
            "PYTHONPATH",
            "ZDOTDIR",
        ] {
            assert!(command.get_env(name).is_none());
        }
    }

    #[test]
    #[cfg(unix)]
    fn actual_pty_interaction_resize_exit_and_stale_handles() {
        let engine = TerminalEngine::default();
        let root = std::env::temp_dir();
        let opened = engine.open(root.to_str().unwrap(), 24, 80, true).unwrap();
        assert!(engine.open(root.to_str().unwrap(), 24, 80, true).is_err());
        engine.resize(opened.id, 32, 100).unwrap();
        engine
            .write(
                opened.id,
                b"printf '\\033[31mPTY_ACTUAL\\033[0m\\n'; stty size; exit 7\r".to_vec(),
            )
            .unwrap();
        let deadline = Instant::now() + Duration::from_secs(5);
        let mut output = Vec::new();
        let mut exited = false;
        while Instant::now() < deadline {
            let frame = engine.read(opened.id).unwrap();
            output.extend(frame.data);
            if frame.exited {
                assert_eq!(frame.exit_code, Some(7));
                exited = true;
                break;
            }
            std::thread::sleep(Duration::from_millis(10));
        }
        let text = String::from_utf8_lossy(&output);
        assert!(exited, "PTY did not exit: {text}");
        assert!(text.contains("\u{1b}[31mPTY_ACTUAL\u{1b}[0m"));
        assert!(text.contains("32 100"));
        engine.close(opened.id).unwrap();
        let next = engine.open(root.to_str().unwrap(), 24, 80, true).unwrap();
        assert!(engine.close(opened.id).is_err());
        assert!(engine.write(opened.id, b"exit\r".to_vec()).is_err());
        engine.close(next.id).unwrap();
    }

    #[test]
    #[cfg(unix)]
    fn actual_output_backpressure_is_bounded_and_close_unblocks_reader() {
        let engine = TerminalEngine::default();
        let root = std::env::temp_dir();
        let opened = engine.open(root.to_str().unwrap(), 24, 80, true).unwrap();
        engine
            .write(opened.id, b"python3 -c \"print('x'*1000000)\"\r".to_vec())
            .unwrap();
        std::thread::sleep(Duration::from_millis(300));
        let session = engine.selected(opened.id).unwrap();
        let bytes = session.output.0.lock().unwrap().bytes.len();
        assert!(bytes > 0 && bytes <= BUFFER_LIMIT);
        drop(session);
        let started = Instant::now();
        engine.close(opened.id).unwrap();
        assert!(started.elapsed() < Duration::from_secs(3));
        assert!(engine.read(opened.id).is_err());
    }

    #[test]
    #[cfg(unix)]
    fn actual_shell_does_not_inherit_fixture_secret() {
        std::env::set_var("BIFANG_PTY_FIXTURE_SECRET", "synthetic-test-value");
        let engine = TerminalEngine::default();
        let root = std::env::temp_dir();
        let opened = engine.open(root.to_str().unwrap(), 24, 80, true).unwrap();
        std::env::remove_var("BIFANG_PTY_FIXTURE_SECRET");
        engine.write(opened.id, b"if [ -z \"$BIFANG_PTY_FIXTURE_SECRET\" ]; then printf '\\033[35mNO_FIXTURE_SECRET\\033[0m\\n'; fi; exit\r".to_vec()).unwrap();
        let deadline = Instant::now() + Duration::from_secs(5);
        let mut output = Vec::new();
        while Instant::now() < deadline {
            let frame = engine.read(opened.id).unwrap();
            output.extend(frame.data);
            if frame.exited {
                break;
            }
            std::thread::sleep(Duration::from_millis(10));
        }
        engine.close(opened.id).unwrap();
        assert!(String::from_utf8_lossy(&output).contains("\u{1b}[35mNO_FIXTURE_SECRET\u{1b}[0m"));
    }

    #[test]
    #[cfg(target_os = "linux")]
    fn closing_shell_terminates_its_ordinary_background_job() {
        let engine = TerminalEngine::default();
        let root = std::env::temp_dir();
        let opened = engine.open(root.to_str().unwrap(), 24, 80, true).unwrap();
        engine
            .write(
                opened.id,
                b"sleep 60 & printf '__BACKGROUND:%s__\\n' $!; wait\r".to_vec(),
            )
            .unwrap();
        let deadline = Instant::now() + Duration::from_secs(5);
        let mut output = Vec::new();
        let mut process = None;
        while Instant::now() < deadline {
            output.extend(engine.read(opened.id).unwrap().data);
            process = String::from_utf8_lossy(&output).lines().find_map(|line| {
                line.trim()
                    .strip_prefix("__BACKGROUND:")
                    .and_then(|value| value.strip_suffix("__"))
                    .and_then(|value| value.parse::<u32>().ok())
            });
            if process.is_some() {
                break;
            }
            std::thread::sleep(Duration::from_millis(10));
        }
        let process = process.expect("Background job did not report its PID");
        let path = PathBuf::from(format!("/proc/{process}"));
        assert!(path.exists());
        engine.close(opened.id).unwrap();
        let deadline = Instant::now() + Duration::from_secs(3);
        while path.exists() && Instant::now() < deadline {
            std::thread::sleep(Duration::from_millis(20));
        }
        assert!(
            !path.exists(),
            "Ordinary background job outlived the terminal"
        );
    }

    #[test]
    #[cfg(target_os = "linux")]
    #[ignore = "Requires btop installed at /usr/bin/btop; run explicitly on the native acceptance host"]
    fn installed_btop_uses_the_actual_pty_alternate_screen() {
        assert!(Path::new("/usr/bin/btop").is_file());
        let engine = TerminalEngine::default();
        let root = std::env::temp_dir();
        let opened = engine.open(root.to_str().unwrap(), 40, 140, true).unwrap();
        engine
            .write(opened.id, b"/usr/bin/btop\r".to_vec())
            .unwrap();
        let deadline = Instant::now() + Duration::from_secs(5);
        let mut output = Vec::new();
        let mut alternate = false;
        while Instant::now() < deadline {
            output.extend(engine.read(opened.id).unwrap().data);
            alternate = output.windows(8).any(|bytes| bytes == b"\x1b[?1049h");
            if alternate {
                break;
            }
            std::thread::sleep(Duration::from_millis(20));
        }
        engine.write(opened.id, b"q".to_vec()).unwrap();
        engine.close(opened.id).unwrap();
        assert!(
            alternate,
            "Installed btop did not enter the PTY alternate screen"
        );
    }
}
