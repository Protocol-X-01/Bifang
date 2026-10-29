package com.bifang.companion

import android.app.Activity
import android.content.Intent
import android.content.ComponentName
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.os.PersistableBundle
import android.util.Base64
import android.content.pm.PackageManager
import app.tauri.plugin.JSObject
import org.json.JSONObject
import java.io.DataInputStream
import java.io.DataOutputStream
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

class TermuxRuntime(private val activity: Activity) {
    private var port = 0
    private var key = ByteArray(0)
    private val random = SecureRandom()
    private var manualConnection = false

    fun status(): JSObject = JSObject().apply {
        val installed = try {
            activity.packageManager.getPackageInfo("com.termux", 0)
            true
        } catch (_: PackageManager.NameNotFoundException) { false }
        put("installed", installed)
        val commandApi = if (installed) try {
            activity.packageManager.getPermissionInfo("com.termux.permission.RUN_COMMAND", 0)
            val service = activity.packageManager.getServiceInfo(ComponentName("com.termux", "com.termux.app.RunCommandService"), 0)
            service.exported && service.enabled
        } catch (_: PackageManager.NameNotFoundException) { false } else false
        put("command_api", commandApi)
        put("permission", activity.checkSelfPermission("com.termux.permission.RUN_COMMAND") == PackageManager.PERMISSION_GRANTED)
    }

    private fun run(path: String, arguments: Array<String>, background: Boolean) {
        check(status().getBoolean("installed")) { "Install and open Termux first" }
        check(status().getBoolean("command_api")) { "This Termux build does not support external commands. Choose a Termux build with RUN_COMMAND support, or use the Android system shell." }
        check(status().getBoolean("permission")) { "Allow Bifang to run Termux commands first" }
        val intent = Intent("com.termux.RUN_COMMAND").apply {
            setClassName("com.termux", "com.termux.app.RunCommandService")
            putExtra("com.termux.RUN_COMMAND_PATH", path)
            putExtra("com.termux.RUN_COMMAND_ARGUMENTS", arguments)
            putExtra("com.termux.RUN_COMMAND_WORKDIR", "/data/data/com.termux/files/home")
            putExtra("com.termux.RUN_COMMAND_BACKGROUND", background)
            putExtra("com.termux.RUN_COMMAND_SESSION_ACTION", "0")
            putExtra("com.termux.RUN_COMMAND_COMMAND_LABEL", "Bifang distributions")
        }
        check(activity.startService(intent) != null) { "Termux could not start" }
    }

    @Synchronized
    fun setup(): JSObject {
        run("/data/data/com.termux/files/usr/bin/bash", arrayOf("-c", "pkg install -y python proot curl tar xz-utils bzip2 gzip unzip file util-linux gawk coreutils findutils grep sed"), false)
        return JSObject().put("dispatched", true)
    }

    @Synchronized
    fun prepareManual(): JSObject {
        check(status().getBoolean("installed")) { "Install and open Termux first" }
        if (port == 0) {
            port = ServerSocket(0, 1, InetAddress.getByName("127.0.0.1")).use { it.localPort }
            key = ByteArray(32).also { random.nextBytes(it) }
        }
        manualConnection = true
        val source = activity.assets.open("bifang_runtime.py").use { it.readBytes() }
        val encoded = Base64.encodeToString(source, Base64.NO_WRAP)
        val command = "python -c 'import base64;exec(compile(base64.b64decode(\"$encoded\"),\"bifang_runtime.py\",\"exec\"))' $port ${hex(key)}"
        val clipboard = activity.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        val clip = ClipData.newPlainText("Bifang private connector", command)
        clip.description.extras = PersistableBundle().apply { putBoolean("android.content.extra.IS_SENSITIVE", true) }
        clipboard.setPrimaryClip(clip)
        return JSObject().put("clipboard_ready", true)
    }

    @Synchronized
    fun connect(): JSONObject {
        if (port != 0) {
            try {
                val result = exchange(JSONObject().put("action", "catalog"))
                if (manualConnection) activity.runOnUiThread {
                    val clipboard = activity.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                    if (clipboard.primaryClipDescription?.label?.toString() == "Bifang private connector") {
                        clipboard.setPrimaryClip(ClipData.newPlainText("", ""))
                    }
                }
                manualConnection = false
                return result
            } catch (_: Exception) {
                check(!manualConnection) { "Run the copied connector inside Termux, then return to Bifang and connect. It needs Python installed in Termux." }
            }
        }
        port = ServerSocket(0, 1, InetAddress.getByName("127.0.0.1")).use { it.localPort }
        key = ByteArray(32).also { random.nextBytes(it) }
        val source = activity.assets.open("bifang_runtime.py").bufferedReader().use { it.readText() }
        run("/data/data/com.termux/files/usr/bin/python", arrayOf("-c", source, port.toString(), hex(key)), true)
        repeat(24) {
            try { return exchange(JSONObject().put("action", "catalog")) } catch (_: Exception) { Thread.sleep(250) }
        }
        port = 0
        key.fill(0)
        throw IllegalStateException("Termux did not connect. Complete Install runtime tools and enable allow-external-apps in Termux, then reconnect.")
    }

    @Synchronized
    fun request(request: JSONObject): JSONObject {
        val action = request.optString("action")
        require(action in setOf("catalog", "terminal_open", "terminal_read", "terminal_write", "terminal_resize", "terminal_close", "stop")) { "Unknown runtime action" }
        check(port != 0) { "Connect the distribution runtime first" }
        return exchange(request)
    }

    private fun hex(bytes: ByteArray): String = bytes.joinToString("") { "%02x".format(it.toInt() and 255) }

    private fun proof(nonce: ByteArray, role: String): String {
        val mac = Mac.getInstance("HmacSHA256")
        mac.init(SecretKeySpec(key, "HmacSHA256"))
        return hex(mac.doFinal(nonce + role.toByteArray(Charsets.UTF_8)))
    }

    private fun exchange(request: JSONObject): JSONObject {
        Socket().use { socket ->
            socket.connect(InetSocketAddress("127.0.0.1", port), 750)
            socket.soTimeout = 5000
            val output = DataOutputStream(socket.getOutputStream())
            val input = DataInputStream(socket.getInputStream())
            fun send(value: JSONObject) {
                val bytes = value.toString().toByteArray(Charsets.UTF_8)
                require(bytes.size in 1..131072) { "Runtime request too large" }
                output.writeInt(bytes.size)
                output.write(bytes)
                output.flush()
            }
            fun receive(): JSONObject {
                val size = input.readInt()
                require(size in 1..131072) { "Invalid runtime response" }
                val bytes = ByteArray(size)
                input.readFully(bytes)
                return JSONObject(String(bytes, Charsets.UTF_8))
            }
            val nonce = ByteArray(32).also { random.nextBytes(it) }
            send(JSONObject().put("nonce", hex(nonce)))
            val hello = receive()
            val remoteNonce = hello.optString("nonce")
            require(remoteNonce.matches(Regex("[0-9a-f]{64}"))) { "Invalid runtime challenge" }
            val challenge = nonce + remoteNonce.chunked(2).map { it.toInt(16).toByte() }.toByteArray()
            val actual = hello.optString("proof").toByteArray(Charsets.UTF_8)
            check(MessageDigest.isEqual(actual, proof(challenge, "server").toByteArray(Charsets.UTF_8))) { "Runtime authentication failed" }
            send(JSONObject().put("proof", proof(challenge, "client")).put("request", request))
            val response = receive()
            if (response.has("error")) throw IllegalStateException(response.getString("error").take(300))
            return response.getJSONObject("result")
        }
    }
}
