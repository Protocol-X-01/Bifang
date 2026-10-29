package com.bifang.companion

import android.opengl.EGL14
import android.opengl.GLES30
import android.opengl.GLES31
import app.tauri.plugin.JSObject
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

object DeviceHardware {
    private const val ELEMENTS = 256

    fun parallelCheck(): JSObject {
        val available = Runtime.getRuntime().availableProcessors().coerceAtLeast(1)
        val workers = available.coerceAtMost(8)
        val ready = CountDownLatch(workers)
        val start = CountDownLatch(1)
        val values = LongArray(workers)
        val threads = (0 until workers).map { worker ->
            Thread({
                ready.countDown()
                start.await()
                var result = 0L
                for (index in 0 until 100000) result += index.toLong() * index + worker
                values[worker] = result
            }, "bifang-worker-$worker")
        }
        threads.forEach { it.start() }
        val allReady = ready.await(3, TimeUnit.SECONDS)
        start.countDown()
        threads.forEach { it.join(3000) }
        check(allReady && threads.none { it.isAlive })
        val count = 100000L
        val squares = count * (count - 1) * (2 * count - 1) / 6
        check(values.indices.all { values[it] == squares + count * it })
        return JSObject().apply {
            put("available_threads", available)
            put("workers_started", workers)
            put("passed", true)
        }
    }

    fun check(): JSObject = JSObject().apply {
        put("cpu", parallelCheck())
        try {
            put("gpu", gpuCheck())
            put("gpu_error", null)
        } catch (_: Exception) {
            put("gpu", null)
            put("gpu_error", "OpenGL ES compute is unavailable or the result check failed")
        }
    }

    fun gpuCheck(): JSObject {
        val display = EGL14.eglGetDisplay(EGL14.EGL_DEFAULT_DISPLAY)
        check(display != EGL14.EGL_NO_DISPLAY)
        val version = IntArray(2)
        check(EGL14.eglInitialize(display, version, 0, version, 1))
        var context = EGL14.EGL_NO_CONTEXT
        var surface = EGL14.EGL_NO_SURFACE
        var shader = 0
        var program = 0
        val buffers = IntArray(1)
        try {
            check(EGL14.eglBindAPI(EGL14.EGL_OPENGL_ES_API))
            val configs = arrayOfNulls<android.opengl.EGLConfig>(1)
            val found = IntArray(1)
            check(EGL14.eglChooseConfig(display, intArrayOf(
                EGL14.EGL_RENDERABLE_TYPE, 0x0040,
                EGL14.EGL_SURFACE_TYPE, EGL14.EGL_PBUFFER_BIT,
                EGL14.EGL_RED_SIZE, 8, EGL14.EGL_GREEN_SIZE, 8, EGL14.EGL_BLUE_SIZE, 8,
                EGL14.EGL_NONE
            ), 0, configs, 0, 1, found, 0) && found[0] > 0)
            context = EGL14.eglCreateContext(display, configs[0], EGL14.EGL_NO_CONTEXT,
                intArrayOf(EGL14.EGL_CONTEXT_CLIENT_VERSION, 3, EGL14.EGL_NONE), 0)
            check(context != EGL14.EGL_NO_CONTEXT)
            surface = EGL14.eglCreatePbufferSurface(display, configs[0],
                intArrayOf(EGL14.EGL_WIDTH, 1, EGL14.EGL_HEIGHT, 1, EGL14.EGL_NONE), 0)
            check(surface != EGL14.EGL_NO_SURFACE)
            check(EGL14.eglMakeCurrent(display, surface, surface, context))
            val renderer = GLES31.glGetString(GLES31.GL_RENDERER) ?: error("Missing renderer")
            val api = GLES31.glGetString(GLES31.GL_VERSION) ?: error("Missing API")
            shader = GLES31.glCreateShader(GLES31.GL_COMPUTE_SHADER)
            GLES31.glShaderSource(shader, """
                #version 310 es
                layout(local_size_x = 64) in;
                layout(std430, binding = 0) buffer Values { uint values[]; };
                void main() {
                    uint index = gl_GlobalInvocationID.x;
                    if (index < 256u) values[index] = values[index] * 3u + 7u;
                }
            """.trimIndent())
            GLES31.glCompileShader(shader)
            val status = IntArray(1)
            GLES31.glGetShaderiv(shader, GLES31.GL_COMPILE_STATUS, status, 0)
            check(status[0] == GLES31.GL_TRUE)
            program = GLES31.glCreateProgram()
            GLES31.glAttachShader(program, shader)
            GLES31.glLinkProgram(program)
            GLES31.glGetProgramiv(program, GLES31.GL_LINK_STATUS, status, 0)
            check(status[0] == GLES31.GL_TRUE)
            val initial = ByteBuffer.allocateDirect(ELEMENTS * 4).order(ByteOrder.nativeOrder())
            for (index in 0 until ELEMENTS) initial.putInt(index)
            initial.rewind()
            GLES31.glGenBuffers(1, buffers, 0)
            GLES31.glBindBuffer(GLES31.GL_SHADER_STORAGE_BUFFER, buffers[0])
            GLES31.glBufferData(GLES31.GL_SHADER_STORAGE_BUFFER, ELEMENTS * 4, initial, GLES30.GL_DYNAMIC_READ)
            GLES31.glBindBufferBase(GLES31.GL_SHADER_STORAGE_BUFFER, 0, buffers[0])
            GLES31.glUseProgram(program)
            GLES31.glDispatchCompute(4, 1, 1)
            GLES31.glMemoryBarrier(GLES31.GL_BUFFER_UPDATE_BARRIER_BIT)
            GLES31.glFinish()
            val result = GLES31.glMapBufferRange(GLES31.GL_SHADER_STORAGE_BUFFER, 0, ELEMENTS * 4,
                GLES30.GL_MAP_READ_BIT) as? ByteBuffer ?: error("GPU readback unavailable")
            val passed = try {
                result.order(ByteOrder.nativeOrder())
                (0 until ELEMENTS).all { result.getInt(it * 4) == it * 3 + 7 }
            } finally {
                GLES31.glUnmapBuffer(GLES31.GL_SHADER_STORAGE_BUFFER)
            }
            check(passed && GLES31.glGetError() == GLES31.GL_NO_ERROR)
            return JSObject().apply {
                put("renderer", renderer.take(256))
                put("api", api.take(256))
                put("values_checked", ELEMENTS)
                put("passed", true)
            }
        } finally {
            if (context != EGL14.EGL_NO_CONTEXT) {
                if (buffers[0] != 0) GLES31.glDeleteBuffers(1, buffers, 0)
                if (program != 0) GLES31.glDeleteProgram(program)
                if (shader != 0) GLES31.glDeleteShader(shader)
                EGL14.eglMakeCurrent(display, EGL14.EGL_NO_SURFACE, EGL14.EGL_NO_SURFACE, EGL14.EGL_NO_CONTEXT)
            }
            if (surface != EGL14.EGL_NO_SURFACE) EGL14.eglDestroySurface(display, surface)
            if (context != EGL14.EGL_NO_CONTEXT) EGL14.eglDestroyContext(display, context)
            EGL14.eglTerminate(display)
        }
    }
}
