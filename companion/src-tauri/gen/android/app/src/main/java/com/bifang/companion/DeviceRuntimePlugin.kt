package com.bifang.companion

import android.app.Activity
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

@TauriPlugin(permissions = [Permission(strings = ["com.termux.permission.RUN_COMMAND"], alias = "termux")])
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

    @Command
    fun runtimeRequest(invoke: Invoke) {
        val arguments = invoke.parseArgs(RuntimeRequest::class.java)
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
