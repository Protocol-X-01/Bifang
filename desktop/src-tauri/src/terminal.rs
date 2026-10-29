use crate::terminal_engine::{TerminalEngine, TerminalFrame, TerminalOpened};
use tauri::{command, Manager, State, WebviewWindow};

pub(crate) fn local_window(window: &WebviewWindow) -> Result<(), String> {
    if window.label() != "main" {
        return Err("Local terminals are available only in the main desktop window".into());
    }
    let url = window.url().map_err(|_| "Desktop origin is unavailable")?;
    if !trusted_origin(&url, cfg!(debug_assertions)) {
        return Err("Local terminals require the bundled desktop interface".into());
    }
    Ok(())
}

fn trusted_origin(url: &reqwest::Url, development: bool) -> bool {
    let bundled =
        url.scheme() == "tauri" && url.host_str() == Some("localhost") && url.port().is_none()
            || matches!(url.scheme(), "http" | "https")
                && url.host_str() == Some("tauri.localhost")
                && url.port().is_none();
    let developer = development
        && url.scheme() == "http"
        && matches!(url.host_str(), Some("localhost" | "127.0.0.1"))
        && url.port() == Some(1420);
    url.username().is_empty() && url.password().is_none() && (bundled || developer)
}

#[command]
pub async fn terminal_open(
    window: WebviewWindow,
    path: String,
    rows: u16,
    cols: u16,
    confirmed: bool,
) -> Result<TerminalOpened, String> {
    local_window(&window)?;
    let app = window.app_handle().clone();
    tauri::async_runtime::spawn_blocking(move || {
        app.state::<TerminalEngine>()
            .open(&path, rows, cols, confirmed)
    })
    .await
    .map_err(|_| "Terminal launch interrupted".to_string())?
}

#[command]
pub async fn terminal_write(window: WebviewWindow, id: u32, data: Vec<u8>) -> Result<(), String> {
    local_window(&window)?;
    let app = window.app_handle().clone();
    tauri::async_runtime::spawn_blocking(move || app.state::<TerminalEngine>().write(id, data))
        .await
        .map_err(|_| "Terminal input interrupted".to_string())?
}

#[command]
pub fn terminal_read(
    window: WebviewWindow,
    state: State<'_, TerminalEngine>,
    id: u32,
) -> Result<TerminalFrame, String> {
    local_window(&window)?;
    state.read(id)
}

#[command]
pub fn terminal_resize(
    window: WebviewWindow,
    state: State<'_, TerminalEngine>,
    id: u32,
    rows: u16,
    cols: u16,
) -> Result<(), String> {
    local_window(&window)?;
    state.resize(id, rows, cols)
}

#[command]
pub async fn terminal_close(window: WebviewWindow, id: u32) -> Result<(), String> {
    local_window(&window)?;
    let app = window.app_handle().clone();
    tauri::async_runtime::spawn_blocking(move || app.state::<TerminalEngine>().close(id))
        .await
        .map_err(|_| "Terminal shutdown interrupted".to_string())?
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn origin_is_local_and_development_is_explicit() {
        for value in [
            "tauri://localhost/",
            "http://tauri.localhost/",
            "https://tauri.localhost/",
        ] {
            assert!(trusted_origin(&reqwest::Url::parse(value).unwrap(), false));
        }
        for value in [
            "https://example.com/",
            "https://tauri.localhost.example.com/",
            "http://127.0.0.1:8000/",
            "http://localhost:1431/",
            "http://user:password@tauri.localhost/",
        ] {
            assert!(!trusted_origin(&reqwest::Url::parse(value).unwrap(), true));
        }
        let dev = reqwest::Url::parse("http://localhost:1420/").unwrap();
        assert!(trusted_origin(&dev, true));
        assert!(!trusted_origin(&dev, false));
    }
}
