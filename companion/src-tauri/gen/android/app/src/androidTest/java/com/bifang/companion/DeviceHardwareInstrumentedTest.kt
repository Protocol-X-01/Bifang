package com.bifang.companion

import android.os.Bundle
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class DeviceHardwareInstrumentedTest {
    @Test
    fun parallelWorkersMatchReference() {
        val report = DeviceHardware.parallelCheck()
        assertTrue(report.getBoolean("passed"))
        assertTrue(report.getInt("workers_started") in 1..8)
        assertTrue(report.getInt("available_threads") >= report.getInt("workers_started"))
        InstrumentationRegistry.getInstrumentation().sendStatus(0, Bundle().apply {
            putString("bifang_cpu_check", report.toString())
        })
    }

    @Test
    fun gpuComputeMatchesEveryReferenceValue() {
        val report = DeviceHardware.gpuCheck()
        assertTrue(report.getBoolean("passed"))
        assertEquals(256, report.getInt("values_checked"))
        InstrumentationRegistry.getInstrumentation().sendStatus(0, Bundle().apply {
            putString("bifang_gpu_check", report.toString())
        })
    }
}
