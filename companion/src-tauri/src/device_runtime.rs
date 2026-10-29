use serde_json::Value;
use tauri::WebviewWindow;
#[cfg(target_os = "android")]
use tauri::Manager;

#[cfg(target_os = "android")]
pub struct DeviceRuntime(tauri::plugin::PluginHandle<tauri::Wry>);

#[cfg(target_os = "android")]
pub fn init() -> tauri::plugin::TauriPlugin<tauri::Wry> {
    tauri::plugin::Builder::new("bifang-device-runtime")
        .setup(|app, api| {
            let handle = api.register_android_plugin("com.bifang.companion", "DeviceRuntimePlugin")?;
            app.manage(DeviceRuntime(handle));
            Ok(())
        })
        .build()
}

#[tauri::command]
pub async fn device_hardware_check(window: WebviewWindow) -> Result<Value, String> {
    crate::device_terminal::local_window(&window)?;
    #[cfg(target_os = "android")]
    {
        let app = window.app_handle().clone();
        tauri::async_runtime::spawn_blocking(move || {
            app.state::<DeviceRuntime>().0.run_mobile_plugin("hardwareCheck", serde_json::json!({}))
                .map_err(|_| "Device hardware check could not complete".to_string())
        }).await.map_err(|_| "Device hardware check interrupted".to_string())?
    }
    #[cfg(not(target_os = "android"))]
    {
        Err("This device check is available on Android".into())
    }
}

#[tauri::command]
pub async fn device_runtime_request(window: WebviewWindow, request: Value) -> Result<Value, String> {
    crate::device_terminal::local_window(&window)?;
    if !request.is_object() || request.to_string().len() > 131072 {
        return Err("Invalid runtime request".into());
    }
    #[cfg(target_os = "android")]
    {
        let app = window.app_handle().clone();
        tauri::async_runtime::spawn_blocking(move || {
            let method = if request.get("action").and_then(Value::as_str) == Some("permission") { "runtimePermission" } else { "runtimeRequest" };
            app.state::<DeviceRuntime>().0.run_mobile_plugin(method, serde_json::json!({"request": request.to_string()}))
                .map_err(|error| error.to_string())
        }).await.map_err(|_| "Distribution runtime request interrupted".to_string())?
    }
    #[cfg(not(target_os = "android"))]
    {
        Err("Distribution runtime integration is available on Android".into())
    }
}
