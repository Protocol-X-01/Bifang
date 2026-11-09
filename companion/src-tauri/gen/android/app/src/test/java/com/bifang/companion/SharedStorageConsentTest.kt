package com.bifang.companion

import android.content.SharedPreferences
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File
import java.lang.reflect.Proxy
import java.nio.file.Files

class SharedStorageConsentTest {
    @get:Rule val temporary = TemporaryFolder()

    /** Reopening the adapter keeps committed values; unexpected clear/remove calls fail. */
    private class Preferences {
        val values = linkedMapOf("unrelated" to true)

        fun open(): SharedPreferences = Proxy.newProxyInstance(
            SharedPreferences::class.java.classLoader, arrayOf(SharedPreferences::class.java)
        ) { _, method, args ->
            when (method.name) {
                "getBoolean" -> values[args!![0] as String] ?: args[1]
                "edit" -> editor()
                else -> error("Unexpected preference operation: ${method.name}")
            }
        } as SharedPreferences

        private fun editor(): SharedPreferences.Editor {
            val pending = linkedMapOf<String, Boolean>()
            return Proxy.newProxyInstance(
                SharedPreferences.Editor::class.java.classLoader, arrayOf(SharedPreferences.Editor::class.java)
            ) { proxy, method, args ->
                when (method.name) {
                    "putBoolean" -> { pending[args!![0] as String] = args[1] as Boolean; proxy }
                    "apply" -> { values.putAll(pending); null }
                    else -> error("Unexpected preference edit: ${method.name}")
                }
            } as SharedPreferences.Editor
        }
    }

    @Test fun hostOptInsPersistIndependentlyAcrossDisconnectAndReconnect() {
        val preferences = Preferences()
        fun host(name: String) = SharedStorageConsent(preferences.open(), name)
        assertFalse(host("bifang").enabled())
        assertFalse(host("termux").enabled())
        host("bifang").setEnabled(true)
        host("termux").setEnabled(true)
        host("bifang").setEnabled(false)
        assertFalse(host("bifang").enabled())
        assertTrue(host("termux").enabled())
        host("bifang").setEnabled(true)
        host("termux").setEnabled(false)
        assertTrue(host("bifang").enabled())
        assertFalse(host("termux").enabled())
        host("termux").setEnabled(true)
        assertEquals(mapOf("unrelated" to true, "bifang" to true, "termux" to true), preferences.values)
    }

    @Test fun nativeDisconnectKeepsWorkingLinksAndDataAndReconnectOnlyFillsMissingLinks() {
        val preferences = Preferences()
        fun consent() = SharedStorageConsent(preferences.open(), "bifang")
        val home = temporary.newFolder("home")
        val root = temporary.newFolder("public")
        SharedStorageLinks.folders.values.filter { it.isNotEmpty() }.forEach { File(root, it).mkdir() }
        File(root, "Download/keep").writeText("synthetic")
        val links = SharedStorageLinks(home, root) { target, link ->
            Files.createSymbolicLink(link.toPath(), target.toPath())
        }
        consent().setEnabled(true)
        assertEquals("ready", links.inspect(true, consent().enabled(), true).state)
        val shared = File(home, "storage/shared").toPath()
        val original = Files.readSymbolicLink(shared)
        val downloads = File(home, "storage/downloads").toPath()
        Files.delete(downloads) // A synthetic owner change, never performed by disconnect.
        consent().setEnabled(false)
        assertEquals("not_connected", links.inspect(true, consent().enabled(), true).state)
        assertFalse(Files.exists(downloads))
        assertEquals(original, Files.readSymbolicLink(shared))
        assertEquals("synthetic", File(home, "storage/shared/Download/keep").readText())
        consent().setEnabled(true)
        assertEquals("ready", links.inspect(true, consent().enabled(), true).state)
        assertTrue(Files.isSymbolicLink(downloads))
        assertEquals(original, Files.readSymbolicLink(shared))
        assertEquals("synthetic", File(root, "Download/keep").readText())
    }
}
