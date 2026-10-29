package com.bifang.companion

import android.content.Context
import org.json.JSONObject
import java.io.File
import android.os.SystemClock

class NativeLinuxRuntime(private val context: Context) {
    fun check(): JSONObject = checkCommand(
        listOf("/system/bin/sh", "-c", "printf BIFANG_PROOT_OK"), "BIFANG_PROOT_OK", false)

    fun checkRootfs(rootfs: File): JSONObject {
        val root = rootfs.canonicalFile
        require(root.isDirectory && root.path.startsWith(context.filesDir.canonicalPath + File.separator)) {
            "Distribution must be in private application storage"
        }
        return checkCommand(listOf("-0", "-r", root.path, "-b", "/dev", "-b", "/proc", "-w", "/",
            "/bin/sh", "-c", "test -r /etc/os-release && printf BIFANG_ROOTFS_OK"), "BIFANG_ROOTFS_OK", true)
    }

    private fun checkCommand(arguments: List<String>, marker: String, rootfsTested: Boolean): JSONObject {
        val libraries = File(context.applicationInfo.nativeLibraryDir)
        val executable = File(libraries, "libbifang_proot.so")
        val loader = File(libraries, "libbifang_proot_loader.so")
        check(executable.isFile && executable.canExecute() && loader.isFile && loader.canExecute()) {
            "This build does not include the native Linux runtime"
        }
        val temporary = File(context.cacheDir, "linux-runtime")
        check(temporary.isDirectory || temporary.mkdirs()) { "Could not prepare runtime storage" }
        val output = File.createTempFile("probe-", ".log", temporary)
        val builder = ProcessBuilder(listOf(executable.absolutePath) + arguments)
            .directory(context.filesDir)
            .redirectErrorStream(true)
            .redirectOutput(output)
        builder.environment().apply {
            clear()
            put("PATH", "/system/bin")
            put("HOME", context.filesDir.absolutePath)
            put("TMPDIR", temporary.absolutePath)
            put("PROOT_TMP_DIR", temporary.absolutePath)
            put("PROOT_LOADER", loader.absolutePath)
        }
        var process: Process? = null
        try {
            process = builder.start()
            val deadline = SystemClock.elapsedRealtime() + 10000
            var exitCode: Int? = null
            while (exitCode == null && SystemClock.elapsedRealtime() < deadline) {
                try { exitCode = process.exitValue() }
                catch (_: IllegalThreadStateException) { Thread.sleep(25) }
            }
            check(exitCode != null) { "Native Linux runtime check timed out" }
            val result = output.inputStream().use {
                val bytes = ByteArray(8192)
                val count = it.read(bytes)
                if (count > 0) String(bytes, 0, count, Charsets.UTF_8) else ""
            }
            check(exitCode == 0 && result.trim() == marker) {
                "Native Linux runtime could not execute its test command (exit $exitCode)"
            }
            return JSONObject().put("passed", true).put("backend", "bundled-proot").put("rootfs_tested", rootfsTested)
        } finally {
            process?.destroy()
            output.delete()
        }
    }
}
