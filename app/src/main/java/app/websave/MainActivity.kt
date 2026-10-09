package app.websave

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
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
        // o servidor Python vive enquanto o processo do app existir
        @Volatile private var porta = 0
    }

    private lateinit var web: WebView
    private var escolhaArquivo: ValueCallback<Array<Uri>>? = null
    private var linkPendente: String? = null
    private var pronto = false

    private val seletor = registerForActivityResult(ActivityResultContracts.GetContent()) { uri ->
        escolhaArquivo?.onReceiveValue(uri?.let { arrayOf(it) })
        escolhaArquivo = null
    }
    private val pedirPermissao = registerForActivityResult(ActivityResultContracts.RequestPermission()) {}

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        Nativo.contexto = applicationContext

        web = WebView(this)
        setContentView(web)
        web.setBackgroundColor(getColor(R.color.papel))
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            mediaPlaybackRequiresUserGesture = true
        }
        web.addJavascriptInterface(Ponte(this), "WebSaveAndroid")
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
                escolhaArquivo?.onReceiveValue(null)
                escolhaArquivo = callback
                return try {
                    seletor.launch("*/*"); true
                } catch (e: Exception) {
                    escolhaArquivo = null; false
                }
            }
        }

        onBackPressedDispatcher.addCallback(this, object : OnBackPressedCallback(true) {
            override fun handleOnBackPressed() {
                web.evaluateJavascript(
                    "(function(){var d=document.getElementById('ajustes');if(d&&d.open){d.close();return true}return false})()"
                ) { fechou -> if (fechou != "true") moveTaskToBack(true) }
            }
        })

        if (Build.VERSION.SDK_INT < 29 &&
            checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED
        ) {
            pedirPermissao.launch(Manifest.permission.WRITE_EXTERNAL_STORAGE)
        }

        linkPendente = linkDe(intent)
        web.loadDataWithBaseURL(null, telaSimples("Iniciando o WebSave…"), "text/html", "utf-8", null)
        iniciarServidor()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        val link = linkDe(intent) ?: return
        if (pronto) web.evaluateJavascript("receberLink(${JSONObject.quote(link)})", null)
        else linkPendente = link
    }

    private fun iniciarServidor() = thread {
        try {
            if (porta == 0) {
                if (!Python.isStarted()) Python.start(AndroidPlatform(applicationContext))
                val livre = ServerSocket(0).use { it.localPort }
                Python.getInstance().getModule("websave")
                    .callAttr("start", livre, filesDir.absolutePath, cacheDir.absolutePath)
                porta = livre
            }
            val base = "http://127.0.0.1:$porta/"
            val ok = esperar(base + "api/ping")
            runOnUiThread {
                if (ok) {
                    pronto = true
                    val q = linkPendente?.let { "?url=" + Uri.encode(it) } ?: ""
                    linkPendente = null
                    web.loadUrl(base + q)
                } else {
                    web.loadDataWithBaseURL(null, telaSimples("O WebSave não conseguiu iniciar. Feche e abra o app de novo."), "text/html", "utf-8", null)
                }
            }
        } catch (e: Throwable) {
            runOnUiThread {
                web.loadDataWithBaseURL(null, telaSimples("Falha ao iniciar: ${e.message}"), "text/html", "utf-8", null)
            }
        }
    }

    private fun esperar(url: String): Boolean {
        repeat(120) {
            try {
                val c = URL(url).openConnection() as HttpURLConnection
                c.connectTimeout = 500
                c.readTimeout = 1000
                if (c.responseCode == 200) return true
            } catch (_: Exception) {}
            Thread.sleep(250)
        }
        return false
    }

    private fun linkDe(i: Intent?): String? {
        if (i?.action != Intent.ACTION_SEND) return null
        val texto = i.getStringExtra(Intent.EXTRA_TEXT) ?: return null
        return Regex("https?://\\S+").find(texto)?.value
    }

    private fun telaSimples(msg: String) = """
        <!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
        <style>
          html,body{height:100%;margin:0}
          body{display:flex;align-items:center;justify-content:center;background:#EDEFF2;color:#5D6571;
               font:500 16px system-ui,sans-serif;padding:24px;text-align:center}
          @media (prefers-color-scheme:dark){body{background:#15181C;color:#9AA3AE}}
        </style></head><body>${android.text.Html.escapeHtml(msg)}</body></html>
    """.trimIndent()
}
