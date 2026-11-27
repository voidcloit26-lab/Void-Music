package com.mochyy.mochymusic.guardian

import android.os.SystemClock
import android.util.Base64

/** Authenticated policy retrieval for the stable package.
 * A caller must configure a separate pinned release public key and origin.
 * Errors propagate: an outage is never interpreted as a mandatory update. */
internal class GuardianReleasePolicyClient(
    private val account: GuardianAccountClient,
    private val updater: GuardianVerifiedUpdater
) {
    data class Verified(val payload: ByteArray, val signature: ByteArray,
        val serverEpoch: Long, val requestStartMs: Long, val decision: String) {
        fun trustedNow(): Long {
            val elapsed = SystemClock.elapsedRealtime() - requestStartMs
            require(elapsed in 0L..120_000L) { "Release policy check expired; refresh first" }
            return Math.addExact(serverEpoch, (elapsed + 999L) / 1000L)
        }
    }

    private fun decode(text: String, max: Int): ByteArray {
        require(text.length in 1..max && text.matches(Regex("[A-Za-z0-9_-]+")))
        val flags = Base64.URL_SAFE or Base64.NO_PADDING or Base64.NO_WRAP
        return Base64.decode(text, flags).also { require(Base64.encodeToString(it, flags) == text) }
    }

    suspend fun check(): Verified {
        val start = SystemClock.elapsedRealtime()
        val response = account.request("release_policy", emptyMap())
        require(response.keys().asSequence().toSet() == setOf("payload", "signature", "server_time"))
        val time = response.get("server_time")
        require(time is Int || time is Long)
        val epoch = (time as Number).toLong()
        require(epoch in 1..253402300799L)
        val payload = decode(response.getString("payload"), 5500)
        val signature = decode(response.getString("signature"), 110)
        val pending = Verified(payload, signature, epoch, start, "")
        val decision = updater.inspect(payload, signature, pending.trustedNow())
        require(decision in setOf("current", "available", "required"))
        return pending.copy(decision = decision)
    }
}
