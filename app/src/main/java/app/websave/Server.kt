package app.websave

import android.app.ActivityManager
import android.content.Context
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.net.HttpURLConnection
import java.net.ServerSocket
import java.net.URL

/** The local Python server (websave.py). One per app process, shared by every screen and the service. */
object Server {

    @Volatile var port = 0
        private set
    private val lock = Any()

    val base: String get() = "http://127.0.0.1:$port/"

    fun start(context: Context) {
        synchronized(lock) {
            if (port != 0) return
            val app = context.applicationContext
            Native.context = app
            if (!Python.isStarted()) Python.start(AndroidPlatform(app))
            val free = ServerSocket(0).use { it.localPort }
            Python.getInstance().getModule("websave").callAttr(
                "start", free, app.filesDir.absolutePath, app.cacheDir.absolutePath,
                app.applicationInfo.nativeLibraryDir, isLightDevice(app)
            )
            port = free
        }
    }

    /**
     * Older or low-memory phones (under 3 GB of RAM, or Android Go): the engine runs one
     * download at a time and makes lighter GIFs so the phone stays responsive.
     */
    fun isLightDevice(context: Context): Boolean {
        val manager = context.getSystemService(ActivityManager::class.java) ?: return false
        val memory = ActivityManager.MemoryInfo().also { manager.getMemoryInfo(it) }
        return manager.isLowRamDevice || memory.totalMem < 3_000_000_000L
    }

    /** Start if needed and wait until the server answers. Call off the main thread. */
    fun awaitReady(context: Context, timeoutMs: Long = 30_000): Boolean {
        start(context)
        val until = System.currentTimeMillis() + timeoutMs
        while (System.currentTimeMillis() < until) {
            if (get("api/ping") != null) return true
            Thread.sleep(250)
        }
        return false
    }

    /** GET a path on the local server; null if it doesn't answer. */
    fun get(path: String): String? = try {
        val connection = URL(base + path).openConnection() as HttpURLConnection
        connection.connectTimeout = 1000
        connection.readTimeout = 3000
        if (connection.responseCode == 200) connection.inputStream.bufferedReader().use { it.readText() } else null
    } catch (_: Exception) {
        null
    }
}
