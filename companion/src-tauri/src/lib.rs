#[path = "../../../desktop/src-tauri/src/remote.rs"]
mod remote;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(remote::RemoteState::default())
        .invoke_handler(tauri::generate_handler![
            remote::remote_connect,
            remote::remote_disconnect,
            remote::remote_operation,
        ])
        .run(tauri::generate_context!())
        .expect("Bifang companion failed to start");
}
