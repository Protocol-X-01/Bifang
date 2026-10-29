package com.bifang.companion

import android.system.ErrnoException
import android.system.Os
import android.system.OsConstants
import org.apache.commons.compress.archivers.tar.TarArchiveInputStream
import org.apache.commons.compress.archivers.tar.TarUtils
import org.tukaani.xz.XZInputStream
import java.io.File
import java.io.InputStream
import java.io.InterruptedIOException
import java.security.MessageDigest
import java.util.UUID
import java.util.zip.GZIPInputStream

class NativeRootfsArchive(
    private val maxExpandedBytes: Long = 4L * 1024 * 1024 * 1024,
    private val maxEntries: Int = 200000,
) {
    data class Report(val entries: Int, val fileBytes: Long)
    private data class Link(val path: String, val target: String, val symbolic: Boolean)

    fun extract(
        archive: File,
        expectedSha256: String,
        destination: File,
        stripComponents: Int = 1,
        cancelled: () -> Boolean = { false },
        progress: (Long) -> Unit = {},
    ): Report {
        require(expectedSha256.matches(Regex("[a-f0-9]{64}"))) { "Invalid archive checksum" }
        require(stripComponents in 0..1) { "Unsupported archive prefix" }
        require(maxExpandedBytes > 0 && maxEntries > 0) { "Invalid extraction limits" }
        require(archive.isFile && archive.length() <= 1024L * 1024 * 1024) { "Invalid archive size" }
        val digest = MessageDigest.getInstance("SHA-256")
        archive.inputStream().buffered().use { input ->
            val buffer = ByteArray(65536)
            while (true) {
                checkCancelled(cancelled)
                val count = input.read(buffer)
                if (count < 0) break
                digest.update(buffer, 0, count)
            }
        }
        val actual = digest.digest().joinToString("") { "%02x".format(it.toInt() and 255) }
        require(actual == expectedSha256) { "Distribution archive checksum mismatch" }
        val parent = requireNotNull(destination.parentFile).canonicalFile
        require(parent.isDirectory) { "Installation parent does not exist" }
        val target = File(parent, destination.name)
        require(target.name !in setOf(".", "..") && !exists(target)) { "Installation already exists" }
        val staging = File(parent, ".rootfs-${UUID.randomUUID()}")
        check(staging.mkdir()) { "Could not create installation staging directory" }
        Os.chmod(staging.path, 448)
        var completed = false
        try {
            val links = mutableListOf<Link>()
            val directories = mutableListOf<Pair<File, Int>>()
            val seen = mutableSetOf<String>()
            var prefix: String? = null
            var count = 0
            var written = 0L
            fun relative(name: String): String {
                require(name.length <= 4096 && !name.startsWith('/') && '\u0000' !in name) { "Unsafe archive path" }
                val parts = name.split('/').filter { it.isNotEmpty() && it != "." }
                require(".." !in parts) { "Archive path escapes its root" }
                if (parts.isEmpty()) return ""
                if (stripComponents == 1) {
                    if (prefix == null) prefix = parts.first()
                    require(prefix == parts.first()) { "Archive contains multiple roots" }
                }
                return parts.drop(stripComponents).joinToString("/")
            }
            compressed(archive).use { decoded ->
                val bounded = TarBudgetStream(decoded, maxExpandedBytes, maxEntries, cancelled)
                TarArchiveInputStream(bounded).use { tar ->
                    val buffer = ByteArray(65536)
                    while (true) {
                        checkCancelled(cancelled)
                        val entry = tar.nextEntry ?: break
                        require(++count <= maxEntries && tar.canReadEntryData(entry) && !entry.isSparse) { "Unsupported or oversized archive" }
                        val name = relative(entry.name)
                        if (name.isEmpty()) {
                            require(entry.isDirectory) { "Archive root must be a directory" }
                            continue
                        }
                        require(seen.add(name)) { "Duplicate archive entry" }
                        val output = File(staging, name)
                        val ancestor = requireNotNull(output.parentFile)
                        check(ancestor.isDirectory || ancestor.mkdirs()) { "Could not create archive directory" }
                        when {
                            entry.isDirectory -> {
                                require(!exists(output) || isDirectory(output)) { "Conflicting archive directory" }
                                check(output.isDirectory || output.mkdir()) { "Could not create archive directory" }
                                directories.add(output to (entry.mode and 511))
                            }
                            entry.isSymbolicLink || entry.isLink -> {
                                require(!exists(output)) { "Conflicting archive link" }
                                val linkTarget = if (entry.isSymbolicLink) rebaseLink(name, entry.linkName) else relative(entry.linkName)
                                require(linkTarget.isNotEmpty()) { "Invalid archive link target" }
                                links.add(Link(name, linkTarget, entry.isSymbolicLink))
                            }
                            entry.isFile -> {
                                require(!exists(output) && entry.size in 0..maxExpandedBytes - written) { "Invalid archive file size" }
                                require(staging.usableSpace >= entry.size + 8L * 1024 * 1024) { "Not enough space for this distribution" }
                                var copied = 0L
                                output.outputStream().buffered().use { stream ->
                                    while (true) {
                                        checkCancelled(cancelled)
                                        val length = tar.read(buffer)
                                        if (length < 0) break
                                        copied += length
                                        require(copied <= entry.size) { "Archive file exceeds declared size" }
                                        stream.write(buffer, 0, length)
                                        progress(written + copied)
                                    }
                                }
                                require(copied == entry.size) { "Truncated archive file" }
                                written += copied
                                Os.chmod(output.path, entry.mode and 511)
                            }
                            else -> error("Unsupported archive entry type")
                        }
                    }
                    while (bounded.read(buffer) != -1) checkCancelled(cancelled)
                }
            }
            for (link in links.filter { !it.symbolic }) {
                checkCancelled(cancelled)
                val source = File(staging, link.target)
                require(exists(source) && OsConstants.S_ISREG(Os.lstat(source.path).st_mode)) { "Hard link target is not a regular file" }
                Os.link(source.path, File(staging, link.path).path)
            }
            for (link in links.filter { it.symbolic }) {
                checkCancelled(cancelled)
                val output = File(staging, link.path)
                require(!exists(output)) { "Conflicting archive link parent" }
                Os.symlink(link.target, output.path)
            }
            for ((directory, mode) in directories.sortedByDescending { it.first.path.length }) Os.chmod(directory.path, mode)
            checkCancelled(cancelled)
            require(!exists(target)) { "Installation destination changed" }
            check(staging.renameTo(target)) { "Could not finish distribution extraction" }
            completed = true
            return Report(count, written)
        } finally {
            if (!completed) removeTree(staging)
        }
    }

    private fun compressed(archive: File): InputStream {
        val input = archive.inputStream().buffered()
        try {
            input.mark(6)
            val magic = ByteArray(6)
            val count = input.read(magic)
            input.reset()
            return when {
                count == 6 && magic.contentEquals(byteArrayOf(-3, 55, 122, 88, 90, 0)) -> XZInputStream(input, 128 * 1024)
                count >= 2 && magic[0] == 31.toByte() && magic[1] == (-117).toByte() -> GZIPInputStream(input)
                else -> error("Unsupported distribution compression")
            }
        } catch (error: Exception) {
            input.close()
            throw error
        }
    }

    private fun rebaseLink(name: String, target: String): String {
        require(target.isNotEmpty() && target.length <= 4096 && '\u0000' !in target) { "Invalid symbolic link" }
        val parent = name.split('/').dropLast(1)
        val resolved = if (target.startsWith('/')) mutableListOf() else parent.toMutableList()
        for (part in target.split('/')) {
            when (part) {
                "", "." -> Unit
                ".." -> {
                    require(resolved.isNotEmpty()) { "Symbolic link escapes archive root" }
                    resolved.removeAt(resolved.lastIndex)
                }
                else -> resolved.add(part)
            }
        }
        var common = 0
        while (common < parent.size && common < resolved.size && parent[common] == resolved[common]) common++
        return (List(parent.size - common) { ".." } + resolved.drop(common)).joinToString("/").ifEmpty { "." }
    }

    private fun exists(file: File): Boolean = try {
        Os.lstat(file.path)
        true
    } catch (error: ErrnoException) {
        if (error.errno != OsConstants.ENOENT) throw error
        false
    }

    private fun isDirectory(file: File) = OsConstants.S_ISDIR(Os.lstat(file.path).st_mode)

    private fun removeTree(file: File) {
        if (!exists(file)) return
        if (isDirectory(file)) {
            Os.chmod(file.path, 448)
            for (child in file.listFiles() ?: error("Could not enumerate partial installation")) removeTree(child)
        }
        check(file.delete()) { "Could not remove partial installation" }
    }

    private fun checkCancelled(cancelled: () -> Boolean) {
        if (cancelled() || Thread.currentThread().isInterrupted) throw InterruptedIOException("Distribution installation cancelled")
    }

    private inner class TarBudgetStream(
        private val source: InputStream,
        private val limit: Long,
        private val entryLimit: Int,
        private val cancelled: () -> Boolean,
    ) : InputStream() {
        private var total = 0L
        private var headers = 0
        private var remaining = 0L
        private var header = ByteArray(0)
        private var position = 0
        private var ended = false

        override fun read(): Int {
            val single = ByteArray(1)
            return if (read(single, 0, 1) < 0) -1 else single[0].toInt() and 255
        }

        override fun read(buffer: ByteArray, offset: Int, length: Int): Int {
            if (length == 0) return 0
            checkCancelled(cancelled)
            if (position < header.size) {
                val count = minOf(length, header.size - position)
                header.copyInto(buffer, offset, position, position + count)
                position += count
                return count
            }
            if (remaining > 0 || ended) {
                val count = source.read(buffer, offset, if (ended) length else minOf(length.toLong(), remaining).toInt())
                if (count > 0) {
                    total += count
                    require(total <= limit) { "Expanded archive exceeds storage limit" }
                    if (!ended) remaining -= count
                } else if (!ended) error("Truncated tar archive")
                return count
            }
            header = ByteArray(512)
            position = 0
            var filled = 0
            while (filled < header.size) {
                val count = source.read(header, filled, header.size - filled)
                require(count > 0) { "Truncated tar header" }
                filled += count
            }
            total += 512
            require(total <= limit && ++headers <= entryLimit) { "Archive exceeds extraction limits" }
            ended = header.all { it == 0.toByte() }
            if (!ended) {
                val size = TarUtils.parseOctalOrBinary(header, 124, 12)
                require(size in 0..limit) { "Invalid tar entry size" }
                val kind = header[156].toInt().toChar()
                require(kind in setOf('\u0000', '0', '1', '2', '5', 'x', 'g', 'L', 'K')) { "Unsupported tar entry type" }
                if (kind in setOf('x', 'g', 'L', 'K')) require(size <= 65536) { "Archive metadata exceeds limit" }
                remaining = ((size + 511) / 512) * 512
            }
            return read(buffer, offset, length)
        }

        override fun close() = source.close()
    }
}
