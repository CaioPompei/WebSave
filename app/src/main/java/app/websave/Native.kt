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

    /**
     * Mux H.264 video and AAC audio into one MP4 without re-encoding (replaces ffmpeg).
     * Samples are interleaved by timestamp, the way cameras write files, and the result is
     * checked afterwards: a file the gallery can't read throws, so Python falls back to a single file.
     */
    @JvmStatic
    fun merge(video: String, audio: String, output: String) {
        val muxer = MediaMuxer(output, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)
        class Source(val extractor: MediaExtractor, val track: Int, var done: Boolean = false)
        var maxSample = 1 shl 20
        val sources = listOf(video to "video/", audio to "audio/").map { (path, mimePrefix) ->
            val extractor = MediaExtractor()
            extractor.setDataSource(path)
            val index = (0 until extractor.trackCount).firstOrNull {
                extractor.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith(mimePrefix) == true
            } ?: throw IOException("No $mimePrefix track found")
            extractor.selectTrack(index)
            val format = extractor.getTrackFormat(index)
            if (format.containsKey(MediaFormat.KEY_MAX_INPUT_SIZE)) {
                maxSample = maxOf(maxSample, format.getInteger(MediaFormat.KEY_MAX_INPUT_SIZE))
            }
            if (mimePrefix == "video/" && format.containsKey("rotation-degrees")) {
                muxer.setOrientationHint(format.getInteger("rotation-degrees"))
            }
            Source(extractor, muxer.addTrack(format))
        }
        try {
            muxer.start()
            val buffer = ByteBuffer.allocate(maxOf(maxSample, 4 shl 20))
            val info = MediaCodec.BufferInfo()
            while (true) {
                // always write the sample with the earliest timestamp next
                val next = sources.filter { !it.done }.minByOrNull { it.extractor.sampleTime } ?: break
                val size = next.extractor.readSampleData(buffer, 0)
                if (size < 0) { next.done = true; continue }
                val isKeyFrame = next.extractor.sampleFlags and MediaExtractor.SAMPLE_FLAG_SYNC != 0
                info.set(0, size, next.extractor.sampleTime, if (isKeyFrame) MediaCodec.BUFFER_FLAG_KEY_FRAME else 0)
                muxer.writeSampleData(next.track, buffer, info)
                if (!next.extractor.advance()) next.done = true
            }
            muxer.stop()
        } finally {
            sources.forEach { it.extractor.release() }
            muxer.release()
        }
        val meta = readVideoMeta(output)
        if (meta == null || meta.durationMs <= 0) {
            File(output).delete()
            throw IOException("The merged file isn't playable")
        }
    }

    private class VideoMeta(val durationMs: Long, val width: Int, val height: Int)

    /** What the gallery will read from the file; null when Android can't read it as a video. */
    private fun readVideoMeta(path: String): VideoMeta? {
        val retriever = MediaMetadataRetriever()
        return try {
            retriever.setDataSource(path)
            if (retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_HAS_VIDEO) != "yes") return null
            val duration = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull() ?: 0L
            var w = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH)?.toIntOrNull() ?: 0
            var h = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_HEIGHT)?.toIntOrNull() ?: 0
            val rotation = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_ROTATION)?.toIntOrNull() ?: 0
            if (rotation == 90 || rotation == 270) { val t = w; w = h; h = t }
            VideoMeta(duration, w, h)
        } catch (_: Exception) {
            null
        } finally {
            retriever.release()
        }
    }

    /**
     * Decode evenly spaced frames of a clip, scaled to [maxWidth], and write them as raw RGBA
     * back to back into [output]. Python turns them into a GIF. Returns "width|height|count|delayMs".
     * Uses the hardware decoder first and falls back to MediaMetadataRetriever.
     */
    @JvmStatic
    fun gifFrames(video: String, output: String, maxWidth: Int, fps: Int, maxFrames: Int): String {
        val decoded = try {
            FileOutputStream(output).buffered(1 shl 20).use { decodeFrames(video, it, maxWidth, fps, maxFrames) }
        } catch (_: Exception) {
            null
        }
        if (decoded != null && decoded.count > 0) return decoded.toString()
        val retrieved = FileOutputStream(output).buffered(1 shl 20).use { retrieveFrames(video, it, maxWidth, fps, maxFrames) }
        if (retrieved.count == 0) throw IOException("Couldn't read frames from this clip")
        return retrieved.toString()
    }

    private class Frames(var width: Int = 0, var height: Int = 0, var count: Int = 0, var delayMs: Int = 100) {
        override fun toString() = "$width|$height|$count|$delayMs"
    }

    private fun targetSize(srcWidth: Int, srcHeight: Int, maxWidth: Int): Pair<Int, Int> {
        val scale = min(1.0, maxWidth.toDouble() / srcWidth)
        val w = ((srcWidth * scale).roundToInt() / 2 * 2).coerceAtLeast(2)
        val h = ((srcHeight * scale).roundToInt() / 2 * 2).coerceAtLeast(2)
        return w to h
    }

    /** Sequential decode with MediaCodec: robust for streamed clips (fragmented MP4, MPEG-TS). */
    private fun decodeFrames(video: String, out: java.io.OutputStream, maxWidth: Int, fps: Int, maxFrames: Int): Frames {
        val result = Frames()
        val extractor = MediaExtractor()
        var codec: MediaCodec? = null
        try {
            extractor.setDataSource(video)
            val track = (0 until extractor.trackCount).firstOrNull {
                extractor.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith("video/") == true
            } ?: return result
            extractor.selectTrack(track)
            val format = extractor.getTrackFormat(track)
            val durationUs = if (format.containsKey(MediaFormat.KEY_DURATION)) format.getLong(MediaFormat.KEY_DURATION) else 0L
            val stepUs = maxOf(1_000_000L / fps, if (durationUs > 0) durationUs / maxFrames else 0L)
            result.delayMs = (stepUs / 1000).toInt()
            format.setInteger(MediaFormat.KEY_COLOR_FORMAT, android.media.MediaCodecInfo.CodecCapabilities.COLOR_FormatYUV420Flexible)
            codec = MediaCodec.createDecoderByType(format.getString(MediaFormat.KEY_MIME)!!)
            codec.configure(format, null, null, 0)
            codec.start()

            val info = MediaCodec.BufferInfo()
            var inputDone = false
            var nextUs = -1L
            var firstUs = -1L
            var rgba: ByteArray? = null
            var idleAfterInput = 0
            while (result.count < maxFrames) {
                if (!inputDone) {
                    val inIndex = codec.dequeueInputBuffer(10_000)
                    if (inIndex >= 0) {
                        val size = extractor.readSampleData(codec.getInputBuffer(inIndex)!!, 0)
                        if (size < 0) {
                            codec.queueInputBuffer(inIndex, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM)
                            inputDone = true
                        } else {
                            codec.queueInputBuffer(inIndex, 0, size, extractor.sampleTime, 0)
                            extractor.advance()
                        }
                    }
                }
                val outIndex = codec.dequeueOutputBuffer(info, 10_000)
                if (outIndex < 0) {
                    // a decoder that stops answering after the last input should not hang the app
                    if (inputDone && ++idleAfterInput > 300) break
                    continue
                }
                val eos = info.flags and MediaCodec.BUFFER_FLAG_END_OF_STREAM != 0
                if (info.size > 0) {
                    if (firstUs < 0) { firstUs = info.presentationTimeUs; nextUs = firstUs }
                    if (info.presentationTimeUs >= nextUs) {
                        codec.getOutputImage(outIndex)?.use { image ->
                            val crop = image.cropRect
                            if (result.width == 0) {
                                val (w, h) = targetSize(crop.width(), crop.height(), maxWidth)
                                result.width = w; result.height = h
                                rgba = ByteArray(w * h * 4)
                            }
                            yuvToRgba(image, result.width, result.height, rgba!!)
                            out.write(rgba!!)
                            result.count++
                            nextUs += stepUs
                        }
                    }
                }
                codec.releaseOutputBuffer(outIndex, false)
                if (eos) break
            }
        } finally {
            try { codec?.stop() } catch (_: Exception) {}
            codec?.release()
            extractor.release()
        }
        return result
    }

    /** Convert a YUV_420_888 image to RGBA at the target size (nearest-neighbour scaling, BT.601). */
    private fun yuvToRgba(image: android.media.Image, width: Int, height: Int, dst: ByteArray) {
        val crop = image.cropRect
        val (yPlane, uPlane, vPlane) = image.planes.let { Triple(it[0], it[1], it[2]) }
        val yBuf = yPlane.buffer; val uBuf = uPlane.buffer; val vBuf = vPlane.buffer
        val yRow = yPlane.rowStride; val yPix = yPlane.pixelStride
        val uRow = uPlane.rowStride; val uPix = uPlane.pixelStride
        val vRow = vPlane.rowStride; val vPix = vPlane.pixelStride
        var o = 0
        for (ty in 0 until height) {
            val sy = crop.top + ty * crop.height() / height
            for (tx in 0 until width) {
                val sx = crop.left + tx * crop.width() / width
                val y = (yBuf.get(sy * yRow + sx * yPix).toInt() and 0xFF) - 16
                val u = (uBuf.get((sy / 2) * uRow + (sx / 2) * uPix).toInt() and 0xFF) - 128
                val v = (vBuf.get((sy / 2) * vRow + (sx / 2) * vPix).toInt() and 0xFF) - 128
                val c = 1192 * maxOf(y, 0)
                dst[o++] = ((c + 1634 * v) shr 10).coerceIn(0, 255).toByte()
                dst[o++] = ((c - 833 * v - 400 * u) shr 10).coerceIn(0, 255).toByte()
                dst[o++] = ((c + 2066 * u) shr 10).coerceIn(0, 255).toByte()
                dst[o++] = 0xFF.toByte()
            }
        }
    }

    /** Fallback: ask MediaMetadataRetriever for each frame. */
    private fun retrieveFrames(video: String, out: java.io.OutputStream, maxWidth: Int, fps: Int, maxFrames: Int): Frames {
        val result = Frames()
        val retriever = MediaMetadataRetriever()
        try {
            retriever.setDataSource(video)
            val durationMs = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull() ?: 0L
            val count = ((durationMs * fps) / 1000).toInt().coerceIn(1, maxFrames)
            val stepUs = if (count > 1) durationMs * 1000 / count else 0L
            result.delayMs = if (count > 1) (stepUs / 1000).toInt() else 100
            for (i in 0 until count) {
                val t = i * stepUs
                val frame = retriever.getFrameAtTime(t, MediaMetadataRetriever.OPTION_CLOSEST)
                    ?: retriever.getFrameAtTime(t, MediaMetadataRetriever.OPTION_CLOSEST_SYNC)
                    ?: continue
                if (result.width == 0) {
                    val (w, h) = targetSize(frame.width, frame.height, maxWidth)
                    result.width = w; result.height = h
                }
                val scaled = Bitmap.createScaledBitmap(frame, result.width, result.height, true)
                val argb = if (scaled.config == Bitmap.Config.ARGB_8888) scaled else scaled.copy(Bitmap.Config.ARGB_8888, false)
                val buffer = ByteBuffer.allocate(result.width * result.height * 4)
                argb.copyPixelsToBuffer(buffer)
                out.write(buffer.array())
                result.count++
                if (argb !== scaled) argb.recycle()
                if (scaled !== frame) scaled.recycle()
                frame.recycle()
            }
        } finally {
            retriever.release()
        }
        return result
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
            // galleries hide videos without a duration, so fill it in instead of relying on the scan
            val meta = if (!isAudio && !isGif) readVideoMeta(path) else null
            val resolver = context.contentResolver
            uri = resolver.insert(collection, values) ?: throw IOException("Couldn't create the file in the gallery")
            resolver.openOutputStream(uri)?.use { out -> file.inputStream().use { it.copyTo(out) } }
                ?: throw IOException("Couldn't write the file")
            values.clear()
            values.put(MediaStore.MediaColumns.IS_PENDING, 0)
            resolver.update(uri, values, null, null)
            if (meta != null) {
                // best effort: some Android versions only let the system scanner write these
                try {
                    val extra = ContentValues().apply {
                        put(MediaStore.MediaColumns.DURATION, meta.durationMs)
                        if (meta.width > 0 && meta.height > 0) {
                            put(MediaStore.MediaColumns.WIDTH, meta.width)
                            put(MediaStore.MediaColumns.HEIGHT, meta.height)
                        }
                    }
                    resolver.update(uri, extra, null, null)
                } catch (_: Exception) {}
            }
            // ask the scanner to (re)read the file so the gallery lists it right away
            MediaScannerConnection.scanFile(context, arrayOf(uri.toString()), arrayOf(mime), null)
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
