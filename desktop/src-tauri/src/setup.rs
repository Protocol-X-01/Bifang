use serde_json::Value;
use std::sync::Mutex;
use std::time::Duration;
use tauri::{command, ipc::Channel, Manager, State, WebviewWindow};
use tauri_plugin_shell::process::{Command, CommandChild, CommandEvent};
use tokio::sync::watch;

const MAX_WIRE: usize = 8_000_000;
const MAX_LINE: usize = 65_536;

#[derive(Default)]
pub struct SetupState(Mutex<Option<(String, watch::Sender<bool>)>>);

impl SetupState {
    fn begin(&self, id: &str) -> Result<watch::Receiver<bool>, String> {
        if id.len() != 32 || !id.bytes().all(|byte| byte.is_ascii_hexdigit()) {
            return Err("Invalid setup operation identifier".into());
        }
        let mut active = self.0.lock().map_err(|_| "Setup state unavailable")?;
        if active.is_some() {
            return Err("Another setup operation is active".into());
        }
        let (sender, receiver) = watch::channel(false);
        *active = Some((id.into(), sender));
        Ok(receiver)
    }

    fn cancel(&self, id: &str) -> Result<bool, String> {
        let active = self.0.lock().map_err(|_| "Setup state unavailable")?;
        Ok(active
            .as_ref()
            .is_some_and(|(current, sender)| current == id && sender.send(true).is_ok()))
    }

    pub fn cancel_all(&self) {
        if let Ok(active) = self.0.lock() {
            if let Some((_, sender)) = active.as_ref() {
                let _ = sender.send(true);
            }
        }
    }
}

struct Active<'a>(&'a SetupState, String);

impl Drop for Active<'_> {
    fn drop(&mut self) {
        if let Ok(mut active) = self.0 .0.lock() {
            if active.as_ref().is_some_and(|(id, _)| id == &self.1) {
                if let Some((_, sender)) = active.take() {
                    let _ = sender.send(true);
                }
            }
        }
    }
}

struct ChildGuard(Option<CommandChild>);

impl Drop for ChildGuard {
    fn drop(&mut self) {
        if let Some(child) = self.0.take() {
            let _ = child.kill();
        }
    }
}

fn encode(request: &Value) -> Result<Vec<u8>, String> {
    let mut fields = vec![
        "version",
        "workspace",
        "sha256",
        "network",
        "registry",
        "confirmed",
    ];
    if request["version"].as_u64() == Some(2) {
        fields.extend(["profile", "allow_builds"]);
        if !matches!(
            request["profile"].as_str(),
            Some("javascript-npm" | "python-uv" | "rust-cargo")
        ) || request["allow_builds"].as_bool().is_none()
        {
            return Err("Select a supported profile and explicit build permission".into());
        }
    }
    let object = request.as_object().ok_or("Invalid setup request")?;
    if object.len() != fields.len()
        || fields.iter().any(|field| !object.contains_key(*field))
        || !matches!(request["version"].as_u64(), Some(1 | 2))
        || request["confirmed"].as_bool() != Some(true)
        || request["network"].as_bool().is_none()
        || !request["workspace"]
            .as_str()
            .is_some_and(|path| std::path::Path::new(path).is_absolute())
        || !request["sha256"].as_str().is_some_and(|hash| {
            hash.len() == 64 && hash.bytes().all(|byte| byte.is_ascii_hexdigit())
        })
        || request["registry"].as_str().is_none()
    {
        return Err("Review and approve an exact setup plan".into());
    }
    let mut bytes = serde_json::to_vec(request).map_err(|_| "Invalid setup request")?;
    bytes.push(b'\n');
    if bytes.len() > 8192 {
        return Err("Setup request is too large".into());
    }
    Ok(bytes)
}

#[derive(Default)]
struct Frames {
    pending: Vec<u8>,
    total: usize,
    receipt: Option<Value>,
}

impl Frames {
    fn feed(
        &mut self,
        bytes: &[u8],
        expected: &str,
        output: &mut impl FnMut(Value) -> Result<(), String>,
    ) -> Result<(), String> {
        self.total = self.total.saturating_add(bytes.len());
        if self.total > MAX_WIRE {
            return Err("Setup output exceeded its transport limit".into());
        }
        for byte in bytes {
            if *byte != b'\n' {
                self.pending.push(*byte);
                if self.pending.len() > MAX_LINE {
                    return Err("Setup frame exceeded its limit".into());
                }
                continue;
            }
            let event: Value =
                serde_json::from_slice(&self.pending).map_err(|_| "Invalid setup output frame")?;
            self.pending.clear();
            if self.receipt.is_some() {
                return Err("Unexpected output after the setup receipt".into());
            }
            match event["event"].as_str() {
                Some("output") if event.as_object().is_some_and(|item| item.len() == 3)
                    && matches!(event["stream"].as_str(), Some("stdout" | "stderr"))
                    && event["text"].as_str().is_some_and(|text| text.len() <= 32768) => output(event)?,
                Some("result") if event.as_object().is_some_and(|item| item.len() == 2)
                    && event["receipt"].is_object()
                    && event["receipt"]["plan_sha256"].as_str() == Some(expected) => {
                        self.receipt = Some(event["receipt"].clone());
                    }
                Some("error") => return Err("Setup could not be verified. Review the current plan and sandbox before retrying.".into()),
                _ => return Err("Invalid setup output event".into()),
            }
        }
        Ok(())
    }
}

async fn run_helper(
    command: Command,
    input: &[u8],
    expected: &str,
    mut cancellation: watch::Receiver<bool>,
    timeout: Duration,
    mut output: impl FnMut(Value) -> Result<(), String>,
) -> Result<Value, String> {
    let (mut receiver, child) = command
        .spawn()
        .map_err(|_| "Could not start setup helper")?;
    let mut child = ChildGuard(Some(child));
    child
        .0
        .as_mut()
        .ok_or("Setup helper unavailable")?
        .write(input)
        .map_err(|_| "Could not send setup request")?;
    let mut frames = Frames::default();
    let mut errors = 0usize;
    let mut cancelled = false;
    let mut deadline = tokio::time::Instant::now() + timeout;
    loop {
        tokio::select! {
            changed = cancellation.changed(), if !cancelled && frames.receipt.is_none() => {
                if changed.is_err() || *cancellation.borrow() {
                    child.0.as_mut().ok_or("Setup helper unavailable")?.write(b"{\"cancel\":true}\n").map_err(|_| "Could not request setup cancellation")?;
                    cancelled = true;
                    deadline = deadline.min(tokio::time::Instant::now() + Duration::from_secs(5));
                }
            }
            _ = tokio::time::sleep_until(deadline) => return Err("Setup helper timed out; inspect the project and saved receipts before retrying".into()),
            event = receiver.recv() => match event {
                Some(CommandEvent::Stdout(bytes)) => frames.feed(&bytes, expected, &mut output)?,
                Some(CommandEvent::Stderr(bytes)) => {
                    errors = errors.saturating_add(bytes.len());
                    if errors > 16384 { return Err("Setup diagnostics exceeded their limit".into()); }
                }
                Some(CommandEvent::Terminated(status)) => {
                    if status.code != Some(0) || !frames.pending.is_empty() {
                        return Err("Setup helper failed; inspect the project before retrying".into());
                    }
                    return frames.receipt.take().ok_or_else(|| "Setup ended without an exit receipt".into());
                }
                Some(CommandEvent::Error(_)) | None => return Err("Setup helper connection ended without a verified result".into()),
                _ => {}
            }
        }
    }
}

#[command]
pub async fn setup_run(
    window: WebviewWindow,
    state: State<'_, SetupState>,
    request: Value,
    id: String,
    on_event: Channel<Value>,
) -> Result<Value, String> {
    crate::terminal::local_window(&window)?;
    let input = encode(&request)?;
    let cancellation = state.begin(&id)?;
    let _active = Active(&state, id);
    on_event
        .send(serde_json::json!({"event":"started"}))
        .map_err(|_| "Setup output receiver closed")?;
    let command = crate::workbench::helper_command(window.app_handle(), "--setup")?;
    run_helper(
        command,
        &input,
        request["sha256"]
            .as_str()
            .ok_or("Missing setup fingerprint")?,
        cancellation,
        Duration::from_secs(345),
        |event| {
            on_event
                .send(event)
                .map_err(|_| "Setup output receiver closed".into())
        },
    )
    .await
}

#[command]
pub fn setup_cancel(
    window: WebviewWindow,
    state: State<'_, SetupState>,
    id: String,
) -> Result<bool, String> {
    crate::terminal::local_window(&window)?;
    state.cancel(&id)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use tauri_plugin_shell::ShellExt;

    fn test_command(program: impl AsRef<std::ffi::OsStr>) -> Command {
        let app = tauri::test::mock_builder()
            .plugin(tauri_plugin_shell::init())
            .build(tauri::test::mock_context(tauri::test::noop_assets()))
            .unwrap();
        app.shell().command(program)
    }

    #[test]
    fn request_and_frames_are_exact_bounded_and_hash_bound() {
        let hash = "a".repeat(64);
        let request = json!({"version":1,"workspace":"/tmp","sha256":hash,"network":false,"registry":"https://registry.npmjs.org","confirmed":true});
        assert!(encode(&request).is_ok());
        let mut bad = request.clone();
        bad["confirmed"] = json!(false);
        assert!(encode(&bad).is_err());
        bad = request.clone();
        bad["command"] = json!("arbitrary");
        assert!(encode(&bad).is_err());
        let mut frames = Frames::default();
        let mut outputs = Vec::new();
        let frame = b"{\"event\":\"output\",\"stream\":\"stdout\",\"text\":\"literal\"}\n";
        for byte in frame {
            frames
                .feed(&[*byte], &hash, &mut |event| {
                    outputs.push(event);
                    Ok(())
                })
                .unwrap();
        }
        assert_eq!(outputs.len(), 1);
        let receipt =
            format!("{{\"event\":\"result\",\"receipt\":{{\"plan_sha256\":\"{hash}\"}}}}\n");
        frames
            .feed(receipt.as_bytes(), &hash, &mut |_| Ok(()))
            .unwrap();
        assert!(frames.receipt.is_some());
        assert!(frames.feed(frame, &hash, &mut |_| Ok(())).is_err());
        assert!(Frames::default()
            .feed(&vec![b'x'; MAX_LINE + 1], &hash, &mut |_| Ok(()))
            .is_err());
        assert!(Frames::default()
            .feed(receipt.as_bytes(), "wrong", &mut |_| Ok(()))
            .is_err());
    }

    #[test]
    fn profile_requests_require_exact_schema_and_explicit_build_permission() {
        for profile in ["python-uv", "rust-cargo"] {
            for allow_builds in [false, true] {
                let request = json!({"version":2,"workspace":"/tmp","sha256":"a".repeat(64),"network":false,"registry":"https://example.org","confirmed":true,"profile":profile,"allow_builds":allow_builds});
                assert!(encode(&request).is_ok());
                let mut invalid = request.clone();
                invalid["allow_builds"] = json!("true");
                assert!(encode(&invalid).is_err());
                invalid = request.clone();
                invalid["profile"] = json!("arbitrary-command");
                assert!(encode(&invalid).is_err());
                invalid = request.clone();
                invalid["argv"] = json!(["sh"]);
                assert!(encode(&invalid).is_err());
                invalid = request;
                invalid.as_object_mut().unwrap().remove("allow_builds");
                assert!(encode(&invalid).is_err());
            }
        }
    }

    #[test]
    fn cancellation_is_scoped_and_stale_ids_cannot_cancel_new_jobs() {
        let state = SetupState::default();
        let first = "a".repeat(32);
        let second = "b".repeat(32);
        let receiver = state.begin(&first).unwrap();
        assert!(state.begin(&second).is_err());
        assert!(!state.cancel(&second).unwrap());
        assert!(state.cancel(&first).unwrap());
        assert!(*receiver.borrow());
        drop(Active(&state, first.clone()));
        let next = state.begin(&second).unwrap();
        drop(Active(&state, first));
        assert!(!*next.borrow());
        state.cancel_all();
        assert!(*next.borrow());
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn actual_event_transport_cancels_gracefully_and_bounds_hung_helpers() {
        let hash = "a".repeat(64);
        let script = format!("import json,sys; sys.stdin.readline(); print(json.dumps({{'event':'output','stream':'stdout','text':'ready'}}),flush=True); control=json.loads(sys.stdin.readline()); assert control=={{'cancel':True}}; print(json.dumps({{'event':'result','receipt':{{'plan_sha256':'{hash}','status':'cancelled'}}}}),flush=True)");
        let command = test_command("/usr/bin/python3")
            .args(["-c", &script])
            .env_clear()
            .set_raw_out(true)
            .set_process_group(true);
        let (sender, receiver) = watch::channel(false);
        let (observed, ready) = tokio::sync::oneshot::channel();
        let mut observed = Some(observed);
        let operation = run_helper(
            command,
            b"{}\n",
            &hash,
            receiver,
            Duration::from_secs(5),
            |_| {
                if let Some(sender) = observed.take() {
                    let _ = sender.send(());
                }
                Ok(())
            },
        );
        let cancel = async {
            ready.await.unwrap();
            sender.send(true).unwrap();
        };
        let (result, _) = tokio::join!(operation, cancel);
        assert_eq!(result.unwrap()["status"], "cancelled");
        let (_sender, receiver) = watch::channel(false);
        let command = test_command("/usr/bin/python3")
            .args(["-c", "import time; time.sleep(20)"])
            .env_clear()
            .set_raw_out(true)
            .set_process_group(true);
        let started = std::time::Instant::now();
        let error = run_helper(
            command,
            b"{}\n",
            &hash,
            receiver,
            Duration::from_millis(50),
            |_| Ok(()),
        )
        .await
        .unwrap_err();
        assert!(error.contains("timed out"));
        assert!(started.elapsed() < Duration::from_secs(2));
    }

    #[cfg(target_os = "linux")]
    #[tokio::test]
    #[ignore = "Requires a freshly built helper and working npm/Bubblewrap; set BIFANG_TEST_SETUP_BINARY and run explicitly"]
    async fn actual_frozen_setup_plan_install_and_native_progress_transport() {
        struct Fixture(std::path::PathBuf);
        impl Drop for Fixture {
            fn drop(&mut self) {
                let _ = std::fs::remove_dir_all(&self.0);
            }
        }
        let binary = std::env::var("BIFANG_TEST_SETUP_BINARY").unwrap();
        let nonce = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = Fixture(std::env::temp_dir().join(format!(
            "bifang-native-setup-{}-{nonce}",
            std::process::id()
        )));
        std::fs::create_dir(&root.0).unwrap();
        let project = root.0.join("project");
        std::fs::create_dir(&project).unwrap();
        std::fs::write(project.join("package.json"), r#"{"name":"native-fixture","version":"1.0.0","scripts":{"postinstall":"touch HOOK_EXECUTED"}}"#).unwrap();
        std::fs::write(
            project.join("package-lock.json"),
            r#"{"lockfileVersion":3,"packages":{"":{"name":"native-fixture","version":"1.0.0"}}}"#,
        )
        .unwrap();
        let command = |mode: &str| {
            test_command(&binary)
                .args([mode])
                .env_clear()
                .env("HOME", &root.0)
                .env("XDG_STATE_HOME", root.0.join("state"))
                .env("BIFANG_NO_DOTENV", "1")
                .env("PATH", "/usr/bin:/bin")
                .set_raw_out(true)
                .set_process_group(true)
        };
        let mut input = serde_json::to_vec(
            &json!({"version":1,"action":"setup.plan","workspace":project,"network":false}),
        )
        .unwrap();
        input.push(b'\n');
        let plan =
            crate::workbench::run_helper(command("--workbench"), &input, Duration::from_secs(15))
                .await
                .unwrap();
        let input = encode(&json!({"version":1,"workspace":project,"sha256":plan["sha256"],"registry":plan["registry"],"network":false,"confirmed":true})).unwrap();
        let (_sender, receiver) = watch::channel(false);
        let mut progress = Vec::new();
        let receipt = run_helper(
            command("--setup"),
            &input,
            plan["sha256"].as_str().unwrap(),
            receiver,
            Duration::from_secs(30),
            |event| {
                progress.push(event);
                Ok(())
            },
        )
        .await
        .unwrap();
        assert_eq!(receipt["status"], "succeeded");
        assert_eq!(receipt["receipt_saved"], true);
        assert!(!progress.is_empty());
        assert!(!project.join("HOOK_EXECUTED").exists());
        let saved: Value = serde_json::from_slice(
            &std::fs::read(receipt["receipt_path"].as_str().unwrap()).unwrap(),
        )
        .unwrap();
        assert_eq!(saved["plan_sha256"], plan["sha256"]);
    }
}
