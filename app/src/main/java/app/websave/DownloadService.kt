package app.websave

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.net.Uri
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import org.json.JSONObject
import kotlin.concurrent.thread

/**
 * Keeps downloads alive while the app is in the background and shows their progress
 * in a notification. Polls the local server and stops itself when nothing is left.
 */
class DownloadService : Service() {

    companion object {
        private const val CHANNEL_PROGRESS = "downloads"
        private const val CHANNEL_DONE = "finished"
        private const val ID_PROGRESS = 1
        private val ACTIVE = setOf("waiting_wifi", "queued", "retrying", "analyzing", "downloading",
            "merging", "converting", "trimming", "saving")

        fun start(context: Context) {
            ContextCompat.startForegroundService(context, Intent(context, DownloadService::class.java))
        }

        fun createChannels(context: Context) {
            val manager = context.getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL_PROGRESS, "Downloads in progress", NotificationManager.IMPORTANCE_LOW)
            )
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL_DONE, "Finished downloads", NotificationManager.IMPORTANCE_DEFAULT)
            )
        }
    }

    @Volatile private var running = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val notification = progress("Starting download", null, 0, true)
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(ID_PROGRESS, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(ID_PROGRESS, notification)
        }
        if (!running) {
            running = true
            thread(name = "websave-downloads") { watch() }
        }
        return START_NOT_STICKY
    }

    private fun watch() {
        val seen = HashMap<String, String>()
        var idle = 0
        try {
            while (true) {
                val body = Server.get("api/jobs")
                val jobs = body?.let { JSONObject(it).getJSONArray("jobs") }
                val active = ArrayList<JSONObject>()
                if (jobs != null) {
                    for (i in 0 until jobs.length()) {
                        val job = jobs.getJSONObject(i)
                        val id = job.getString("id")
                        val status = job.optString("status")
                        val before = seen[id]
                        if (before != null && before in ACTIVE && status !in ACTIVE) finished(job)
                        seen[id] = status
                        if (status in ACTIVE) active += job
                    }
                }
                if (active.isEmpty()) {
                    if (++idle >= 3) break
                } else {
                    idle = 0
                    showProgress(active)
                }
                Thread.sleep(1000)
            }
        } catch (_: Exception) {
        } finally {
            running = false
            if (Build.VERSION.SDK_INT >= 24) stopForeground(STOP_FOREGROUND_REMOVE) else @Suppress("DEPRECATION") stopForeground(true)
            stopSelf()
        }
    }

    private fun showProgress(active: List<JSONObject>) {
        val labels = mapOf("waiting_wifi" to "Waiting for Wi-Fi", "queued" to "Waiting in line",
            "retrying" to "Retrying", "merging" to "Merging", "converting" to "Creating GIF",
            "trimming" to "Trimming", "saving" to "Saving")
        val notification = if (active.size == 1) {
            val job = active[0]
            val status = job.optString("status")
            val percent = job.optDouble("progress", 0.0).toInt()
            val waiting = status in setOf("waiting_wifi", "queued", "analyzing", "retrying")
            progress(job.optString("title").ifBlank { "Downloading" },
                labels[status] ?: "Downloading $percent%", percent, waiting)
        } else {
            val percent = active.map { it.optDouble("progress", 0.0) }.average().toInt()
            progress("Saving ${active.size} items", "$percent% overall", percent, false)
        }
        notify(ID_PROGRESS, notification)
    }

    private fun progress(title: String, text: String?, percent: Int, indeterminate: Boolean) =
        NotificationCompat.Builder(this, CHANNEL_PROGRESS)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setContentText(text)
            .setOnlyAlertOnce(true)
            .setOngoing(true)
            .setProgress(100, percent, indeterminate)
            .setContentIntent(openApp())
            .build()

    private fun finished(job: JSONObject) {
        val title = job.optString("title").ifBlank { "Download" }
        val status = job.optString("status")
        if (status == "cancelled") return
        val builder = NotificationCompat.Builder(this, CHANNEL_DONE)
            .setSmallIcon(R.drawable.ic_notification)
            .setAutoCancel(true)
        if (status == "done") {
            val location = job.optString("location").ifBlank { "your gallery" }
            builder.setContentTitle("Saved: $title")
                .setContentText(job.optString("warning").ifBlank { "In $location" })
                .setContentIntent(openFile(job.optString("uri"), job.optString("mime")) ?: openApp())
        } else {
            builder.setContentTitle("Couldn't save: $title")
                .setContentText(job.optString("error"))
                .setStyle(NotificationCompat.BigTextStyle().bigText(job.optString("error")))
                .setContentIntent(openApp())
        }
        notify(job.getString("id").hashCode(), builder.build())
    }

    private fun notify(id: Int, notification: android.app.Notification) {
        try { NotificationManagerCompat.from(this).notify(id, notification) } catch (_: SecurityException) {}
    }

    private fun openApp(): PendingIntent = PendingIntent.getActivity(
        this, 0, Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
        PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
    )

    private fun openFile(uri: String, mime: String): PendingIntent? {
        if (uri.isBlank()) return null
        val view = Intent(Intent.ACTION_VIEW)
            .setDataAndType(Uri.parse(uri), mime.ifBlank { "video/*" })
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        return PendingIntent.getActivity(this, uri.hashCode(), view,
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    }
}
