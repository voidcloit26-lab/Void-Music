package com.mochyy.mochymusic.guardian

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.URL
import javax.net.ssl.HttpsURLConnection

/**
 * Staged V2 transport. No live origin or Clerk SDK is configured here.
 * Caller obtains a current token from the authentication SDK, not local storage.
 */
internal class GuardianAccountClient(
    origin: String,
    private val session: suspend () -> Session,
    private val expectedSubject: String? = null,
    private val expectedSessionId: String? = null,
) {
    // Never log or persist instances of Session or responses containing recovery codes.
    class Session(val token: String, val subject: String, val sessionId: String)
    class RequestFailed(val status: Int) : Exception("Guardian request failed ($status)")
    private val base = URL(origin)
    private val lock = Mutex()

    init {
        require(base.protocol == "https" && base.host.isNotBlank() &&
            base.userInfo == null && base.query == null && base.ref == null &&
            base.path in listOf("", "/") && base.port in listOf(-1, 443))
    }

    suspend fun request(action: String, body: Map<String, Any?>): JSONObject =
        lock.withLock {
            withContext(Dispatchers.IO) {
                // Snapshot the exact request before the challenge; caller mutations
                // cannot alter the body after it has been signed.
                val snapshot = objectMap(JSONObject(AccountProofV2.canonicalBody(action, body)))
                val auth = checkedSession()
                require(auth.token.length in 1..8192 && Regex("[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+").matches(auth.token))
                require(Regex("user_[A-Za-z0-9]{1,120}").matches(auth.subject))
                require(Regex("sess_[A-Za-z0-9]{1,120}").matches(auth.sessionId))
                val key = DeviceEntitlement.encodedPublicKey()
                val canonical = AccountProofV2.canonicalBody(action, snapshot)
                val challengeBody = JSONObject().put("public_key", key)
                    .put("action", action).put("body", JSONObject(canonical))
                val challenge = post("/v2/challenge", auth.token, challengeBody)
                val nonce = challenge.getString("nonce")
                val proof = DeviceEntitlement.signAccountRequest(nonce, auth.sessionId,
                    auth.subject, action, snapshot)
                // Clerk session tokens can expire between the challenge and execution.
                // Refresh the token without allowing identity or session changes.
                val refreshed = checkedSession()
                check(refreshed.subject == auth.subject && refreshed.sessionId == auth.sessionId)
                val execution = JSONObject().put("public_key", key).put("action", action)
                    .put("body", JSONObject(canonical)).put("nonce", nonce).put("signature", proof)
                // No automatic retry of a mutation: a lost response may have
                // committed the operation. Refresh state before retrying.
                val response = post("/v2/execute", refreshed.token, execution)
                val after = checkedSession()
                check(after.subject == auth.subject && after.sessionId == auth.sessionId)
                response
            }
        }

    private suspend fun checkedSession(): Session = session().also {
        check(expectedSubject == null || it.subject == expectedSubject)
        check(expectedSessionId == null || it.sessionId == expectedSessionId)
        require(it.token.length in 1..8192 && Regex("[A-Za-z0-9_-]+\\\\.[A-Za-z0-9_-]+\\\\.[A-Za-z0-9_-]+").matches(it.token))
    }

    private fun objectMap(value: JSONObject): Map<String, Any?> =
        value.keys().asSequence().associateWith { convert(value.get(it)) }

    private fun convert(value: Any?): Any? = when (value) {
        null, JSONObject.NULL -> null
        is JSONObject -> objectMap(value)
        is JSONArray -> List(value.length()) { convert(value.get(it)) }
        is String, is Boolean, is Int, is Long -> value
        else -> throw IllegalArgumentException("Unsupported request value")
    }

    private fun post(path: String, token: String, body: JSONObject): JSONObject {
        require(path == "/v2/challenge" || path == "/v2/execute")
        val conn = URL(base.toString().trimEnd('/') + path).openConnection() as HttpsURLConnection
        try {
            conn.instanceFollowRedirects = false
            conn.connectTimeout = 15_000
            conn.readTimeout = 25_000
            conn.requestMethod = "POST"
            conn.doOutput = true
            conn.useCaches = false
            conn.setRequestProperty("Authorization", "Bearer $token")
            conn.setRequestProperty("Content-Type", "application/json")
            conn.setRequestProperty("Accept", "application/json")
            conn.setRequestProperty("Cache-Control", "no-store")
            val bytes = body.toString().toByteArray(Charsets.UTF_8)
            require(bytes.size <= 600 * 1024 + 4096)
            conn.setFixedLengthStreamingMode(bytes.size)
            conn.outputStream.use { it.write(bytes) }
            val status = conn.responseCode
            if (status != 200) throw RequestFailed(status)
            require(conn.contentType?.substringBefore(";")?.trim()?.lowercase() == "application/json")
            val output = ByteArrayOutputStream()
            conn.inputStream.use { input ->
                val buffer = ByteArray(8192)
                while (true) {
                    val n = input.read(buffer)
                    if (n < 0) break
                    require(output.size() + n <= 600 * 1024 + 4096)
                    output.write(buffer, 0, n)
                }
            }
            return JSONObject(output.toString("UTF-8"))
        } finally {
            conn.disconnect()
        }
    }
}
