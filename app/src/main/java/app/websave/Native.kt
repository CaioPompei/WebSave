package app.websave

import android.content.ContentValues
import android.content.Context
import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import android.media.MediaMuxer
import android.media.MediaScannerConnection
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.core.content.FileProvider
import java.io.File
import java.io.IOException
import java.nio.ByteBuffer

/** Native helpers called from Python (websave.py) through Chaquopy. */
object Native {

    lateinit var context: Context

    private val AUDIO_EXTENSIONS = setOf("m4a", "mp3", "aac", "opus", "ogg", "oga", "wav", "flac", "weba")

    /** Mux H.264 video and AAC audio into one MP4 without re-encoding (replaces ffmpeg). */
    @JvmStatic
    fun merge(video: String, audio: String, output: String) {
        val muxer = MediaMuxer(output, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)
        val sources = listOf(video to "video/", audio to "audio/").map { (path, mimePrefix) ->
            val extractor = MediaExtractor()
            extractor.setDataSource(path)
            val index = (0 until extractor.trackCount).firstOrNull {
                extractor.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith(mimePrefix) == true
            } ?: throw IOException("No $mimePrefix track found")
            extractor.selectTrack(index)
            extractor to muxer.addTrack(extractor.getTrackFormat(index))
        }
        try {
            muxer.start()
            val buffer = ByteBuffer.allocate(8 * 1024 * 1024)
            val info = MediaCodec.BufferInfo()
            for ((extractor, track) in sources) {
                while (true) {
                    val size = extractor.readSampleData(buffer, 0)
                    if (size < 0) break
                    val isKeyFrame = extractor.sampleFlags and MediaExtractor.SAMPLE_FLAG_SYNC != 0
                    info.set(0, size, extractor.sampleTime, if (isKeyFrame) MediaCodec.BUFFER_FLAG_KEY_FRAME else 0)
                    muxer.writeSampleData(track, buffer, info)
                    extractor.advance()
                }
            }
            muxer.stop()
        } finally {
            sources.forEach { it.first.release() }
            muxer.release()
        }
    }

    /** Copy the file to Movies/WebSave (or Music/WebSave) and return "uri|folder". */
    @JvmStatic
    fun save(path: String, name: String): String {
        val file = File(path)
        val ext = file.extension.lowercase()
        val isAudio = ext in AUDIO_EXTENSIONS
        val mime = when (ext) {
            "mp4" -> "video/mp4"
            "webm" -> "video/webm"
            "mkv" -> "video/x-matroska"
            "mov" -> "video/quicktime"
            "m4a" -> "audio/mp4"
            "mp3" -> "audio/mpeg"
            "opus", "ogg", "oga" -> "audio/ogg"
            else -> if (isAudio) "audio/*" else "video/*"
        }
        val root = if (isAudio) Environment.DIRECTORY_MUSIC else Environment.DIRECTORY_MOVIES
        val folder = "$root/WebSave"

        val uri: Uri
        if (Build.VERSION.SDK_INT >= 29) {
            val collection = if (isAudio)
                MediaStore.Audio.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
            else
                MediaStore.Video.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
            val values = ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, name)
                put(MediaStore.MediaColumns.MIME_TYPE, mime)
                put(MediaStore.MediaColumns.RELATIVE_PATH, folder)
                put(MediaStore.MediaColumns.IS_PENDING, 1)
            }
            val resolver = context.contentResolver
            uri = resolver.insert(collection, values) ?: throw IOException("Couldn't create the file in the gallery")
            resolver.openOutputStream(uri)?.use { out -> file.inputStream().use { it.copyTo(out) } }
                ?: throw IOException("Couldn't write the file")
            values.clear()
            values.put(MediaStore.MediaColumns.IS_PENDING, 0)
            resolver.update(uri, values, null, null)
        } else {
            val dir = File(Environment.getExternalStoragePublicDirectory(root), "WebSave").apply { mkdirs() }
            var target = File(dir, name)
            var n = 1
            while (target.exists()) {
                target = File(dir, "${file.nameWithoutExtension.ifEmpty { "video" }} ($n).$ext")
                n++
            }
            file.copyTo(target)
            MediaScannerConnection.scanFile(context, arrayOf(target.absolutePath), arrayOf(mime), null)
            uri = FileProvider.getUriForFile(context, "app.websave.files", target)
        }
        file.delete()
        return "$uri|$folder"
    }
}
