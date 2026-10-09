package app.websave

import android.content.ContentValues
import android.content.Context
import android.graphics.Bitmap
import android.media.MediaCodec
import android.media.MediaExtractor
import android.media.MediaFormat
import android.media.MediaMetadataRetriever
import android.media.MediaMuxer
import android.media.MediaScannerConnection
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import androidx.core.content.FileProvider
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.nio.ByteBuffer
import kotlin.math.min
import kotlin.math.roundToInt

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

    /**
     * Decode evenly spaced frames of a clip, scaled to [maxWidth], and write them as raw RGBA
     * back to back into [output]. Python turns them into a GIF. Returns "width|height|count|delayMs".
     */
    @JvmStatic
    fun gifFrames(video: String, output: String, maxWidth: Int, fps: Int, maxFrames: Int): String {
        val retriever = MediaMetadataRetriever()
        try {
            retriever.setDataSource(video)
            val durationMs = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull() ?: 0L
            val count = ((durationMs * fps) / 1000).toInt().coerceIn(1, maxFrames)
            val stepUs = if (count > 1) durationMs * 1000 / count else 0L
            var width = 0
            var height = 0
            var written = 0
            FileOutputStream(output).buffered(1 shl 20).use { out ->
                for (i in 0 until count) {
                    val frame = retriever.getFrameAtTime(i * stepUs, MediaMetadataRetriever.OPTION_CLOSEST) ?: continue
                    if (width == 0) {
                        val scale = min(1.0, maxWidth.toDouble() / frame.width)
                        width = (frame.width * scale).roundToInt().coerceAtLeast(2)
                        height = (frame.height * scale).roundToInt().coerceAtLeast(2)
                    }
                    val scaled = if (frame.width == width && frame.height == height) frame
                        else Bitmap.createScaledBitmap(frame, width, height, true)
                    val argb = if (scaled.config == Bitmap.Config.ARGB_8888) scaled
                        else scaled.copy(Bitmap.Config.ARGB_8888, false)
                    val buffer = ByteBuffer.allocate(width * height * 4)
                    argb.copyPixelsToBuffer(buffer)
                    out.write(buffer.array())
                    written++
                    if (argb !== frame) argb.recycle()
                    if (scaled !== frame && scaled !== argb) scaled.recycle()
                    frame.recycle()
                }
            }
            if (written == 0) throw IOException("Couldn't read frames from this clip")
            val delayMs = if (count > 1) (stepUs / 1000).toInt() else 100
            return "$width|$height|$written|$delayMs"
        } finally {
            retriever.release()
        }
    }

    /** Copy the file into the gallery's WebSave album (audio: Music/WebSave) and return "uri|folder". */
    @JvmStatic
    fun save(path: String, name: String): String {
        val file = File(path)
        val ext = file.extension.lowercase()
        val isAudio = ext in AUDIO_EXTENSIONS
        val isGif = ext == "gif"
        val mime = when (ext) {
            "mp4" -> "video/mp4"
            "webm" -> "video/webm"
            "mkv" -> "video/x-matroska"
            "mov" -> "video/quicktime"
            "m4a" -> "audio/mp4"
            "mp3" -> "audio/mpeg"
            "gif" -> "image/gif"
            "opus", "ogg", "oga" -> "audio/ogg"
            else -> if (isAudio) "audio/*" else "video/*"
        }
        // videos and GIFs share one "WebSave" album in the gallery
        val root = if (isAudio) Environment.DIRECTORY_MUSIC else Environment.DIRECTORY_PICTURES
        val folder = "$root/WebSave"

        val uri: Uri
        if (Build.VERSION.SDK_INT >= 29) {
            val volume = MediaStore.VOLUME_EXTERNAL_PRIMARY
            val collection = when {
                isAudio -> MediaStore.Audio.Media.getContentUri(volume)
                isGif -> MediaStore.Images.Media.getContentUri(volume)
                else -> MediaStore.Video.Media.getContentUri(volume)
            }
            val now = System.currentTimeMillis()
            val values = ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, name)
                put(MediaStore.MediaColumns.MIME_TYPE, mime)
                put(MediaStore.MediaColumns.RELATIVE_PATH, folder)
                put(MediaStore.MediaColumns.IS_PENDING, 1)
                // dated "now" so it shows up at the top of the gallery, not on the upload date
                put(MediaStore.MediaColumns.DATE_TAKEN, now)
                put(MediaStore.MediaColumns.DATE_ADDED, now / 1000)
                put(MediaStore.MediaColumns.DATE_MODIFIED, now / 1000)
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
