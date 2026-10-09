package app.websave

import android.webkit.CookieManager
import java.io.File

/**
 * The YouTube session from the in-app sign-in (YoutubeLoginActivity). Cookies live in the app's
 * own WebView cookie jar and are written as a fresh cookies.txt for yt-dlp whenever it needs them,
 * so they never go stale the way an exported file does.
 */
object YoutubeAccount {

    private const val URL = "https://www.youtube.com"
    private const val SIX_MONTHS_S = 180L * 24 * 3600

    private fun raw(): String? = try { CookieManager.getInstance().getCookie(URL) } catch (_: Exception) { null }

    @JvmStatic
    fun isSignedIn(): Boolean {
        val cookies = raw() ?: return false
        return cookies.contains("LOGIN_INFO=") || cookies.contains("SAPISID=")
    }

    /** Write the session in the Netscape format yt-dlp reads. Returns false when not signed in. */
    @JvmStatic
    fun exportCookies(path: String): Boolean {
        val cookies = raw() ?: return false
        if (!isSignedIn()) return false
        val expires = System.currentTimeMillis() / 1000 + SIX_MONTHS_S
        val lines = cookies.split(";").mapNotNull { part ->
            val pair = part.trim()
            val eq = pair.indexOf('=')
            if (eq <= 0) null else ".youtube.com\tTRUE\t/\tTRUE\t$expires\t${pair.substring(0, eq)}\t${pair.substring(eq + 1)}"
        }
        File(path).writeText("# Netscape HTTP Cookie File\n" + lines.joinToString("\n") + "\n")
        return true
    }

    /** Forget the session; [then] runs once the cookies are really gone. */
    @JvmStatic
    @JvmOverloads
    fun signOut(then: (() -> Unit)? = null) {
        val manager = CookieManager.getInstance()
        manager.removeAllCookies {
            manager.flush()
            then?.invoke()
        }
    }
}
