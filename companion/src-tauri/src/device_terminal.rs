use crate::terminal_engine::{TerminalEngine, TerminalFrame, TerminalOpened};
use std::path::PathBuf;
use tauri::{Manager, State, WebviewWindow};

pub(crate) fn local_window(window: &WebviewWindow) -> Result<(), String> {
    let url = window.url().map_err(|_| "Application origin is unavailable")?;
    let bundled = url.scheme() == "tauri" && url.host_str() == Some("localhost")
        || matches!(url.scheme(), "http" | "https") && url.host_str() == Some("tauri.localhost");
    let development = cfg!(debug_assertions) && url.scheme() == "http"
        && matches!(url.host_str(), Some("localhost" | "127.0.0.1")) && url.port() == Some(1435);
    if window.label() != "main" || !url.username().is_empty() || url.password().is_some()
        || !(bundled && url.port().is_none() || development) {
        return Err("Device terminals require the Bifang application interface".into());
    }
    if cfg!(target_os = "ios") {
        return Err("Local shells are available on Android and desktop builds".into());
    }
    Ok(())
}

fn directory(window: &WebviewWindow) -> Result<PathBuf, String> {
    let root = window.app_handle().path().app_data_dir()
        .map_err(|_| "Application storage is unavailable")?;
    let projects = root.join("projects").join("terminal");
    std::fs::create_dir_all(projects.join(".tmp"))
        .map_err(|_| "Could not prepare terminal project storage")?;
    let root = root.canonicalize().map_err(|_| "Application storage is unavailable")?;
    let projects = projects.canonicalize().map_err(|_| "Terminal project storage is unavailable")?;
    if !projects.starts_with(root) {
        return Err("Terminal project storage must stay inside application data".into());
    }
    Ok(projects)
}

#[tauri::command]
pub fn device_terminal_directory(window: WebviewWindow) -> Result<String, String> {
    local_window(&window)?;
    Ok(directory(&window)?.to_string_lossy().into_owned())
}

#[tauri::command]
pub async fn terminal_open(window: WebviewWindow, path: String, rows: u16, cols: u16, confirmed: bool) -> Result<TerminalOpened, String> {
    local_window(&window)?;
    let expected = directory(&window)?;
    if PathBuf::from(path) != expected {
        return Err("Start the terminal in its application project directory".into());
    }
    let app = window.app_handle().clone();
    tauri::async_runtime::spawn_blocking(move || app.state::<TerminalEngine>().open(&expected.to_string_lossy(), rows, cols, confirmed))
        .await.map_err(|_| "Device terminal launch interrupted".to_string())?
}

#[tauri::command]
pub async fn terminal_write(window: WebviewWindow, id: u32, data: Vec<u8>) -> Result<(), String> {
    local_window(&window)?;
    let app = window.app_handle().clone();
    tauri::async_runtime::spawn_blocking(move || app.state::<TerminalEngine>().write(id, data))
        .await.map_err(|_| "Device terminal input interrupted".to_string())?
}

#[tauri::command]
pub fn terminal_read(window: WebviewWindow, state: State<'_, TerminalEngine>, id: u32) -> Result<TerminalFrame, String> {
    local_window(&window)?;
    state.read(id)
}

#[tauri::command]
pub fn terminal_resize(window: WebviewWindow, state: State<'_, TerminalEngine>, id: u32, rows: u16, cols: u16) -> Result<(), String> {
    local_window(&window)?;
    state.resize(id, rows, cols)
}

#[tauri::command]
pub async fn terminal_close(window: WebviewWindow, id: u32) -> Result<(), String> {
    local_window(&window)?;
    let app = window.app_handle().clone();
    tauri::async_runtime::spawn_blocking(move || app.state::<TerminalEngine>().close(id))
        .await.map_err(|_| "Device terminal shutdown interrupted".to_string())?
}
