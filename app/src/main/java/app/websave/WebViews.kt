package app.websave

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.text.Html
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient

/** Shared WebView setup for the full app and the quick-save sheet. */
@SuppressLint("SetJavaScriptEnabled")
fun Activity.setUpWebView(web: WebView, backgroundColor: Int) {
    web.setBackgroundColor(backgroundColor)
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
}

/** A minimal page for "starting" and error states, before the local server answers. */
fun plainScreen(message: String, transparent: Boolean = false): String {
    val background = if (transparent) "transparent" else "#12161F"
    return """
        <!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
        <style>
          html,body{height:100%;margin:0}
          body{display:flex;align-items:center;justify-content:center;background:$background;color:#8F98AB;
               font:500 16px system-ui,sans-serif;padding:24px;text-align:center}
        </style></head><body>${Html.escapeHtml(message)}</body></html>
    """.trimIndent()
}

/** The first http(s) link in a piece of shared text. */
fun firstLink(text: String?): String? = text?.let { Regex("https?://\\S+").find(it)?.value }
