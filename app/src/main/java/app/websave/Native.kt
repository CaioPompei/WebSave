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
     * Keep only [startMs, endMs] of a video or audio file, without re-encoding. Video starts at the
     * keyframe at or before startMs, which is how every lossless cutter works.
     */
    @JvmStatic
    fun trim(input: String, output: String, startMs: Long, endMs: Long) {
        class Source(val extractor: MediaExtractor, val track: Int, var done: Boolean = false)
        val probe = MediaExtractor()
        probe.setDataSource(input)
        val muxer = MediaMuxer(output, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)
        val sources = ArrayList<Source>()
        var maxSample = 1 shl 20
        try {
            for (i in 0 until probe.trackCount) {
                val format = probe.getTrackFormat(i)
                val mime = format.getString(MediaFormat.KEY_MIME) ?: continue
                if (!mime.startsWith("video/") && !mime.startsWith("audio/")) continue
                val extractor = MediaExtractor()
                extractor.setDataSource(input)
                extractor.selectTrack(i)
                if (format.containsKey(MediaFormat.KEY_MAX_INPUT_SIZE)) {
                    maxSample = maxOf(maxSample, format.getInteger(MediaFormat.KEY_MAX_INPUT_SIZE))
                }
                if (mime.startsWith("video/") && format.containsKey("rotation-degrees")) {
                    muxer.setOrientationHint(format.getInteger("rotation-degrees"))
                }
                sources += Source(extractor, muxer.addTrack(format))
            }
        } finally {
            probe.release()
        }
        if (sources.isEmpty()) {
            muxer.release()
            throw IOException("Nothing to trim in this file")
        }
        val startUs = startMs * 1000
        val endUs = endMs * 1000
        sources.forEach { it.extractor.seekTo(startUs, MediaExtractor.SEEK_TO_PREVIOUS_SYNC) }
        val baseUs = sources.map { it.extractor.sampleTime }.filter { it >= 0 }.minOrNull() ?: 0L
        try {
            muxer.start()
            val buffer = ByteBuffer.allocate(maxOf(maxSample, 4 shl 20))
            val info = MediaCodec.BufferInfo()
            while (true) {
                val next = sources.filter { !it.done }.minByOrNull { it.extractor.sampleTime } ?: break
                val time = next.extractor.sampleTime
                if (time < 0 || time > endUs) { next.done = true; continue }
                val size = next.extractor.readSampleData(buffer, 0)
                if (size < 0) { next.done = true; continue }
                val isKeyFrame = next.extractor.sampleFlags and MediaExtractor.SAMPLE_FLAG_SYNC != 0
                info.set(0, size, maxOf(0L, time - baseUs), if (isKeyFrame) MediaCodec.BUFFER_FLAG_KEY_FRAME else 0)
                muxer.writeSampleData(next.track, buffer, info)
                if (!next.extractor.advance()) next.done = true
            }
            muxer.stop()
        } finally {
            sources.forEach { it.extractor.release() }
            muxer.release()
        }
        val retriever = MediaMetadataRetriever()
        val playable = try {
            retriever.setDataSource(output)
            (retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull() ?: 0L) > 0
        } catch (_: Exception) {
            false
        } finally {
            retriever.release()
        }
        if (!playable) {
            File(output).delete()
            throw IOException("The trimmed file isn't playable")
        }
    }

    /**
     * Pull the sound out of a video without re-encoding. AAC goes into an .m4a, Opus/Vorbis into
     * a .webm. Returns the file written ([outputBase] plus its extension); throws "NO_AUDIO" when
     * the video has no sound at all.
     */
    @JvmStatic
    fun extractAudio(input: String, outputBase: String): String {
        val extractor = MediaExtractor()
        try {
            extractor.setDataSource(input)
            val index = (0 until extractor.trackCount).firstOrNull {
                extractor.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith("audio/") == true
            } ?: throw IOException("NO_AUDIO")
            extractor.selectTrack(index)
            val format = extractor.getTrackFormat(index)
            val mime = format.getString(MediaFormat.KEY_MIME) ?: ""
            val (container, ext) = when (mime) {
                "audio/opus", "audio/vorbis" -> MediaMuxer.OutputFormat.MUXER_OUTPUT_WEBM to ".webm"
                else -> MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4 to ".m4a"
            }
            val output = outputBase + ext
            val muxer = MediaMuxer(output, container)
            try {
                val track = muxer.addTrack(format)
                muxer.start()
                val size = if (format.containsKey(MediaFormat.KEY_MAX_INPUT_SIZE)) format.getInteger(MediaFormat.KEY_MAX_INPUT_SIZE) else 0
                val buffer = ByteBuffer.allocate(maxOf(size, 1 shl 20))
                val info = MediaCodec.BufferInfo()
                var first = -1L
                while (true) {
                    val read = extractor.readSampleData(buffer, 0)
                    if (read < 0) break
                    if (first < 0) first = extractor.sampleTime
                    info.set(0, read, maxOf(0L, extractor.sampleTime - first), MediaCodec.BUFFER_FLAG_KEY_FRAME)
                    muxer.writeSampleData(track, buffer, info)
                    if (!extractor.advance()) break
                }
                muxer.stop()
            } finally {
                muxer.release()
            }
            return output
        } finally {
            extractor.release()
        }
    }

    /** True on Wi-Fi, Ethernet or any network the user marked as unmetered. */
    @JvmStatic
    fun isOnWifi(): Boolean {
        val manager = context.getSystemService(android.net.ConnectivityManager::class.java) ?: return false
        val caps = manager.getNetworkCapabilities(manager.activeNetwork) ?: return false
        return caps.hasTransport(android.net.NetworkCapabilities.TRANSPORT_WIFI) ||
            caps.hasTransport(android.net.NetworkCapabilities.TRANSPORT_ETHERNET) ||
            caps.hasCapability(android.net.NetworkCapabilities.NET_CAPABILITY_NOT_METERED)
    }

    /**
     * Decode evenly spaced frames of a clip, scaled to [maxWidth], and write them as raw RGBA
     * back to back into [output]. Python turns them into a GIF. Returns "width|height|count|delayMs".
     * Only frames between [startMs] and [endMs] are used (endMs < 0 means "to the end").
     * Uses the hardware decoder first and falls back to MediaMetadataRetriever.
     */
    @JvmStatic
    fun gifFrames(video: String, output: String, maxWidth: Int, fps: Int, maxFrames: Int, startMs: Long, endMs: Long): String {
        val decoded = try {
            FileOutputStream(output).buffered(1 shl 20).use { decodeFrames(video, it, maxWidth, fps, maxFrames, startMs, endMs) }
        } catch (_: Exception) {
            null
        }
        if (decoded != null && decoded.count > 0) return decoded.toString()
        val retrieved = FileOutputStream(output).buffered(1 shl 20).use {
            retrieveFrames(video, it, maxWidth, fps, maxFrames, startMs, endMs)
        }
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
    private fun decodeFrames(
        video: String, out: java.io.OutputStream, maxWidth: Int, fps: Int, maxFrames: Int, startMs: Long, endMs: Long
    ): Frames {
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
            val fullUs = if (format.containsKey(MediaFormat.KEY_DURATION)) format.getLong(MediaFormat.KEY_DURATION) else 0L
            val startUs = maxOf(0L, startMs * 1000)
            val endUs = if (endMs > 0) endMs * 1000 else Long.MAX_VALUE
            val durationUs = if (endMs > 0) endUs - startUs else maxOf(0L, fullUs - startUs)
            val stepUs = maxOf(1_000_000L / fps, if (durationUs > 0) durationUs / maxFrames else 0L)
            if (startUs > 0) extractor.seekTo(startUs, MediaExtractor.SEEK_TO_PREVIOUS_SYNC)
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
                if (info.size > 0 && info.presentationTimeUs > endUs) {
                    codec.releaseOutputBuffer(outIndex, false)
                    break
                }
                if (info.size > 0 && info.presentationTimeUs >= startUs) {
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
    private fun retrieveFrames(
        video: String, out: java.io.OutputStream, maxWidth: Int, fps: Int, maxFrames: Int, startMs: Long, endMs: Long
    ): Frames {
        val result = Frames()
        val retriever = MediaMetadataRetriever()
        try {
            retriever.setDataSource(video)
            val fullMs = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull() ?: 0L
            val fromMs = maxOf(0L, startMs)
            val durationMs = (if (endMs > 0) minOf(endMs, fullMs) else fullMs) - fromMs
            val count = ((durationMs * fps) / 1000).toInt().coerceIn(1, maxFrames)
            val stepUs = if (count > 1) durationMs * 1000 / count else 0L
            result.delayMs = if (count > 1) (stepUs / 1000).toInt() else 100
            for (i in 0 until count) {
                val t = fromMs * 1000 + i * stepUs
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

    // ------------------------------------------------------------ local tools (websave_tools.py)

    /** "durationMs|width|height|bitrate|hasAudio" of a video, with width/height as displayed (rotation applied). */
    @JvmStatic
    fun probe(path: String): String {
        val retriever = MediaMetadataRetriever()
        try {
            retriever.setDataSource(path)
            val duration = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull() ?: 0L
            var w = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_WIDTH)?.toIntOrNull() ?: 0
            var h = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_HEIGHT)?.toIntOrNull() ?: 0
            val rotation = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_VIDEO_ROTATION)?.toIntOrNull() ?: 0
            if (rotation == 90 || rotation == 270) { val t = w; w = h; h = t }
            var bitrate = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_BITRATE)?.toLongOrNull() ?: 0L
            if (bitrate <= 0 && duration > 0) bitrate = File(path).length() * 8000 / duration
            val audio = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_HAS_AUDIO) == "yes"
            return "$duration|$w|$h|$bitrate|${if (audio) 1 else 0}"
        } catch (_: Exception) {
            return "0|0|0|0|0"
        } finally {
            retriever.release()
        }
    }

    /** Decode a photo Python's imaging library can't read (HEIC, AVIF) and write it as a JPEG. */
    @JvmStatic
    fun decodeImage(input: String, output: String): Boolean {
        return try {
            val bitmap = if (Build.VERSION.SDK_INT >= 28) {
                android.graphics.ImageDecoder.decodeBitmap(android.graphics.ImageDecoder.createSource(File(input))) { decoder, _, _ ->
                    decoder.allocator = android.graphics.ImageDecoder.ALLOCATOR_SOFTWARE
                }
            } else {
                android.graphics.BitmapFactory.decodeFile(input)
            } ?: return false
            FileOutputStream(output).use { bitmap.compress(Bitmap.CompressFormat.JPEG, 95, it) }
            bitmap.recycle()
            true
        } catch (_: Throwable) {
            false
        }
    }

    /** A JPEG preview frame of a video, at most [maxWidth] wide. */
    @JvmStatic
    fun videoThumb(input: String, output: String, maxWidth: Int): Boolean {
        val retriever = MediaMetadataRetriever()
        return try {
            retriever.setDataSource(input)
            val frame = retriever.getFrameAtTime(1_000_000, MediaMetadataRetriever.OPTION_CLOSEST_SYNC)
                ?: retriever.getFrameAtTime(0) ?: return false
            val scale = min(1.0, maxWidth.toDouble() / frame.width)
            val scaled = if (scale < 1) Bitmap.createScaledBitmap(frame, (frame.width * scale).roundToInt(), (frame.height * scale).roundToInt(), true) else frame
            FileOutputStream(output).use { scaled.compress(Bitmap.CompressFormat.JPEG, 82, it) }
            if (scaled !== frame) scaled.recycle()
            frame.recycle()
            true
        } catch (_: Exception) {
            false
        } finally {
            retriever.release()
        }
    }

    /** Draw one page of a PDF as a JPEG, [width] pixels wide. */
    @JvmStatic
    fun pdfRender(input: String, page: Int, width: Int, output: String): Boolean {
        var fd: android.os.ParcelFileDescriptor? = null
        var renderer: android.graphics.pdf.PdfRenderer? = null
        var current: android.graphics.pdf.PdfRenderer.Page? = null
        return try {
            fd = android.os.ParcelFileDescriptor.open(File(input), android.os.ParcelFileDescriptor.MODE_READ_ONLY)
            renderer = android.graphics.pdf.PdfRenderer(fd!!)
            if (page < 0 || page >= renderer.pageCount) return false
            current = renderer.openPage(page)
            val height = (width.toDouble() * current.height / current.width).roundToInt().coerceAtLeast(1)
            val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
            bitmap.eraseColor(android.graphics.Color.WHITE)
            current.render(bitmap, null, null, android.graphics.pdf.PdfRenderer.Page.RENDER_MODE_FOR_DISPLAY)
            FileOutputStream(output).use { bitmap.compress(Bitmap.CompressFormat.JPEG, 85, it) }
            bitmap.recycle()
            true
        } catch (_: Throwable) {
            false
        } finally {
            try { current?.close() } catch (_: Throwable) {}
            try { renderer?.close() } catch (_: Throwable) {}
            try { fd?.close() } catch (_: Throwable) {}
        }
    }

    @Volatile private var transformer: androidx.media3.transformer.Transformer? = null
    @Volatile private var exportLatch: java.util.concurrent.CountDownLatch? = null
    @Volatile private var exportProgress = 0
    private val exportError = java.util.concurrent.atomic.AtomicReference<Throwable?>(null)

    /**
     * Re-encode a video to H.264/AAC at [height] pixels tall (as displayed) and [videoBitrate].
     * Uses the phone's hardware encoder through Media3 Transformer. Blocks until done; throws on
     * failure or cancel. [startMs]/[endMs] (endMs < 0: to the end) keep only part of the video.
     */
    @JvmStatic
    fun transcode(input: String, output: String, height: Int, videoBitrate: Int, removeAudio: Boolean, startMs: Long, endMs: Long) {
        val latch = java.util.concurrent.CountDownLatch(1)
        exportLatch = latch
        exportError.set(null)
        exportProgress = 0
        val main = android.os.Handler(android.os.Looper.getMainLooper())
        main.post {
            try {
                val item = androidx.media3.common.MediaItem.Builder().setUri(Uri.fromFile(File(input)))
                if (startMs > 0 || endMs > 0) {
                    val clip = androidx.media3.common.MediaItem.ClippingConfiguration.Builder().setStartPositionMs(maxOf(0L, startMs))
                    if (endMs > 0) clip.setEndPositionMs(endMs)
                    item.setClippingConfiguration(clip.build())
                }
                val edited = androidx.media3.transformer.EditedMediaItem.Builder(item.build())
                    .setRemoveAudio(removeAudio)
                    .setEffects(androidx.media3.transformer.Effects(
                        listOf(), listOf(androidx.media3.effect.Presentation.createForHeight(height))))
                    .build()
                val encoders = androidx.media3.transformer.DefaultEncoderFactory.Builder(context)
                    .setRequestedVideoEncoderSettings(
                        androidx.media3.transformer.VideoEncoderSettings.Builder().setBitrate(videoBitrate).build())
                    .setEnableFallback(true)
                    .build()
                val t = androidx.media3.transformer.Transformer.Builder(context)
                    .setVideoMimeType(androidx.media3.common.MimeTypes.VIDEO_H264)
                    .setAudioMimeType(androidx.media3.common.MimeTypes.AUDIO_AAC)
                    .setEncoderFactory(encoders)
                    .addListener(object : androidx.media3.transformer.Transformer.Listener {
                        override fun onCompleted(
                            composition: androidx.media3.transformer.Composition,
                            exportResult: androidx.media3.transformer.ExportResult
                        ) {
                            transformer = null
                            latch.countDown()
                        }

                        override fun onError(
                            composition: androidx.media3.transformer.Composition,
                            exportResult: androidx.media3.transformer.ExportResult,
                            exportException: androidx.media3.transformer.ExportException
                        ) {
                            exportError.set(exportException)
                            transformer = null
                            latch.countDown()
                        }
                    })
                    .build()
                transformer = t
                t.start(edited, output)
                val holder = androidx.media3.transformer.ProgressHolder()
                main.postDelayed(object : Runnable {
                    override fun run() {
                        val current = transformer ?: return
                        if (current.getProgress(holder) == androidx.media3.transformer.Transformer.PROGRESS_STATE_AVAILABLE) {
                            exportProgress = holder.progress
                        }
                        main.postDelayed(this, 500)
                    }
                }, 500)
            } catch (e: Throwable) {
                exportError.set(e)
                latch.countDown()
            }
        }
        latch.await()
        exportLatch = null
        exportError.get()?.let {
            File(output).delete()
            throw IOException(it.message ?: "Couldn't compress this video")
        }
        if (!File(output).exists() || File(output).length() == 0L) throw IOException("Couldn't compress this video")
    }

    /** 0 to 100 while [transcode] runs. */
    @JvmStatic
    fun transcodeProgress(): Int = exportProgress

    @JvmStatic
    fun cancelTranscode() {
        android.os.Handler(android.os.Looper.getMainLooper()).post {
            transformer?.cancel()
            transformer = null
            exportError.set(IOException("Cancelled"))
            exportLatch?.countDown()
        }
    }

    /** Copy the file into the gallery's WebSave album (audio: Music/WebSave) and return "uri|folder". */
    @JvmStatic
    fun save(path: String, name: String): String {
        val file = File(path)
        val ext = file.extension.lowercase()
        val isAudio = ext in AUDIO_EXTENSIONS
        val isImage = ext in setOf("gif", "jpg", "jpeg", "png", "webp")
        val isDocument = ext == "pdf"
        val mime = when (ext) {
            "mp4" -> "video/mp4"
            "webm" -> "video/webm"
            "mkv" -> "video/x-matroska"
            "mov" -> "video/quicktime"
            "m4a" -> "audio/mp4"
            "mp3" -> "audio/mpeg"
            "gif" -> "image/gif"
            "jpg", "jpeg" -> "image/jpeg"
            "png" -> "image/png"
            "webp" -> "image/webp"
            "pdf" -> "application/pdf"
            "opus", "ogg", "oga" -> "audio/ogg"
            else -> if (isAudio) "audio/*" else "video/*"
        }
        // videos, GIFs and covers share one "WebSave" album in the gallery
        val root = when {
            isAudio -> Environment.DIRECTORY_MUSIC
            isDocument -> Environment.DIRECTORY_DOWNLOADS
            else -> Environment.DIRECTORY_PICTURES
        }
        val folder = "$root/WebSave"

        val uri: Uri
        if (Build.VERSION.SDK_INT >= 29) {
            val volume = MediaStore.VOLUME_EXTERNAL_PRIMARY
            val collection = when {
                isDocument -> MediaStore.Downloads.getContentUri(volume)
                isAudio -> MediaStore.Audio.Media.getContentUri(volume)
                isImage -> MediaStore.Images.Media.getContentUri(volume)
                else -> MediaStore.Video.Media.getContentUri(volume)
            }
            val now = System.currentTimeMillis()
            val values = ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, name)
                put(MediaStore.MediaColumns.MIME_TYPE, mime)
                put(MediaStore.MediaColumns.RELATIVE_PATH, folder)
                put(MediaStore.MediaColumns.IS_PENDING, 1)
                // dated "now" so it shows up at the top of the gallery, not on the upload date
                if (!isDocument) put(MediaStore.MediaColumns.DATE_TAKEN, now)
                put(MediaStore.MediaColumns.DATE_ADDED, now / 1000)
                put(MediaStore.MediaColumns.DATE_MODIFIED, now / 1000)
            }
            // galleries hide videos without a duration, so fill it in instead of relying on the scan
            val meta = if (!isAudio && !isImage && !isDocument) readVideoMeta(path) else null
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
            if (!isDocument) MediaScannerConnection.scanFile(context, arrayOf(uri.toString()), arrayOf(mime), null)
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
