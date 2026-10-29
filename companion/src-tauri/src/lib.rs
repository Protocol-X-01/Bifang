#[path = "../../../desktop/src-tauri/src/remote.rs"]
mod remote;
#[path = "../../../desktop/src-tauri/src/terminal_engine.rs"]
mod terminal_engine;
mod device_terminal;
mod device_runtime;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let builder = tauri::Builder::default();
    #[cfg(target_os = "android")]
    let builder = builder.plugin(device_runtime::init());
    builder
        .manage(remote::RemoteState::default())
        .manage(terminal_engine::TerminalEngine::default())
        .invoke_handler(tauri::generate_handler![
            remote::remote_connect,
            remote::remote_disconnect,
            remote::remote_operation,
            remote::remote_pair_begin,
            remote::remote_pair_poll,
            remote::remote_pair_cancel,
            device_terminal::device_terminal_directory,
            device_terminal::terminal_open,
            device_terminal::terminal_write,
            device_terminal::terminal_read,
            device_terminal::terminal_resize,
            device_terminal::terminal_close,
            device_runtime::device_hardware_check,
            device_runtime::device_runtime_request,
        ])
        .run(tauri::generate_context!())
        .expect("Bifang companion failed to start");
}
