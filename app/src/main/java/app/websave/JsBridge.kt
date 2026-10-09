package app.websave

import android.Manifest
import android.app.Activity
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.webkit.JavascriptInterface
import android.widget.Toast
import java.util.concurrent.FutureTask
import java.util.concurrent.TimeUnit

/** Android features the page calls through window.WebSaveAndroid. */
class JsBridge(private val activity: Activity) {

    @JavascriptInterface
    fun paste(): String {
        val task = FutureTask {
            val clipboard = activity.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val clip = clipboard.primaryClip
            if (clip == null || clip.itemCount == 0) "" else clip.getItemAt(0).coerceToText(activity).toString()
        }
        activity.runOnUiThread(task)
        return try { task.get(2, TimeUnit.SECONDS) } catch (_: Exception) { "" }
    }

    @JavascriptInterface
    fun open(uri: String, mime: String) = activity.runOnUiThread {
        try {
            activity.startActivity(
                Intent(Intent.ACTION_VIEW)
                    .setDataAndType(Uri.parse(uri), mime)
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            )
        } catch (_: Exception) {
            Toast.makeText(activity, "No installed app can open this file.", Toast.LENGTH_SHORT).show()
        }
    }

    @JavascriptInterface
    fun share(uri: String, mime: String) = activity.runOnUiThread {
        val send = Intent(Intent.ACTION_SEND)
            .setType(mime)
            .putExtra(Intent.EXTRA_STREAM, Uri.parse(uri))
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        activity.startActivity(Intent.createChooser(send, "Send to"))
    }

    @JavascriptInterface
    fun toast(message: String) = activity.runOnUiThread {
        Toast.makeText(activity, message, Toast.LENGTH_SHORT).show()
    }

    /** Keep downloads running in the background, with progress in the notifications. */
    @JavascriptInterface
    fun watchDownloads() = activity.runOnUiThread { DownloadService.start(activity) }

    @JavascriptInterface
    fun requestNotifications() = activity.runOnUiThread {
        if (Build.VERSION.SDK_INT >= 33 &&
            activity.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
        ) {
            activity.requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), 7)
        }
    }

    /** Close the quick-save sheet (or send the full app to the background). */
    @JavascriptInterface
    fun close() = activity.runOnUiThread {
        if (activity is QuickSaveActivity) activity.finish() else activity.moveTaskToBack(true)
    }

    /** From the quick-save sheet: continue in the full app, with the link already open. */
    @JavascriptInterface
    fun openFull(url: String) = activity.runOnUiThread {
        activity.startActivity(
            Intent(activity, MainActivity::class.java)
                .putExtra(MainActivity.EXTRA_URL, url)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
        )
        if (activity is QuickSaveActivity) activity.finish()
    }
}
