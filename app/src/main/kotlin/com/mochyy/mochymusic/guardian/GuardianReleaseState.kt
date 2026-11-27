package com.mochyy.mochymusic.guardian

import android.content.Context
import android.util.AtomicFile
import java.io.File
import java.io.FileNotFoundException
import java.security.PublicKey

/** Persists verified policy sequence and content digest across process restarts.
 * Not an installed-version gate; caller must supply trusted time and a separate release key.
 */
internal class GuardianReleaseState(context: Context, private val key: PublicKey) {
    private val storage = AtomicFile(File(context.applicationContext.noBackupFilesDir, "guardian_release_floor_v2"))

    private fun read(): ReleaseFloor? {
        val raw = try {
            storage.openRead().use { input ->
                require(input.channel.size() in 66L..84L)
                input.readBytes()
            }
        } catch (e: FileNotFoundException) {
            // Missing on first installation is valid, unreadable existing state is not.
            if (storage.baseFile.exists() || File(storage.baseFile.path + ".bak").exists() ||
                File(storage.baseFile.path + ".new").exists()) throw e
            return null
        }
        require(raw.all { it.toInt() in 32..126 })
        return ReleaseFloor.parse(String(raw, Charsets.US_ASCII))
    }

    fun verifyAndRemember(payload: ByteArray, signature: ByteArray, trustedNow: Long): SignedGuardianPolicy.Release =
        synchronized(lock) {
            val candidate = SignedGuardianPolicy.release(payload, signature, key, trustedNow)
            val previous = read()
            val floor = ReleaseFloor.accept(previous, candidate.sequence, payload)
            if (floor != previous) {
                val stream = storage.startWrite()
                try {
                    stream.write(floor.encode().toByteArray(Charsets.US_ASCII))
                    storage.finishWrite(stream)
                } catch (e: Exception) {
                    storage.failWrite(stream)
                    throw e
                }
                check(read() == floor)
            }
            candidate
        }

    private companion object { val lock = Any() }
}
