package app.websave

import android.content.Context
import android.net.Uri
import android.provider.OpenableColumns
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID

/**
 * Copies files the user picked (or shared to WebSave) into the app's cache, where the tools in
 * websave_tools.py can work on them. The originals are never changed.
 */
object Staging {

    /** Files shared from another app, waiting for the quick sheet to ask for them (JSON). */
    @Volatile var shared: String? = null

    private fun root(context: Context) = File(context.cacheDir, "websave-stage")

    /** Copy each document and return a JSON array of {path, name, mime}. */
    fun stage(context: Context, uris: List<Uri>): String {
        val out = JSONArray()
        val resolver = context.contentResolver
        for (uri in uris) {
            try {
                var name: String? = null
                resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
                    if (c.moveToFirst()) name = c.getString(0)
                }
                val mime = resolver.getType(uri) ?: ""
                val safe = (name ?: uri.lastPathSegment ?: "file")
                    .substringAfterLast('/')
                    .replace(Regex("[\\\\/:*?\"<>|\\x00-\\x1f]"), "_")
                    .take(120)
                    .ifBlank { "file" }
                val folder = File(root(context), UUID.randomUUID().toString().take(12)).apply { mkdirs() }
                val target = File(folder, withExtension(safe, mime))
                resolver.openInputStream(uri)?.use { input ->
                    target.outputStream().use { input.copyTo(it, 1 shl 16) }
                } ?: continue
                out.put(JSONObject().put("path", target.absolutePath).put("name", target.name).put("mime", mime))
            } catch (_: Exception) {
                // skip files that can't be read (cloud files offline, revoked permission...)
            }
        }
        return out.toString()
    }

    /** Some apps share names without an extension; add one from the type so the tools recognize it. */
    private fun withExtension(name: String, mime: String): String {
        if (name.contains('.')) return name
        val ext = android.webkit.MimeTypeMap.getSingleton().getExtensionFromMimeType(mime) ?: return name
        return "$name.$ext"
    }
}
