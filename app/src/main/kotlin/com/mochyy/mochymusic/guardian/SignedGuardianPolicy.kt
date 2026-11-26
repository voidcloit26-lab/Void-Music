package com.mochyy.mochymusic.guardian

import java.security.AlgorithmParameters
import java.security.PublicKey
import java.security.Signature
import java.security.interfaces.ECPublicKey
import java.security.spec.ECGenParameterSpec
import java.security.spec.ECParameterSpec

/** Strict canonical payloads from Guardian V2. Caller must supply pinned keys
 * and trusted time, and persist the last accepted release sequence. Not a gate. */
internal object SignedGuardianPolicy {
    private const val MaxEpoch = 253402300799L
    private val leasePattern = Regex("""\{"account":"([a-f0-9]{32})","audience":"online\.voidbot\.music","device":"([a-f0-9]{64})","expires_at":([1-9][0-9]{0,11}),"issued_at":([1-9][0-9]{0,11}),"membership_expires_at":(null|[1-9][0-9]{0,11}),"version":2\}""")
    private val releasePattern = Regex("""\{"apk_bytes":([1-9][0-9]{0,9}),"apk_sha256":"([a-f0-9]{64})","channel":"stable","expires_at":([1-9][0-9]{0,11}),"issued_at":([1-9][0-9]{0,11}),"latest":([1-9][0-9]{0,9}),"minimum":([1-9][0-9]{0,9}),"package":"online\.voidbot\.music","sequence":([1-9][0-9]{0,18}),"signer_sha256":"([a-f0-9]{64})","version_name":"([0-9]+\.[0-9]+\.[0-9]+)"\}""")

    data class Lease(val account: String, val device: String, val issuedAt: Long, val expiresAt: Long, val membershipExpiresAt: Long?)
    data class Release(val sequence: Long, val latest: Long, val minimum: Long, val versionName: String,
                       val apkBytes: Long, val apkSha256: String, val signerSha256: String,
                       val issuedAt: Long, val expiresAt: Long) {
        fun decision(installed: Long): String {
            require(installed > 0)
            return when {
                installed < minimum -> "required"
                installed < latest -> "available"
                else -> "current"
            }
        }
    }

    private fun verified(payload: ByteArray, signature: ByteArray, key: PublicKey, maxBytes: Int): String {
        require(payload.size in 1..maxBytes && signature.size in 1..80)
        require(payload.all { it.toInt() in 32..126 })
        require(key is ECPublicKey)
        val expected = AlgorithmParameters.getInstance("EC").apply { init(ECGenParameterSpec("secp256r1")) }
            .getParameterSpec(ECParameterSpec::class.java)
        val actual = key.params
        require(actual.curve == expected.curve && actual.generator == expected.generator &&
            actual.order == expected.order && actual.cofactor == expected.cofactor)
        require(Signature.getInstance("SHA256withECDSA").run {
            initVerify(key)
            update(payload)
            verify(signature)
        })
        return String(payload, Charsets.US_ASCII)
    }

    fun lease(payload: ByteArray, signature: ByteArray, key: PublicKey, account: String,
              device: String, trustedNow: Long, trustedFloor: Long): Lease {
        val m = requireNotNull(leasePattern.matchEntire(verified(payload, signature, key, 2048)))
        val (a, d, expires, issued, membership) = m.destructured
        val i = issued.toLong()
        val e = expires.toLong()
        val end = if (membership == "null") null else membership.toLong()
        require(a == account && d == device)
        require(trustedNow in 1..MaxEpoch && trustedFloor in 1..trustedNow)
        require(i in 1..trustedNow && e in (i + 1)..MaxEpoch && e - i <= 86400L && trustedNow < e)
        require(i >= trustedFloor - 86400L)
        require(end == null || (end in e..MaxEpoch))
        return Lease(a, d, i, e, end)
    }

    fun release(payload: ByteArray, signature: ByteArray, key: PublicKey, trustedNow: Long,
                previous: Release? = null): Release {
        val m = requireNotNull(releasePattern.matchEntire(verified(payload, signature, key, 4096)))
        val g = m.groupValues
        val candidate = Release(g[7].toLong(), g[5].toLong(), g[6].toLong(), g[9],
            g[1].toLong(), g[2], g[8], g[4].toLong(), g[3].toLong())
        require(trustedNow in 1..MaxEpoch)
        require(candidate.minimum in 1..candidate.latest && candidate.latest <= 2100000000L)
        require(candidate.apkBytes in 1..524288000L)
        require(candidate.issuedAt in 1..(trustedNow + 300L) && candidate.expiresAt in (trustedNow + 1)..MaxEpoch)
        require(candidate.expiresAt > candidate.issuedAt && candidate.expiresAt - candidate.issuedAt <= 604800L)
        if (previous != null) {
            require(candidate.sequence >= previous.sequence)
            require(candidate.sequence != previous.sequence || candidate == previous)
        }
        return candidate
    }
}
