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

/** Funções do Android que a página chama via window.WebSaveAndroid. */
class Ponte(private val act: Activity) {

    @JavascriptInterface
    fun colar(): String {
        val tarefa = FutureTask {
            val cm = act.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            val clip = cm.primaryClip
            if (clip == null || clip.itemCount == 0) "" else clip.getItemAt(0).coerceToText(act).toString()
        }
        act.runOnUiThread(tarefa)
        return try { tarefa.get(2, TimeUnit.SECONDS) } catch (_: Exception) { "" }
    }

    @JavascriptInterface
    fun abrir(uri: String, mime: String) = act.runOnUiThread {
        try {
            act.startActivity(
                Intent(Intent.ACTION_VIEW)
                    .setDataAndType(Uri.parse(uri), mime)
                    .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            )
        } catch (_: Exception) {
            Toast.makeText(act, "Nenhum app instalado abre esse arquivo.", Toast.LENGTH_SHORT).show()
        }
    }

    @JavascriptInterface
    fun compartilhar(uri: String, mime: String) = act.runOnUiThread {
        val envio = Intent(Intent.ACTION_SEND)
            .setType(mime)
            .putExtra(Intent.EXTRA_STREAM, Uri.parse(uri))
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        act.startActivity(Intent.createChooser(envio, "Enviar para"))
    }
}
