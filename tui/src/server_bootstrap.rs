//! Server bootstrap - start the bifang-server sidecar when it is not running yet.
//!
//! The TUI expects a bifang-server on `BIFANG_TUI_SERVER` (default
//! `http://127.0.0.1:8000`). If nothing answers there, `ensure_server` launches
//! a server binary from (in order) `BIFANG_TUI_SERVER_BINARY`, a sibling file
//! next to the TUI executable, or the `bifang-server` on PATH. The child is
//! detached from the TUI process group so the TUI can exit without killing it,
//! and repeated launches reuse the running server instead of spawning more,
//! because spawn only happens when the health check fails.

use std::future::Future;
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::time::Duration;

use anyhow::{anyhow, Context, Result};
use tokio::process::{Child, Command};
use url::Url;

/// Environment variable that names the server binary explicitly.
pub const SERVER_BINARY_ENV: &str = "BIFANG_TUI_SERVER_BINARY";

/// Setting this to `0`/`false` turns auto-start off for the TUI.
pub const AUTOSTART_ENV: &str = "BIFANG_AUTOSTART_SERVER";

/// Delay between health probes while the spawned server warms up.
pub const HEALTH_POLL_SECS: u64 = 1;

/// Give the frozen (PyInstaller) server enough time for its one-file unpack.
pub const HEALTH_ATTEMPTS: u32 = 45;

fn default_port(url: &Url) -> u16 {
    url.port().unwrap_or(match url.scheme() {
        "https" => 443,
        "http" => 80,
        _ => 8000,
    })
}

/// Parse host and port from the configured server URL.
pub fn parse_host_port(server_url: &str) -> Result<(String, u16)> {
    let url = Url::parse(server_url).context("BIFANG_TUI_SERVER is not a valid URL")?;
    let host = match url.host_str() {
        Some(host) => host.to_string(),
        None => return Err(anyhow!("BIFANG_TUI_SERVER has no host")),
    };
    Ok((host, default_port(&url)))
}

/// Copy of `which`: first PATH directory containing an executable `name`.
pub fn which(name: &str) -> Option<PathBuf> {
    let dirs = std::env::var_os("PATH")?;
    for dir in std::env::split_paths(&dirs) {
        let candidate = dir.join(name);
        if is_executable_file(&candidate) {
            return Some(candidate);
        }
    }
    None
}

fn is_executable_file(path: &Path) -> bool {
    use std::os::unix::fs::PermissionsExt;
    match path.metadata() {
        Ok(metadata) => metadata.is_file() && metadata.permissions().mode() & 0o111 != 0,
        Err(_) => false,
    }
}

/// Locate a server binary: explicit override, then sibling of the TUI
/// executable, then `bifang-server` on PATH.
pub fn resolve_server_binary(override_value: Option<&str>, exe_parent: Option<&Path>) -> Option<PathBuf> {
    if let Some(value) = override_value.filter(|value| !value.trim().is_empty()) {
        let path = PathBuf::from(value);
        if is_executable_file(&path) {
            return Some(path);
        }
        if let Some(found) = which(value) {
            return Some(found);
        }
        return None;
    }
    if let Some(parent) = exe_parent {
        let sibling = parent.join("bifang-server");
        if is_executable_file(&sibling) {
            return Some(sibling);
        }
        // Tauri's build layout names sidecars with the target triple.
        let sibling = parent.join(format!("bifang-server-{}", sidecar_triple()));
        if is_executable_file(&sibling) {
            return Some(sibling);
        }
    }
    which("bifang-server")
}

/// Cargo/tauri host tuple for same-directory sidecar discovery.
fn sidecar_triple() -> &'static str {
    if cfg!(all(target_os = "linux", target_arch = "x86_64")) {
        "x86_64-unknown-linux-gnu"
    } else if cfg!(all(target_os = "linux", target_arch = "aarch64")) {
        "aarch64-unknown-linux-gnu"
    } else if cfg!(target_os = "macos") && cfg!(target_arch = "aarch64") {
        "aarch64-apple-darwin"
    } else if cfg!(target_os = "macos") && cfg!(target_arch = "x86_64") {
        "x86_64-apple-darwin"
    } else if cfg!(target_os = "windows") && cfg!(target_arch = "aarch64") {
        "aarch64-pc-windows-msvc"
    } else if cfg!(target_os = "windows") {
        "x86_64-pc-windows-msvc"
    } else {
        "x86_64-unknown-linux-gnu"
    }
}

/// Spawn a detached server child for `server_url`; returns the child handle.
pub async fn launch(server_binary: &Path, server_url: &str) -> Result<Child> {
    let (host, port) = parse_host_port(server_url)?;
    let log_path = server_log_path();
    std::fs::create_dir_all(log_path.parent().ok_or_else(|| anyhow!("no server log directory"))?)?;

    let stdout_log = std::fs::OpenOptions::new().create(true).append(true).open(&log_path)?
        .try_clone()?;
    let stderr_log = std::fs::OpenOptions::new().create(true).append(true).open(&log_path)?;
    let mut command = Command::new(server_binary);
    command
        .env("BIFANG_SERVER_HOST", &host)
        .env("BIFANG_SERVER_PORT", port.to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::from(stdout_log))
        .stderr(Stdio::from(stderr_log));

    #[cfg(unix)]
    command.process_group(0);

    command.spawn().map_err(|error| {
        anyhow!("failed to spawn {}: {error}", server_binary.display())
    })
}

/// Log file for auto-started servers, next to other Bifang user state.
pub fn server_log_path() -> PathBuf {
    let mut path = dirs::data_local_dir().unwrap_or_else(|| PathBuf::from("/tmp"));
    path.push("bifang");
    path.push("tui-server.log");
    path
}

/// True unless the user explicitly disabled auto-start.
pub fn autostart_enabled(disabled_env: Option<&str>) -> bool {
    match disabled_env {
        Some(value) => !matches!(value.trim(), "0" | "false" | "no" | "off" | ""),
        None => true,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_host_and_default_port() {
        let (host, port) = parse_host_port("http://127.0.0.1:8000").unwrap();
        assert_eq!(host, "127.0.0.1");
        assert_eq!(port, 8000);
        let (host, port) = parse_host_port("http://127.0.0.1").unwrap();
        assert_eq!(port, 80);
        let (host, port) = parse_host_port("https://example.com").unwrap();
        assert_eq!(port, 443);
        assert!(parse_host_port("not a url").is_err());
    }

    #[test]
    fn resolve_prefers_explicit_override() {
        let mut path = std::env::temp_dir();
        path.push("bifang-test-override-server");
        std::fs::write(&path, b"#!/bin/sh\n").expect("write marker");
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o755)).expect("chmod");
        }
        let resolved = resolve_server_binary(Some(path.to_str().unwrap()), None);
        assert_eq!(resolved, Some(path.clone()));
        std::fs::remove_file(&path).expect("cleanup");
    }

    #[test]
    fn resolve_finds_sibling() {
        let mut dir = std::env::temp_dir();
        dir.push(format!("bifang-sibling-{}", std::process::id()));
        std::fs::create_dir_all(&dir).expect("mkdir");
        let sibling = dir.join("bifang-server");
        std::fs::write(&sibling, b"#!/bin/sh\n").expect("write");
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&sibling, std::fs::Permissions::from_mode(0o755)).expect("chmod");
        }
        let resolved = resolve_server_binary(None, Some(&dir));
        assert_eq!(resolved, Some(sibling.clone()));
        std::fs::remove_dir_all(&dir).expect("cleanup");
    }

    #[test]
    fn autostart_flag_off() {
        assert!(autostart_enabled(None));
        assert!(autostart_enabled(Some("1")));
        assert!(!autostart_enabled(Some("0")));
        assert!(!autostart_enabled(Some("false")));
        assert!(!autostart_enabled(Some("")));
    }

    #[test]
    fn log_path_is_under_bifang_state() {
        assert!(server_log_path().ends_with("bifang/tui-server.log"));
    }
}
