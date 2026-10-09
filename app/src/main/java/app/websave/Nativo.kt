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

/** Funções nativas chamadas pelo Python (websave.py) via Chaquopy. */
object Nativo {

    lateinit var contexto: Context

    private val AUDIO = setOf("m4a", "mp3", "aac", "opus", "ogg", "oga", "wav", "flac", "weba")

    /** Junta o vídeo (H.264) e o áudio (AAC) num MP4, sem recodificar. Substitui o ffmpeg. */
    @JvmStatic
    fun juntar(video: String, audio: String, saida: String) {
        val muxer = MediaMuxer(saida, MediaMuxer.OutputFormat.MUXER_OUTPUT_MPEG_4)
        val fontes = listOf(video to "video/", audio to "audio/").map { (caminho, tipo) ->
            val ex = MediaExtractor()
            ex.setDataSource(caminho)
            val i = (0 until ex.trackCount).firstOrNull {
                ex.getTrackFormat(it).getString(MediaFormat.KEY_MIME)?.startsWith(tipo) == true
            } ?: throw IOException("Faixa $tipo não encontrada")
            ex.selectTrack(i)
            ex to muxer.addTrack(ex.getTrackFormat(i))
        }
        try {
            muxer.start()
            val buffer = ByteBuffer.allocate(8 * 1024 * 1024)
            val info = MediaCodec.BufferInfo()
            for ((ex, faixa) in fontes) {
                while (true) {
                    val tamanho = ex.readSampleData(buffer, 0)
                    if (tamanho < 0) break
                    info.set(
                        0, tamanho, ex.sampleTime,
                        if (ex.sampleFlags and MediaExtractor.SAMPLE_FLAG_SYNC != 0) MediaCodec.BUFFER_FLAG_KEY_FRAME else 0
                    )
                    muxer.writeSampleData(faixa, buffer, info)
                    ex.advance()
                }
            }
            muxer.stop()
        } finally {
            fontes.forEach { it.first.release() }
            muxer.release()
        }
    }

    /** Copia o arquivo para Filmes/WebSave (ou Música/WebSave) e devolve "uri|pasta". */
    @JvmStatic
    fun salvar(caminho: String, nome: String): String {
        val arq = File(caminho)
        val ext = arq.extension.lowercase()
        val ehAudio = ext in AUDIO
        val mime = when (ext) {
            "mp4" -> "video/mp4"
            "webm" -> "video/webm"
            "mkv" -> "video/x-matroska"
            "mov" -> "video/quicktime"
            "m4a" -> "audio/mp4"
            "mp3" -> "audio/mpeg"
            "opus", "ogg", "oga" -> "audio/ogg"
            else -> if (ehAudio) "audio/*" else "video/*"
        }
        val raiz = if (ehAudio) Environment.DIRECTORY_MUSIC else Environment.DIRECTORY_MOVIES
        val pasta = "$raiz/WebSave"

        val uri: Uri
        if (Build.VERSION.SDK_INT >= 29) {
            val colecao = if (ehAudio)
                MediaStore.Audio.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
            else
                MediaStore.Video.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY)
            val valores = ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, nome)
                put(MediaStore.MediaColumns.MIME_TYPE, mime)
                put(MediaStore.MediaColumns.RELATIVE_PATH, pasta)
                put(MediaStore.MediaColumns.IS_PENDING, 1)
            }
            val resolver = contexto.contentResolver
            uri = resolver.insert(colecao, valores) ?: throw IOException("Não foi possível criar o arquivo na galeria")
            resolver.openOutputStream(uri)?.use { saida -> arq.inputStream().use { it.copyTo(saida) } }
                ?: throw IOException("Não foi possível gravar o arquivo")
            valores.clear()
            valores.put(MediaStore.MediaColumns.IS_PENDING, 0)
            resolver.update(uri, valores, null, null)
        } else {
            val dir = File(Environment.getExternalStoragePublicDirectory(raiz), "WebSave").apply { mkdirs() }
            var destino = File(dir, nome)
            var n = 1
            while (destino.exists()) {
                destino = File(dir, "${arq.nameWithoutExtension.ifEmpty { "video" }} ($n).$ext"); n++
            }
            arq.copyTo(destino)
            MediaScannerConnection.scanFile(contexto, arrayOf(destino.absolutePath), arrayOf(mime), null)
            uri = FileProvider.getUriForFile(contexto, "app.websave.arquivos", destino)
        }
        arq.delete()
        return "$uri|$pasta"
    }
}
