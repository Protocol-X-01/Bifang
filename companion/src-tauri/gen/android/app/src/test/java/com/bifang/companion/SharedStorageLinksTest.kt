package com.bifang.companion

import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.nio.file.Files

class SharedStorageLinksTest {
    @get:Rule val temporary = TemporaryFolder()

    private fun policy(home: File, root: File) = SharedStorageLinks(home, root) { target, link ->
        Files.createSymbolicLink(link.toPath(), target.toPath())
    }

    private fun folders(): File = temporary.newFolder("shared").also { root ->
        SharedStorageLinks.folders.values.filter { it.isNotEmpty() }.forEach { File(root, it).mkdir() }
    }

    @Test fun permissionAndOptInAreBothRequiredAndChecksNeverCreateLinks() {
        val home = temporary.newFolder("home")
        val root = folders()
        val links = policy(home, root)
        assertEquals("not_connected", links.inspect(true, false, true).state)
        assertEquals("permission_needed", links.inspect(false, true, true).state)
        assertEquals("unavailable", links.inspect(true, true).state)
        assertFalse(File(home, "storage").exists())
        assertEquals("ready", links.inspect(true, true, true).state)
        assertEquals(7, links.inspect(true, true).aliases.size)
        assertEquals("permission_needed", links.inspect(false, true).state)
        assertTrue(File(home, "storage/shared").exists()) // Revocation never removes data.
    }

    @Test fun existingFilesAndDanglingLinksAreNeverReplaced() {
        val home = temporary.newFolder("home")
        val root = folders()
        val storage = File(home, "storage").apply { mkdir() }
        File(storage, "downloads").writeText("keep")
        val dangling = File(storage, "documents").toPath()
        Files.createSymbolicLink(dangling, File(home, "missing").toPath())
        val result = policy(home, root).inspect(true, true, true)
        assertEquals("partial", result.state)
        assertTrue(result.conflicts.containsAll(listOf("downloads", "documents")))
        assertEquals("keep", File(storage, "downloads").readText())
        assertEquals(File(home, "missing").toPath(), Files.readSymbolicLink(dangling))
    }

    @Test fun storageAndPublicTargetRedirectsCannotExposePrivateFiles() {
        val home = temporary.newFolder("home")
        val root = folders()
        val private = File(home, ".ssh").apply { mkdir() }
        Files.createSymbolicLink(File(home, "storage").toPath(), private.toPath())
        assertEquals("conflict", policy(home, root).inspect(true, true, true).state)
        assertTrue(private.list()!!.isEmpty())
        Files.delete(File(home, "storage").toPath())
        File(root, "Download").delete()
        Files.createSymbolicLink(File(root, "Download").toPath(), private.toPath())
        val result = policy(home, root).inspect(true, true, true)
        assertFalse(result.aliases.containsKey("downloads"))
        assertFalse(File(home, "storage/downloads").exists())
    }
}
