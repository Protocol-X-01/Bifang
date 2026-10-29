package com.bifang.companion

import android.os.Bundle
import android.system.Os
import android.system.OsConstants
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.apache.commons.compress.archivers.tar.TarArchiveEntry
import org.apache.commons.compress.archivers.tar.TarArchiveOutputStream
import org.apache.commons.compress.archivers.tar.TarConstants
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File
import java.security.MessageDigest
import java.util.UUID
import java.util.zip.GZIPOutputStream

@RunWith(AndroidJUnit4::class)
class NativeRootfsArchiveInstrumentedTest {
    private data class Entry(val name: String, val data: String = "", val type: Byte = TarConstants.LF_NORMAL, val target: String = "")

    private fun digest(file: File): String = MessageDigest.getInstance("SHA-256").digest(file.readBytes())
        .joinToString("") { "%02x".format(it.toInt() and 255) }

    private fun fixture(parent: File, entries: List<Entry>): File {
        val archive = File(parent, "fixture.tar.gz")
        TarArchiveOutputStream(GZIPOutputStream(archive.outputStream())).use { stream ->
            stream.setLongFileMode(TarArchiveOutputStream.LONGFILE_POSIX)
            for (item in entries) {
                val entry = if (item.type == TarConstants.LF_NORMAL) TarArchiveEntry(item.name, true) else TarArchiveEntry(item.name, item.type)
                entry.mode = 493
                entry.size = if (item.type == TarConstants.LF_NORMAL) item.data.toByteArray().size.toLong() else 0
                entry.linkName = item.target
                stream.putArchiveEntry(entry)
                if (entry.size > 0) stream.write(item.data.toByteArray())
                stream.closeArchiveEntry()
            }
        }
        return archive
    }

    private fun cleanup(file: File) {
        val mode = Os.lstat(file.path).st_mode
        if (OsConstants.S_ISDIR(mode)) {
            Os.chmod(file.path, 448)
            for (child in file.listFiles() ?: emptyArray()) cleanup(child)
        }
        assertTrue(file.delete())
    }

    private fun directory(test: (File) -> Unit) {
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        val parent = File(context.filesDir, "rootfs-test-${UUID.randomUUID()}")
        assertTrue(parent.mkdir())
        try { test(parent) } finally { cleanup(parent) }
    }

    private fun rejected(parent: File, operation: () -> Unit) {
        var failure: Exception? = null
        try { operation() } catch (error: Exception) { failure = error }
        assertTrue("Invalid archive was accepted", failure != null)
        assertFalse(File(parent, "installed").exists())
        assertTrue(parent.listFiles()!!.none { it.name.startsWith(".rootfs-") })
    }

    @Test
    fun filesLinksAndExecutableModesSurviveExtraction() = directory { parent ->
        val archive = fixture(parent, listOf(Entry("root/bin/tool", "payload"),
            Entry("root/hard", type = TarConstants.LF_LINK, target = "root/bin/tool"),
            Entry("root/absolute", type = TarConstants.LF_SYMLINK, target = "/bin/tool")))
        val destination = File(parent, "installed")
        val report = NativeRootfsArchive().extract(archive, digest(archive), destination)
        assertEquals(3, report.entries)
        assertEquals(7L, report.fileBytes)
        assertEquals("payload", File(destination, "absolute").readText())
        assertEquals("bin/tool", Os.readlink(File(destination, "absolute").path))
        assertEquals(Os.stat(File(destination, "bin/tool").path).st_ino, Os.stat(File(destination, "hard").path).st_ino)
        assertTrue(File(destination, "bin/tool").canExecute())
    }

    @Test
    fun wrongChecksumCreatesNoInstallation() = directory { parent ->
        val archive = fixture(parent, listOf(Entry("root/file", "payload")))
        rejected(parent) { NativeRootfsArchive().extract(archive, "0".repeat(64), File(parent, "installed")) }
    }

    @Test
    fun traversalAndAbsoluteNamesAreRejected() = directory { parent ->
        for (name in listOf("root/../escape", "/absolute/escape")) {
            val archive = fixture(parent, listOf(Entry(name, "payload")))
            rejected(parent) { NativeRootfsArchive().extract(archive, digest(archive), File(parent, "installed")) }
        }
        assertFalse(File(parent, "escape").exists())
    }

    @Test
    fun linkEscapeAndLinkParentWritesAreRejected() = directory { parent ->
        val cases = listOf(
            listOf(Entry("root/link", type = TarConstants.LF_SYMLINK, target = "../../outside")),
            listOf(Entry("root/link", type = TarConstants.LF_LINK, target = "root/../outside")),
            listOf(Entry("root/alias", type = TarConstants.LF_SYMLINK, target = "/outside"),
                Entry("root/alias/file", "payload")),
        )
        for (entries in cases) {
            val archive = fixture(parent, entries)
            rejected(parent) { NativeRootfsArchive().extract(archive, digest(archive), File(parent, "installed")) }
        }
    }

    @Test
    fun existingInstallIsPreserved() = directory { parent ->
        val destination = File(parent, "installed")
        assertTrue(destination.mkdir())
        File(destination, "keep").writeText("original")
        val archive = fixture(parent, listOf(Entry("root/file", "payload")))
        var rejected = false
        try { NativeRootfsArchive().extract(archive, digest(archive), destination) }
        catch (_: IllegalArgumentException) { rejected = true }
        assertTrue(rejected)
        assertEquals("original", File(destination, "keep").readText())
    }

    @Test
    fun expansionAndEntryLimitsCleanUp() = directory { parent ->
        val archive = fixture(parent, listOf(Entry("root/file", "payload".repeat(500)), Entry("root/second", "second")))
        rejected(parent) { NativeRootfsArchive(maxExpandedBytes = 1024).extract(archive, digest(archive), File(parent, "installed")) }
        rejected(parent) { NativeRootfsArchive(maxEntries = 1).extract(archive, digest(archive), File(parent, "installed")) }
    }

    @Test
    fun cancellationRemovesPartialFiles() = directory { parent ->
        val archive = fixture(parent, listOf(Entry("root/file", "payload")))
        var cancelled = false
        rejected(parent) {
            NativeRootfsArchive().extract(archive, digest(archive), File(parent, "installed"),
                cancelled = { cancelled }, progress = { cancelled = true })
        }
        assertTrue(cancelled)
    }

    @Test
    fun corruptCompressionFooterIsRejected() = directory { parent ->
        val archive = fixture(parent, listOf(Entry("root/file", "payload")))
        val bytes = archive.readBytes()
        bytes[bytes.lastIndex] = (bytes.last().toInt() xor 1).toByte()
        archive.writeBytes(bytes)
        rejected(parent) { NativeRootfsArchive().extract(archive, digest(archive), File(parent, "installed")) }
    }

    @Test
    fun oversizedMetadataAndDuplicateEntriesAreRejected() = directory { parent ->
        val metadata = fixture(parent, listOf(Entry("root/" + "a".repeat(70000), "payload")))
        rejected(parent) { NativeRootfsArchive().extract(metadata, digest(metadata), File(parent, "installed")) }
        val duplicate = fixture(parent, listOf(Entry("root/file", "first"), Entry("root/file", "second")))
        rejected(parent) { NativeRootfsArchive().extract(duplicate, digest(duplicate), File(parent, "installed")) }
    }

    @Test
    fun pinnedAlpineExtractsAndRunsWithoutTermux() = directory { parent ->
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val archive = File(parent, "alpine.tar.xz")
        instrumentation.targetContext.assets.open("rootfs-test/alpine.tar.xz").use { input ->
            archive.outputStream().use { output -> input.copyTo(output) }
        }
        val destination = File(parent, "installed")
        val report = NativeRootfsArchive().extract(archive,
            "bb23e51cd5b5ae56bf946a34992876902de1bb2ecc0f639d59c702c6371adc62", destination)
        assertTrue(File(destination, "etc/alpine-release").isFile)
        val result = NativeLinuxRuntime(instrumentation.targetContext).checkRootfs(destination)
        assertTrue(result.getBoolean("passed") && result.getBoolean("rootfs_tested"))
        result.put("archive_sha256", digest(archive)).put("entries", report.entries).put("file_bytes", report.fileBytes)
        instrumentation.sendStatus(0, Bundle().apply { putString("bifang_native_rootfs_check", result.toString()) })
    }
}
