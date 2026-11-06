package com.bifang.companion

import java.io.File

/** Filesystem policy shared by the Android adapter and host tests. Never replaces an entry. */
class SharedStorageLinks(
    private val home: File,
    private val root: File,
    private val createLink: (File, File) -> Unit,
) {
    data class Report(val state: String, val aliases: Map<String, String>, val conflicts: List<String>)

    companion object {
        val folders = linkedMapOf("shared" to "", "downloads" to "Download", "documents" to "Documents",
            "dcim" to "DCIM", "pictures" to "Pictures", "music" to "Music", "movies" to "Movies")
        // File.exists follows links and misses dangling links; directory entries do not.
        private fun present(file: File) = file.parentFile?.list()?.contains(file.name) == true
    }

    fun inspect(granted: Boolean, enabled: Boolean, createMissing: Boolean = false): Report {
        if (!enabled) return Report("not_connected", emptyMap(), emptyList())
        if (!granted) return Report("permission_needed", emptyMap(), emptyList())
        val storage = File(home, "storage")
        if (home.canonicalFile != home.absoluteFile ||
            present(storage) && (!storage.isDirectory || storage.canonicalFile != storage.absoluteFile)) {
            return Report("conflict", emptyMap(), listOf("storage"))
        }
        if (createMissing && !storage.isDirectory && !storage.mkdirs()) {
            return Report("unavailable", emptyMap(), emptyList())
        }
        val aliases = linkedMapOf<String, String>()
        val conflicts = mutableListOf<String>()
        for ((name, folder) in folders) {
            val target = File(root, folder)
            val link = File(storage, name)
            val accessible = target.canonicalFile == target.absoluteFile && target.isDirectory &&
                target.canRead() && target.canWrite() && target.list() != null
            if (!present(link) && accessible && createMissing) {
                try { createLink(target, link) } catch (_: Exception) { conflicts.add(name) }
            }
            if (present(link)) {
                if (accessible && link.canonicalFile == target.absoluteFile && link.canonicalFile != link.absoluteFile) {
                    aliases[name] = target.absolutePath
                } else if (name !in conflicts) conflicts.add(name)
            }
        }
        val state = when {
            aliases.size == folders.size -> "ready"
            aliases.isNotEmpty() -> "partial"
            conflicts.isNotEmpty() -> "conflict"
            else -> "unavailable"
        }
        return Report(state, aliases, conflicts)
    }
}
