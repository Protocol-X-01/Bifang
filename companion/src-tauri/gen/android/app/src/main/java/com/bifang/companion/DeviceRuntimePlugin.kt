package com.bifang.companion

import android.app.Activity
import android.Manifest
import android.os.Build
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import app.tauri.annotation.Command
import app.tauri.annotation.InvokeArg
import app.tauri.annotation.Permission
import app.tauri.annotation.PermissionCallback
import app.tauri.annotation.TauriPlugin
import app.tauri.plugin.Invoke
import app.tauri.plugin.Plugin
import app.tauri.plugin.JSObject
import org.json.JSONObject
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.Executors

@InvokeArg
class RuntimeRequest {
    var request: String = "{}"
}

@TauriPlugin(permissions = [
    Permission(strings = ["com.termux.permission.RUN_COMMAND"], alias = "termux"),
    Permission(strings = [Manifest.permission.READ_EXTERNAL_STORAGE, Manifest.permission.WRITE_EXTERNAL_STORAGE], alias = "storage")
])
class DeviceRuntimePlugin(private val activity: Activity) : Plugin(activity) {
    private val checking = AtomicBoolean(false)
    private val runtime = TermuxRuntime(activity)
    private val runtimeWorker = Executors.newSingleThreadExecutor { work -> Thread(work, "bifang-distro-runtime").apply { isDaemon = true } }

    @Command
    fun runtimePermission(invoke: Invoke) {
        activity.runOnUiThread {
            val status = runtime.status()
            if (!status.getBoolean("installed")) {
                invoke.reject("Install and open Termux before allowing the connection")
            } else if (!status.getBoolean("command_api")) {
                invoke.reject("This Termux build has no external command API. Use a build with RUN_COMMAND support; Android cannot show a permission that the installed app does not provide.")
            } else if (status.getBoolean("permission")) {
                invoke.resolve(status)
            } else {
                requestPermissionForAlias("termux", invoke, "runtimePermissionResult")
            }
        }
    }

    @PermissionCallback
    fun runtimePermissionResult(invoke: Invoke) {
        invoke.resolve(runtime.status())
    }

    @PermissionCallback
    fun storagePermissionResult(invoke: Invoke) {
        refreshStorage(invoke, true)
    }

    private fun refreshStorage(invoke: Invoke, createMissing: Boolean) {
        val request = JSONObject(invoke.parseArgs(RuntimeRequest::class.java).request)
        runtimeWorker.execute {
            try {
                val result = DeviceStorage(activity, request.getString("terminal_home")).status(createMissing)
                activity.runOnUiThread { invoke.resolve(result) }
            } catch (_: Exception) {
                activity.runOnUiThread { invoke.reject("Could not check shared storage; existing files were kept") }
            }
        }
    }

    @Command
    fun runtimeRequest(invoke: Invoke) {
        val arguments = invoke.parseArgs(RuntimeRequest::class.java)
        val action = JSONObject(arguments.request).optString("action")
        if (action == "device_storage_connect") {
            activity.runOnUiThread {
                try {
                    val storage = DeviceStorage(activity, JSONObject(arguments.request).getString("terminal_home"))
                    storage.optIn()
                    if (storage.granted()) refreshStorage(invoke, true)
                    else if (Build.VERSION.SDK_INT >= 30) {
                        storage.openSettings()
                        refreshStorage(invoke, false)
                    } else requestPermissionForAlias("storage", invoke, "storagePermissionResult")
                } catch (error: Exception) {
                    invoke.reject(error.message ?: "Open Android storage permissions, then check/refresh here")
                }
            }
            return
        }
        if (action == "device_storage_status" || action == "device_storage_refresh") {
            refreshStorage(invoke, action == "device_storage_refresh")
            return
        }
        if (action == "termux_open") {
            activity.runOnUiThread {
                try {
                    val intent = activity.packageManager.getLaunchIntentForPackage("com.termux")
                        ?: throw IllegalStateException("Install and open Termux first")
                    activity.startActivity(intent)
                    invoke.resolve(JSObject().put("opened", true))
                } catch (_: Exception) { invoke.reject("Open Termux from your Android launcher") }
            }
            return
        }
        if (JSONObject(arguments.request).optString("action") == "manual") {
            activity.runOnUiThread {
                try {
                    invoke.resolve(runtime.prepareManual())
                } catch (_: Exception) {
                    invoke.reject("Open Termux and try copying the connector again")
                }
            }
            return
        }
        if (JSONObject(arguments.request).optString("action") == "settings") {
            activity.runOnUiThread {
                try {
                    activity.startActivity(Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                        Uri.parse("package:${activity.packageName}")))
                    invoke.resolve(runtime.status())
                } catch (_: Exception) {
                    invoke.reject("Open Android Settings, Apps, Bifang, Permissions to allow Termux commands")
                }
            }
            return
        }
        runtimeWorker.execute {
            try {
                val request = JSONObject(arguments.request)
                val result = when (request.optString("action")) {
                    "native_check" -> NativeLinuxRuntime(activity).check()
                    "status" -> runtime.status()
                    "setup" -> runtime.setup()
                    "connect" -> runtime.connect()
                    "termux_storage_connect" -> runtime.setupStorage()
                    "termux_storage_status" -> runtime.storageStatus()
                    else -> runtime.request(request)
                }
                activity.runOnUiThread { invoke.resolve(JSObject(result.toString())) }
            } catch (error: Exception) {
                val message = if (error is IllegalStateException || error is IllegalArgumentException) error.message ?: "Runtime request failed" else "The distribution runtime disconnected; reconnect to continue"
                activity.runOnUiThread { invoke.reject(message.take(300)) }
            }
        }
    }

    @Command
    fun hardwareCheck(invoke: Invoke) {
        if (!checking.compareAndSet(false, true)) {
            invoke.reject("A hardware check is already running")
            return
        }
        Thread({
            try {
                val result = DeviceHardware.check()
                activity.runOnUiThread { invoke.resolve(result) }
            } catch (_: Exception) {
                activity.runOnUiThread { invoke.reject("Device hardware check failed") }
            } finally {
                checking.set(false)
            }
        }, "bifang-device-check").start()
    }
}
