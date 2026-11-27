package com.mochyy.mochymusic.guardian

import java.security.MessageDigest

/** Persistent sequence floor for previously verified signed release policies.
 * Higher signed sequences may deliberately lower the minimum version during an emergency.
 */
internal data class ReleaseFloor(val sequence: Long, val digest: String) {
    init {
        require(sequence > 0L && digest.matches(Regex("[a-f0-9]{64}")))
    }

    fun encode(): String = "$sequence:$digest"

    companion object {
        fun parse(value: String): ReleaseFloor {
            val parts = value.split(':')
            require(parts.size == 2 && parts[0].matches(Regex("[1-9][0-9]{0,18}")))
            return ReleaseFloor(parts[0].toLong(), parts[1]).also { require(it.encode() == value) }
        }

        /** Call only after validating signature, target, freshness and canonical payload. */
        fun accept(previous: ReleaseFloor?, sequence: Long, payload: ByteArray): ReleaseFloor {
            require(payload.size in 1..4096)
            val digest = MessageDigest.getInstance("SHA-256").digest(payload)
                .joinToString("") { "%02x".format(it.toInt() and 255) }
            val next = ReleaseFloor(sequence, digest)
            require(previous == null || next.sequence > previous.sequence || next == previous) {
                "Stale or conflicting release policy"
            }
            return next
        }
    }
}
