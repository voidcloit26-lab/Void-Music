package com.mochyy.mochymusic.guardian
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.security.MessageDigest
fun main() {
    val bytes = "test APK content".toByteArray()
    val hash = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it.toInt() and 255) }
    fun run(size: Long, digest: String, cancel: () -> Unit = {}): ByteArray {
        val out = ByteArrayOutputStream()
        VerifiedApkBytes.copy(ByteArrayInputStream(bytes), out, size, digest, cancel)
        return out.toByteArray()
    }
    check(run(bytes.size.toLong(), hash).contentEquals(bytes))
    check(runCatching { run(bytes.size.toLong()-1, hash) }.isFailure)
    check(runCatching { run(bytes.size.toLong()+1, hash) }.isFailure)
    check(runCatching { run(bytes.size.toLong(), "0".repeat(64)) }.isFailure)
    check(runCatching { run(0, hash) }.isFailure)
    check(runCatching { run(bytes.size.toLong(), hash) { error("cancelled") } }.isFailure)
    println("PASS: 6 APK stream verification checks")
}
