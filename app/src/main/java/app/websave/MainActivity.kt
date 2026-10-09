package app.websave

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.text.Html
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.ComponentActivity
import androidx.activity.OnBackPressedCallback
import androidx.activity.result.contract.ActivityResultContracts
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.ServerSocket
import java.net.URL
import kotlin.concurrent.thread

class MainActivity : ComponentActivity() {

    companion object {
        // the Python server lives as long as the app process does
        @Volatile private var port = 0
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

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Native.context = applicationContext

        web = WebView(this)
        setContentView(web)
        web.setBackgroundColor(getColor(R.color.paper))
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            mediaPlaybackRequiresUserGesture = true
        }
        web.addJavascriptInterface(JsBridge(this), "WebSaveAndroid")
        web.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                if (request.url.host == "127.0.0.1") return false
                try { startActivity(Intent(Intent.ACTION_VIEW, request.url)) } catch (_: Exception) {}
                return true
            }
        }
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
                web.evaluateJavascript(
                    "(function(){var d=document.getElementById('settings');if(d&&d.open){d.close();return true}return false})()"
                ) { closed -> if (closed != "true") moveTaskToBack(true) }
            }
        })

        if (Build.VERSION.SDK_INT < 29 &&
            checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermission.launch(Manifest.permission.WRITE_EXTERNAL_STORAGE)
        }

        pendingLink = linkFrom(intent)
        web.loadDataWithBaseURL(null, plainScreen("Starting WebSave…"), "text/html", "utf-8", null)
        startServer()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        val link = linkFrom(intent) ?: return
        if (ready) web.evaluateJavascript("receiveLink(${JSONObject.quote(link)})", null)
        else pendingLink = link
    }

    private fun startServer() = thread {
        try {
            if (port == 0) {
                if (!Python.isStarted()) Python.start(AndroidPlatform(applicationContext))
                val free = ServerSocket(0).use { it.localPort }
                Python.getInstance().getModule("websave").callAttr(
                    "start", free, filesDir.absolutePath, cacheDir.absolutePath,
                    applicationInfo.nativeLibraryDir
                )
                port = free
            }
            val base = "http://127.0.0.1:$port/"
            val ok = waitFor(base + "api/ping")
            runOnUiThread {
                if (ok) {
                    ready = true
                    val query = pendingLink?.let { "?url=" + Uri.encode(it) } ?: ""
                    pendingLink = null
                    web.loadUrl(base + query)
                } else {
                    web.loadDataWithBaseURL(null, plainScreen("WebSave couldn't start. Close and reopen the app."), "text/html", "utf-8", null)
                }
            }
        } catch (e: Throwable) {
            runOnUiThread {
                web.loadDataWithBaseURL(null, plainScreen("Startup failed: ${e.message}"), "text/html", "utf-8", null)
            }
        }
    }

    private fun waitFor(url: String): Boolean {
        repeat(120) {
            try {
                val connection = URL(url).openConnection() as HttpURLConnection
                connection.connectTimeout = 500
                connection.readTimeout = 1000
                if (connection.responseCode == 200) return true
            } catch (_: Exception) {}
            Thread.sleep(250)
        }
        return false
    }

    private fun linkFrom(intent: Intent?): String? {
        if (intent?.action != Intent.ACTION_SEND) return null
        val text = intent.getStringExtra(Intent.EXTRA_TEXT) ?: return null
        return Regex("https?://\\S+").find(text)?.value
    }

    private fun plainScreen(message: String) = """
        <!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
        <style>
          html,body{height:100%;margin:0}
          body{display:flex;align-items:center;justify-content:center;background:#EDEFF2;color:#5D6571;
               font:500 16px system-ui,sans-serif;padding:24px;text-align:center}
          @media (prefers-color-scheme:dark){body{background:#15181C;color:#9AA3AE}}
        </style></head><body>${Html.escapeHtml(message)}</body></html>
    """.trimIndent()
}
