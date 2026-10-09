package app.websave

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebView
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import org.json.JSONObject
import kotlin.concurrent.thread

/** The full app: Save, Library and Settings. */
class MainActivity : ComponentActivity() {

    companion object {
        /** Extra with a link to open right away (from the quick-save sheet's "More options"). */
        const val EXTRA_URL = "app.websave.URL"
    }

    private lateinit var web: WebView
    private var fileCallback: ValueCallback<Array<Uri>>? = null
    private var pendingLink: String? = null
    private var ready = false

    private val filePicker = registerForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        fileCallback?.onReceiveValue(uri?.let { arrayOf(it) })
        fileCallback = null
    }
    private val requestPermission = registerForActivityResult(ActivityResultContracts.RequestPermission()) {}

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        web = WebView(this)
        setContentView(web)
        setUpWebView(web, getColor(R.color.background))
        web.webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
                view: WebView, callback: ValueCallback<Array<Uri>>, params: FileChooserParams
            ): Boolean {
                fileCallback?.onReceiveValue(null)
                fileCallback = callback
                return try {
                    filePicker.launch("*/*"); true
                } catch (e: Exception) {
                    fileCallback = null; false
                }
            }
        }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                // the page handles its own back stack (sheet, video screen, tabs); leave the app only at the root
                web.evaluateJavascript("window.handleBack ? handleBack() : false") { handled ->
                    if (handled != "true") moveTaskToBack(true)
                }
            }
        })

        if (Build.VERSION.SDK_INT < 29 &&
            checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermission.launch(Manifest.permission.WRITE_EXTERNAL_STORAGE)
        }

        pendingLink = linkFrom(intent)
        web.loadDataWithBaseURL(null, plainScreen("Starting WebSave…"), "text/html", "utf-8", null)
        thread {
            val ok = try { Server.awaitReady(this) } catch (_: Throwable) { false }
            runOnUiThread {
                if (ok) {
                    ready = true
                    val query = pendingLink?.let { "?url=" + Uri.encode(it) } ?: ""
                    pendingLink = null
                    web.loadUrl(Server.base + query)
                } else {
                    web.loadDataWithBaseURL(null, plainScreen("WebSave couldn't start. Close and reopen the app."),
                        "text/html", "utf-8", null)
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        val link = linkFrom(intent) ?: return
        if (ready) web.evaluateJavascript("receiveLink(${JSONObject.quote(link)})", null)
        else pendingLink = link
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        // Android only lets an app read the clipboard while it has focus
        if (hasFocus && ready) web.evaluateJavascript("window.onAppFocus && onAppFocus()", null)
    }

    private fun linkFrom(intent: Intent?): String? =
        intent?.getStringExtra(EXTRA_URL)?.takeIf { it.isNotBlank() }
            ?: if (intent?.action == Intent.ACTION_SEND) firstLink(intent.getStringExtra(Intent.EXTRA_TEXT)) else null
}
