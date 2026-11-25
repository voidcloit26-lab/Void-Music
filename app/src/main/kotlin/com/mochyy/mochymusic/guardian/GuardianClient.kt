package com.mochyy.mochymusic.guardian

import android.content.Context
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.URL
import javax.net.ssl.HttpsURLConnection
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Activation transport; deliberately not yet wired to startup. The origin and public
 * signing key must come from immutable release configuration, never from an invitation
 * or server response. Only verified status denial removes an offline lifetime receipt.
 */
internal class GuardianClient(
    context: Context,
    private val origin: String,
    private val serverPublicKey: String,
) {
    private val app = context.applicationContext
    private val endpoint = URL(origin)

    init {
        require(endpoint.protocol == "https" && endpoint.host.isNotBlank() &&
            endpoint.userInfo == null && endpoint.query == null && endpoint.ref == null &&
            endpoint.path in listOf("", "/") && endpoint.port in listOf(-1, 443))
        require(serverPublicKey.isNotBlank())
    }

    enum class Outcome { Active, Denied, Revoked, Retry, InvalidReceipt }

    suspend fun redeem(input: String): Outcome = withContext(Dispatchers.IO) {
        val code = input.trim().uppercase(java.util.Locale.ROOT)
        if (!Regex("VOID-(?:[0-9A-F]{8}-){3}[0-9A-F]{8}").matches(code))
            return@withContext Outcome.Denied
        exchange("redeem", code)
    }

    suspend fun refresh(): Outcome = withContext(Dispatchers.IO) {
        exchange("status", "")
    }

    private fun exchange(action: String, code: String): Outcome = try {
        val public = DeviceEntitlement.encodedPublicKey()
        val challenge = post("/v1/challenge", JSONObject().put("public_key", public).put("action", action))
        if (challenge.status != 200) Outcome.Retry else {
            val nonce = JSONObject(challenge.body).getString("nonce")
            val body = JSONObject().put("public_key", public).put("nonce", nonce)
                .put("signature", DeviceEntitlement.signChallenge(nonce, action, code))
            if (action == "redeem") body.put("code", code)
            val result = post("/v1/$action", body)
            when {
                result.status == 200 -> if (DeviceEntitlement.save(app, result.body, serverPublicKey))
                    Outcome.Active else Outcome.InvalidReceipt
                result.status == 403 && action == "status" &&
                    JSONObject(result.body).optString("error") == "access_inactive" -> {
                    DeviceEntitlement.clear(app)
                    Outcome.Revoked
                }
                result.status == 403 -> Outcome.Denied
                else -> Outcome.Retry
            }
        }
    } catch (_: Exception) {
        // A network failure does not destroy a valid lifetime receipt.
        Outcome.Retry
    }

    private data class Reply(val status: Int, val body: String)

    private fun post(path: String, body: JSONObject): Reply {
        val conn = URL(origin.trimEnd('/') + path).openConnection() as HttpsURLConnection
        try {
            conn.instanceFollowRedirects = false
            conn.connectTimeout = 8000
            conn.readTimeout = 8000
            conn.requestMethod = "POST"
            conn.doOutput = true
            conn.useCaches = false
            conn.setRequestProperty("Content-Type", "application/json")
            conn.setRequestProperty("Accept", "application/json")
            val bytes = body.toString().toByteArray(Charsets.UTF_8)
            require(bytes.size <= 4096)
            conn.setFixedLengthStreamingMode(bytes.size)
            conn.outputStream.use { it.write(bytes) }
            val status = conn.responseCode
            val source = if (status in 200..299) conn.inputStream else conn.errorStream
            val out = ByteArrayOutputStream()
            source?.use {
                val buffer = ByteArray(1024)
                while (true) {
                    val n = it.read(buffer)
                    if (n < 0) break
                    require(out.size() + n <= 8192)
                    out.write(buffer, 0, n)
                }
            }
            return Reply(status, out.toString("UTF-8"))
        } finally {
            conn.disconnect()
        }
    }
}
