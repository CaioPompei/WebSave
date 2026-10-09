package app.websave

import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.webkit.WebView
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import kotlin.concurrent.thread

/**
 * A small sheet over the current app. Opens when a link is shared to WebSave, or from the
 * Quick Settings tile / icon shortcut (then it uses the copied link). The download keeps
 * going in [DownloadService] with progress in the notifications.
 */
class QuickSaveActivity : ComponentActivity() {

    companion object {
        const val ACTION_CLIPBOARD = "app.websave.SAVE_CLIPBOARD"
    }

    private lateinit var web: WebView
    private var ready = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        web = WebView(this)
        setContentView(web)
        setUpWebView(web, Color.TRANSPARENT)
        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() = finish()
        })
        load(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        load(intent)
    }

    private fun load(intent: Intent?) {
        val link = if (intent?.action == Intent.ACTION_SEND) firstLink(intent.getStringExtra(Intent.EXTRA_TEXT)) else null
        if (intent?.action == Intent.ACTION_SEND && link == null) {
            finish()
            return
        }
        ready = false
        web.loadDataWithBaseURL(null, plainScreen("", transparent = true), "text/html", "utf-8", null)
        thread {
            val ok = try { Server.awaitReady(this) } catch (_: Throwable) { false }
            runOnUiThread {
                if (isFinishing) return@runOnUiThread
                if (!ok) {
                    web.loadDataWithBaseURL(null, plainScreen("WebSave couldn't start. Try again."), "text/html", "utf-8", null)
                    return@runOnUiThread
                }
                ready = true
                val query = "?mode=quick" + (link?.let { "&url=" + Uri.encode(it) } ?: "")
                web.loadUrl(Server.base + query)
            }
        }
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        // the clipboard can only be read once this window has focus
        if (hasFocus && ready) web.evaluateJavascript("window.onAppFocus && onAppFocus()", null)
    }

    override fun finish() {
        super.finish()
        @Suppress("DEPRECATION")
        overridePendingTransition(0, android.R.anim.fade_out)
    }
}
