// Bifang Desktop - Tauri Backend

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use tauri::{command, generate_context, generate_handler, AppHandle, Manager, State};
use tauri_plugin_shell::{process::CommandChild, ShellExt};

mod commands;

// App state for bifang server
struct BifangServerState {
    process: Mutex<Option<RunningServer>>,
}

struct RunningServer {
    child: CommandChild,
    running: Arc<AtomicBool>,
}

fn spawn_server(app: &AppHandle) -> Result<RunningServer, String> {
    let config_path = app
        .path()
        .app_config_dir()
        .map_err(|error| error.to_string())?
        .join(".env");

    let (mut receiver, child) = app
        .shell()
        .sidecar("bifang-server")
        .map_err(|error| error.to_string())?
        .env("BIFANG_SERVER_HOST", "127.0.0.1")
        .env("BIFANG_ALLOW_ABSOLUTE_WORKSPACES", "1")
        .env("BIFANG_ENV_FILE", config_path.to_string_lossy().as_ref())
        .spawn()
        .map_err(|error| error.to_string())?;

    let running = Arc::new(AtomicBool::new(true));
    let monitor = Arc::clone(&running);
    tauri::async_runtime::spawn(async move {
        while receiver.recv().await.is_some() {}
        monitor.store(false, Ordering::Release);
    });

    Ok(RunningServer { child, running })
}

#[command]
async fn start_bifang_server(
    app: AppHandle,
    state: State<'_, BifangServerState>,
) -> Result<String, String> {
    let mut process_guard = state.process.lock().unwrap();

    if let Some(server) = process_guard.as_ref() {
        if server.running.load(Ordering::Acquire) {
            return Ok("Server already running".to_string());
        }
    }
    if let Some(server) = process_guard.take() {
        let _ = server.child.kill();
    }

    // Start bifang-server in background
    let child = spawn_server(&app)?;

    *process_guard = Some(child);
    Ok("Bifang server started on http://localhost:8000".to_string())
}

#[command]
async fn stop_bifang_server(state: State<'_, BifangServerState>) -> Result<String, String> {
    let mut process_guard = state.process.lock().unwrap();

    if let Some(server) = process_guard.take() {
        server
            .child
            .kill()
            .map_err(|e| format!("Failed to stop server: {}", e))?;
        Ok("Bifang server stopped".to_string())
    } else {
        Ok("Server not running".to_string())
    }
}

#[command]
async fn get_server_status(state: State<'_, BifangServerState>) -> Result<bool, String> {
    let process_guard = state.process.lock().unwrap();
    Ok(process_guard
        .as_ref()
        .is_some_and(|server| server.running.load(Ordering::Acquire)))
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .manage(BifangServerState {
            process: Mutex::new(None),
        })
        .invoke_handler(generate_handler![
            commands::get_file_tree,
            start_bifang_server,
            stop_bifang_server,
            get_server_status,
        ])
        .setup(|app| {
            let state = app.state::<BifangServerState>();
            tauri::async_runtime::block_on(async {
                let mut process_guard = state.process.lock().unwrap();
                if process_guard.is_none() {
                    if let Ok(child) = spawn_server(app.handle()) {
                        *process_guard = Some(child);
                    }
                }
            });

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                // Stop server on close
                let state = window.state::<BifangServerState>();
                tauri::async_runtime::block_on(async {
                    let mut process_guard = state.process.lock().unwrap();
                    if let Some(server) = process_guard.take() {
                        let _ = server.child.kill();
                    }
                });
            }
        })
        .run(generate_context!())
        .expect("error while running tauri application");
}
