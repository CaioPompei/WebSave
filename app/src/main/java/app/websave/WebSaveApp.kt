package app.websave

import android.app.Application
import kotlin.concurrent.thread

/** Starts the Python server as soon as the process starts, so every screen opens faster. */
class WebSaveApp : Application() {
    override fun onCreate() {
        super.onCreate()
        Native.context = this
        DownloadService.createChannels(this)
        thread(name = "websave-server") {
            try { Server.start(this) } catch (_: Throwable) {}
        }
    }
}
