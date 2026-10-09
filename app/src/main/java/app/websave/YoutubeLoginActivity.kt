package app.websave

import android.annotation.SuppressLint
import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.view.Gravity
import android.view.ViewGroup.LayoutParams.MATCH_PARENT
import android.view.ViewGroup.LayoutParams.WRAP_CONTENT
import android.webkit.CookieManager
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity

/** Sign in to YouTube inside WebSave; the session is then used for downloads that need an account. */
class YoutubeLoginActivity : ComponentActivity() {

    private lateinit var web: WebView
    private var finished = false

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val density = resources.displayMetrics.density
        fun dp(v: Int) = (v * density).toInt()

        val title = TextView(this).apply {
            text = "Sign in to YouTube"
            setTextColor(Color.parseColor("#EEF1F6"))
            textSize = 17f
            typeface = Typeface.DEFAULT_BOLD
        }
        val done = Button(this).apply {
            text = "Done"
            setOnClickListener { finishSignIn(userAsked = true) }
        }
        val bar = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(Color.parseColor("#1B2130"))
            setPadding(dp(16), dp(8), dp(8), dp(8))
            addView(title, LinearLayout.LayoutParams(0, WRAP_CONTENT, 1f))
            addView(done, LinearLayout.LayoutParams(WRAP_CONTENT, WRAP_CONTENT))
        }

        web = WebView(this)
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            // the plain mobile-browser identity; Google refuses some sign-ins from "embedded" browsers
            userAgentString = userAgentString.replace("; wv", "")
        }
        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, true)
        web.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView, url: String) {
                // back on YouTube with a session: we're done
                if (url.contains("youtube.com") && YoutubeAccount.isSignedIn()) finishSignIn(userAsked = false)
            }
        }

        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#12161F"))
            addView(bar, LinearLayout.LayoutParams(MATCH_PARENT, WRAP_CONTENT))
            addView(web, LinearLayout.LayoutParams(MATCH_PARENT, 0, 1f))
        })
        web.loadUrl("https://accounts.google.com/ServiceLogin?service=youtube&continue=https%3A%2F%2Fwww.youtube.com%2F")
    }

    private fun finishSignIn(userAsked: Boolean) {
        if (finished) return
        CookieManager.getInstance().flush()
        if (YoutubeAccount.isSignedIn()) {
            finished = true
            Toast.makeText(this, "Signed in to YouTube", Toast.LENGTH_SHORT).show()
            finish()
        } else if (userAsked) {
            finished = true
            finish()
        }
    }

    override fun onDestroy() {
        web.destroy()
        super.onDestroy()
    }
}
