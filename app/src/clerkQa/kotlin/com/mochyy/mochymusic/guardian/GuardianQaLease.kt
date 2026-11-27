package com.mochyy.mochymusic.guardian

import android.content.Context
import android.util.Base64
import java.security.KeyFactory
import java.security.spec.X509EncodedKeySpec
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import org.json.JSONObject

/** Test-only cache exercise. Never consulted by the playback gate. */
internal class GuardianQaLease(
    context: Context,
    private val client: GuardianAccountClient,
    private val isCurrent: () -> Boolean
) {
    private val flags = Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING
    private val key = KeyFactory.getInstance("EC").generatePublic(X509EncodedKeySpec(
        decode("MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEQd2EkFTXZBKBZW0S2HRm2kVFUFUjS9KmxUHDa1c8RktpEJ-gcHU33Z5UmiXk5p2pVi-R1tZI4NpuEGBOV3z8Cw", 256)
    ))
    private val cache = GuardianLeaseCache(context, key)
    @Volatile private var closed = false

    private fun decode(value: String, limit: Int): ByteArray {
        require(value.length in 1..limit && value.matches(Regex("[A-Za-z0-9_-]+")))
        return Base64.decode(value, flags).also {
            require(Base64.encodeToString(it, flags) == value)
        }
    }

    suspend fun refresh(account: String): Boolean = withContext(Dispatchers.IO) {
        require(account.matches(Regex("[a-f0-9]{32}")))
        check(!closed && isCurrent())
        cache.clear()
        val anchor = cache.anchor()
        val response = client.request("lease", emptyMap())
        check(response.keys().asSequence().toSet() == setOf("payload", "signature"))
        val payload = decode(response.getString("payload"), 4096)
        val signature = decode(response.getString("signature"), 128)
        // Untrusted until saveFresh verifies signature, account/device and canonical payload.
        val issued = JSONObject(String(payload, Charsets.US_ASCII)).getLong("issued_at")
        currentCoroutineContext().ensureActive()
        check(!closed && isCurrent())
        val saved = cache.saveFresh(payload, signature, account, issued, anchor)
        if (closed || !isCurrent()) {
            cache.clear()
            return@withContext false
        }
        saved && cache.active(account)
    }

    suspend fun checkCached(account: String): Boolean = withContext(Dispatchers.IO) {
        !closed && isCurrent() && cache.active(account)
    }

    fun clear() { cache.clear() }

    fun close() {
        closed = true
        cache.clear()
    }
}
