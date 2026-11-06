package com.bifang.companion

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.Settings
import android.system.Os
import app.tauri.plugin.JSObject
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

class DeviceStorage(private val activity: Activity, terminalHome: String) {
    private val preferences = activity.getSharedPreferences("shared-storage", 0)
    private val home = File(terminalHome).canonicalFile

    init {
        // terminalHome comes from Rust's app_data_dir, the same source used by terminal_open.
        require(home == File(activity.dataDir.canonicalFile, "projects/terminal")) {
            "Terminal HOME must stay in Bifang project storage"
        }
    }

    fun granted(): Boolean = if (Build.VERSION.SDK_INT >= 30) Environment.isExternalStorageManager() else
        activity.checkSelfPermission(Manifest.permission.READ_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED &&
            activity.checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED

    fun optIn() { preferences.edit().putBoolean("bifang", true).apply() }

    fun openSettings() {
        check(Build.VERSION.SDK_INT >= 30) { "Use Android's storage permission dialog" }
        try {
            activity.startActivity(Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION,
                Uri.parse("package:${activity.packageName}")))
        } catch (_: android.content.ActivityNotFoundException) {
            throw IllegalStateException("Open Android Settings, Special app access, All files access, and select Bifang; then check/refresh here")
        }
    }

    @Suppress("DEPRECATION")
    fun status(createMissing: Boolean = false): JSObject {
        val enabled = preferences.getBoolean("bifang", false)
        val permission = granted()
        val report = SharedStorageLinks(home, Environment.getExternalStorageDirectory().canonicalFile) { target, link ->
            Os.symlink(target.absolutePath, link.absolutePath)
        }.inspect(permission, enabled, createMissing)
        return JSObject().apply {
            put("host", "bifang")
            put("home", home.absolutePath)
            put("enabled", enabled)
            put("permission", permission)
            put("state", report.state)
            put("aliases", JSONObject(report.aliases))
            put("conflicts", JSONArray(report.conflicts))
        }
    }
}
