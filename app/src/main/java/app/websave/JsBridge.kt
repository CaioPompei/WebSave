package app.websave

import android.app.Activity
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
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
}
