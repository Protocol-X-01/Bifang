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
    private val consent = SharedStorageConsent(activity.getSharedPreferences("shared-storage", 0), "bifang")
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

    fun optIn() { consent.setEnabled(true) }

    fun optOut() { consent.setEnabled(false) }

    fun openSettings() {
        try {
            val action = if (Build.VERSION.SDK_INT >= 30) Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION
                else Settings.ACTION_APPLICATION_DETAILS_SETTINGS
            activity.startActivity(Intent(action,
                Uri.parse("package:${activity.packageName}")))
        } catch (_: android.content.ActivityNotFoundException) {
            throw IllegalStateException("Open Android Settings and review Bifang's storage permissions; on Android 11+, use Special app access, All files access. Then check/refresh here")
        }
    }

    @Suppress("DEPRECATION")
    fun status(createMissing: Boolean = false): JSObject {
        val enabled = consent.enabled()
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
