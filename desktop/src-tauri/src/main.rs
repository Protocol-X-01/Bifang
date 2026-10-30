// Bifang Desktop - Tauri Backend

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use tauri::{command, generate_context, generate_handler, AppHandle, Manager, State};
use tauri_plugin_shell::{
    process::{CommandChild, CommandEvent},
    ShellExt,
};

mod commands;
mod remote;
mod server_connection;
mod setup;
mod terminal;
mod terminal_engine;
mod workbench;

// App state for bifang server
struct BifangServerState {
    process: Mutex<Option<RunningServer>>,
}

struct RunningServer {
    child: CommandChild,
    running: Arc<AtomicBool>,
    connection: Arc<Mutex<Option<server_connection::ServerConnection>>>,
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
        .set_process_group(true)
        .env("BIFANG_SERVER_HOST", "127.0.0.1")
        .env("BIFANG_DESKTOP_BOOTSTRAP", "1")
        .env("BIFANG_ALLOW_ABSOLUTE_WORKSPACES", "1")
        .env("BIFANG_ENV_FILE", config_path.to_string_lossy().as_ref())
        .env("XDG_STATE_HOME", workbench::state_root(app)?)
        .spawn()
        .map_err(|error| error.to_string())?;

    let running = Arc::new(AtomicBool::new(true));
    let monitor = Arc::clone(&running);
    let connection = Arc::new(Mutex::new(None));
    let ready = Arc::clone(&connection);
    tauri::async_runtime::spawn(async move {
        while let Some(event) = receiver.recv().await {
            if let CommandEvent::Stdout(line) = event {
                if let Some(parsed) = server_connection::ServerConnection::parse(&line) {
                    let mut current = ready.lock().unwrap();
                    if current.is_none() {
                        *current = Some(parsed);
                    }
                }
            }
        }
        *ready.lock().unwrap() = None;
        monitor.store(false, Ordering::Release);
    });

    Ok(RunningServer {
        child,
        running,
        connection,
    })
}

#[command]
async fn get_server_connection(
    window: tauri::WebviewWindow,
    state: State<'_, BifangServerState>,
) -> Result<server_connection::ServerConnection, String> {
    terminal::local_window(&window)?;
    for _ in 0..450 {
        {
            let process = state.process.lock().unwrap();
            let server = process.as_ref().ok_or("Local server is stopped")?;
            if !server.running.load(Ordering::Acquire) {
                return Err("Local server exited before connecting".into());
            }
            let ready = server.connection.lock().unwrap().clone();
            if let Some(connection) = ready {
                return Ok(connection);
            }
        }
        tokio::time::sleep(std::time::Duration::from_millis(100)).await;
    }
    Err("Local server did not become ready in time".into())
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
    Ok("Bifang server is starting on a private local connection".to_string())
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
    Ok(process_guard.as_ref().is_some_and(|server| {
        server.running.load(Ordering::Acquire) && server.connection.lock().unwrap().is_some()
    }))
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_shell::init())
        .manage(BifangServerState {
            process: Mutex::new(None),
        })
        .manage(remote::RemoteState::default())
        .manage(terminal_engine::TerminalEngine::default())
        .manage(workbench::WorkbenchState(tokio::sync::Semaphore::new(1)))
        .manage(setup::SetupState::default())
        .invoke_handler(generate_handler![
            commands::get_file_tree,
            commands::read_workspace_file,
            commands::resolve_workspace_path,
            commands::create_workspace,
            workbench::workbench_request,
            setup::setup_run,
            setup::setup_cancel,
            start_bifang_server,
            stop_bifang_server,
            get_server_status,
            get_server_connection,
            remote::remote_connect,
            remote::remote_disconnect,
            remote::remote_operation,
            remote::remote_pair_begin,
            remote::remote_pair_poll,
            remote::remote_pair_cancel,
            terminal::terminal_open,
            terminal::terminal_write,
            terminal::terminal_read,
            terminal::terminal_resize,
            terminal::terminal_close,
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
                window
                    .state::<terminal_engine::TerminalEngine>()
                    .close_all();
                window.state::<setup::SetupState>().cancel_all();
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
