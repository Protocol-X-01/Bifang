package com.bifang.companion

import android.os.Bundle
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.io.File

@RunWith(AndroidJUnit4::class)
class NativeLinuxRuntimeInstrumentedTest {
    @Test
    fun bundledRuntimeExecutesWithoutTermux() {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val before = File(context.cacheDir, "linux-runtime").listFiles()?.map { it.name }?.toSet() ?: emptySet()
        repeat(2) {
            val report = NativeLinuxRuntime(context).check()
            assertTrue(report.getBoolean("passed"))
            assertEquals("bundled-proot", report.getString("backend"))
            assertFalse(report.getBoolean("rootfs_tested"))
            instrumentation.sendStatus(0, Bundle().apply {
                putString("bifang_native_runtime_check", report.toString())
            })
        }
        val after = File(context.cacheDir, "linux-runtime").listFiles()?.map { it.name }?.toSet() ?: emptySet()
        assertEquals(before, after)
    }
}
