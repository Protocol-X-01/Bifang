use serde_json::Value;
use std::path::PathBuf;
use std::time::Duration;
use tauri::{command, AppHandle, Manager, State, WebviewWindow};
use tauri_plugin_shell::{process::CommandEvent, ShellExt};

const MAX_REQUEST: usize = 4096;
const MAX_OUTPUT: usize = 2_000_001;
const MAX_ERROR: usize = 16_384;

pub struct WorkbenchState(pub tokio::sync::Semaphore);

pub fn state_root(app: &AppHandle) -> Result<PathBuf, String> {
    resolve_state_root(
        std::env::var_os("XDG_STATE_HOME").map(PathBuf::from),
        app.path().home_dir().ok(),
    )
}

fn resolve_state_root(
    configured: Option<PathBuf>,
    home: Option<PathBuf>,
) -> Result<PathBuf, String> {
    let root = configured
        .or_else(|| home.map(|path| path.join(".local/state")))
        .ok_or("Desktop state directory is unavailable")?;
    if !root.is_absolute() {
        return Err("Desktop state directory must be absolute".into());
    }
    Ok(root)
}

fn encode_request(request: &Value) -> Result<Vec<u8>, String> {
    let mut encoded = serde_json::to_vec(request).map_err(|_| "Invalid workbench request")?;
    encoded.push(b'\n');
    if encoded.len() > MAX_REQUEST || !request.is_object() {
        return Err("Workbench request is too large or invalid".into());
    }
    Ok(encoded)
}

fn parse_response(output: &[u8], code: Option<i32>) -> Result<Value, String> {
    let response: Value =
        serde_json::from_slice(output).map_err(|_| "Invalid workbench response")?;
    if code != Some(0) || response.get("ok") != Some(&Value::Bool(true)) {
        return Err(
            "Workbench request failed. Refresh and review the current files and selection.".into(),
        );
    }
    response
        .get("result")
        .filter(|result| result.is_object())
        .cloned()
        .ok_or("Missing workbench result".into())
}

#[command]
pub async fn workbench_request(
    window: WebviewWindow,
    state: State<'_, WorkbenchState>,
    request: Value,
) -> Result<Value, String> {
    crate::terminal::local_window(&window)?;
    let _permit = state
        .0
        .try_acquire()
        .map_err(|_| "Another workbench operation is in progress")?;
    let input = encode_request(&request)?;
    let command = helper_command(window.app_handle(), "--workbench")?;
    run_helper(command, &input, Duration::from_secs(25)).await
}

pub fn helper_command(
    app: &AppHandle,
    mode: &str,
) -> Result<tauri_plugin_shell::process::Command, String> {
    if !matches!(mode, "--workbench" | "--setup") {
        return Err("Unsupported helper mode".into());
    }
    let mut command = app
        .shell()
        .sidecar("bifang-server")
        .map_err(|_| "Bundled workbench helper is unavailable")?
        .args([mode])
        .env_clear()
        .set_raw_out(true)
        .set_process_group(true);
    for name in [
        "HOME",
        "USERPROFILE",
        "SystemRoot",
        "WINDIR",
        "TEMP",
        "TMP",
        "LANG",
        "LC_ALL",
        "PATH",
        "RUSTUP_HOME",
        "UV_PYTHON_INSTALL_DIR",
        "XDG_DATA_HOME",
    ] {
        if let Some(value) = std::env::var_os(name) {
            command = command.env(name, value);
        }
    }
    command = command
        .env("XDG_STATE_HOME", state_root(app)?)
        .env("BIFANG_NO_DOTENV", "1");
    Ok(command)
}

pub(crate) async fn run_helper(
    command: tauri_plugin_shell::process::Command,
    input: &[u8],
    timeout: Duration,
) -> Result<Value, String> {
    let (mut receiver, mut child) = command
        .spawn()
        .map_err(|_| "Could not start workbench helper")?;
    if child.write(input).is_err() {
        let _ = child.kill();
        return Err("Could not send workbench request".into());
    }
    let mut terminated = false;
    let result = tokio::time::timeout(timeout, async {
        let mut output = Vec::new();
        let mut error_size = 0usize;
        while let Some(event) = receiver.recv().await {
            match event {
                CommandEvent::Stdout(bytes) => {
                    if output.len() + bytes.len() > MAX_OUTPUT {
                        return Err("Workbench response exceeded its limit".into());
                    }
                    output.extend(bytes);
                }
                CommandEvent::Stderr(bytes) => {
                    error_size = error_size.saturating_add(bytes.len());
                    if error_size > MAX_ERROR {
                        return Err("Workbench diagnostics exceeded their limit".into());
                    }
                }
                CommandEvent::Error(_) => return Err("Workbench helper failed".into()),
                CommandEvent::Terminated(status) => {
                    terminated = true;
                    return parse_response(&output, status.code);
                }
                _ => {}
            }
        }
        Err("Workbench helper ended without a result".into())
    })
    .await
    .unwrap_or_else(|_| Err("Workbench request timed out".into()));
    if !terminated {
        let _ = child.kill();
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn test_command(program: impl AsRef<std::ffi::OsStr>) -> tauri_plugin_shell::process::Command {
        let app = tauri::test::mock_builder()
            .plugin(tauri_plugin_shell::init())
            .build(tauri::test::mock_context(tauri::test::noop_assets()))
            .unwrap();
        app.shell().command(program)
    }

    #[test]
    fn request_is_bounded_and_single_line() {
        assert!(encode_request(&json!([])).is_err());
        assert!(encode_request(&json!({"source": "x".repeat(MAX_REQUEST)})).is_err());
        let encoded =
            encode_request(&json!({"action": "plugins.list", "workspace": "line\nname"})).unwrap();
        assert_eq!(encoded.iter().filter(|byte| **byte == b'\n').count(), 1);
    }

    #[test]
    fn response_requires_success_and_exact_json_without_leaking_diagnostics() {
        assert_eq!(
            parse_response(br#"{"ok":true,"result":{"plugins":[]}}"#, Some(0)).unwrap(),
            json!({"plugins":[]})
        );
        for bytes in [
            br#"{"ok":false,"error":"private fixture"}"#.as_slice(),
            b"not json",
            b"{}",
            br#"{"ok":true,"result":[]}"#,
            b"{}\n{}",
        ] {
            let error = parse_response(bytes, Some(0)).unwrap_err();
            assert!(!error.contains("private fixture"));
        }
        assert!(parse_response(br#"{"ok":true,"result":{}}"#, Some(1)).is_err());
    }

    #[test]
    fn desktop_state_root_is_explicit_and_absolute() {
        let home = std::env::temp_dir();
        assert_eq!(
            resolve_state_root(None, Some(home.clone())).unwrap(),
            home.join(".local/state")
        );
        assert_eq!(resolve_state_root(Some(home.clone()), None).unwrap(), home);
        assert!(resolve_state_root(Some(PathBuf::from("relative")), None).is_err());
        assert!(resolve_state_root(None, None).is_err());
    }

    #[tokio::test]
    #[ignore = "Requires the separately built helper; set BIFANG_TEST_WORKBENCH_BINARY and run explicitly"]
    async fn actual_frozen_helper_native_event_transport() {
        let binary = std::env::var("BIFANG_TEST_WORKBENCH_BINARY").unwrap();
        let home = std::env::temp_dir();
        for action in ["toolchains.inspect", "metrics.sample"] {
            let command = test_command(&binary)
                .args(["--workbench"])
                .env_clear()
                .env("HOME", &home)
                .env("USERPROFILE", &home)
                .set_raw_out(true)
                .set_process_group(true);
            let input =
                encode_request(&json!({"version":1,"action":action,"workspace":home})).unwrap();
            let result = run_helper(command, &input, Duration::from_secs(15))
                .await
                .unwrap();
            if action == "toolchains.inspect" {
                assert_eq!(result["automatic_install"], false);
                assert!(result["profiles"].is_array());
            } else {
                assert_eq!(result["schema"], 1);
                for component in ["cpu", "memory", "disk"] {
                    assert_eq!(result[component]["available"], true);
                }
                assert_eq!(result["gpu"]["available"], false);
            }
        }
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn actual_transport_limits_output_and_terminates_timeout_group() {
        let command = test_command("/bin/sh")
            .args(["-c", "head -c 2000002 /dev/zero"])
            .env_clear()
            .env("PATH", "/usr/bin:/bin")
            .set_raw_out(true)
            .set_process_group(true);
        let error = run_helper(command, b"{}\n", Duration::from_secs(5))
            .await
            .unwrap_err();
        assert!(error.contains("exceeded"));
        let command = test_command("/bin/sh")
            .args(["-c", "sleep 10"])
            .env_clear()
            .env("PATH", "/usr/bin:/bin")
            .set_raw_out(true)
            .set_process_group(true);
        let started = std::time::Instant::now();
        let error = run_helper(command, b"{}\n", Duration::from_millis(50))
            .await
            .unwrap_err();
        assert!(error.contains("timed out"));
        assert!(started.elapsed() < Duration::from_secs(2));
    }
}
