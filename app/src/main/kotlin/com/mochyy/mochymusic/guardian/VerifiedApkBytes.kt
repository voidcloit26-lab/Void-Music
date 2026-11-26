package com.mochyy.mochymusic.guardian

import java.io.InputStream
import java.io.OutputStream
import java.security.MessageDigest

/** Exact length and digest checks for the signed release's APK bytes. */
internal object VerifiedApkBytes {
    fun copy(input: InputStream, output: OutputStream, size: Long, sha256: String,
             checkCancelled: () -> Unit = {}) {
        require(size in 1..524288000L && Regex("[a-f0-9]{64}").matches(sha256))
        val digest = MessageDigest.getInstance("SHA-256")
        val buffer = ByteArray(65536)
        var count = 0L
        while (true) {
            checkCancelled()
            val n = input.read(buffer)
            if (n < 0) break
            require(n > 0 && n.toLong() <= size - count) { "Unexpected APK length" }
            digest.update(buffer, 0, n)
            output.write(buffer, 0, n)
            count += n
        }
        require(count == size) { "Truncated APK" }
        val actual = digest.digest().joinToString("") { "%02x".format(it.toInt() and 255) }
        require(MessageDigest.isEqual(actual.toByteArray(Charsets.US_ASCII), sha256.toByteArray(Charsets.US_ASCII))) {
            "APK digest mismatch"
        }
    }
}
