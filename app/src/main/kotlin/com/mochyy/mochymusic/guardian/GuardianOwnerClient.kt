package com.mochyy.mochymusic.guardian

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.URL
import javax.net.ssl.HttpsURLConnection

/** Native HTTPS client; no embedded browser, persistent password or provider error text. */
internal object GuardianOwnerClient {
    private const val origin = "https://void-guardian-owner-staging.onrender.com"
    data class Reply(val status: Int, val data: JSONObject)
    suspend fun call(action: String, data: JSONObject = JSONObject(), token: String = ""): Reply = withContext(Dispatchers.IO) {
        require(action in setOf("login", "list", "generate", "cancel", "revoke", "logout"))
        val conn = URL("$origin/native/v1/$action").openConnection() as HttpsURLConnection
        try {
            conn.instanceFollowRedirects = false
            conn.connectTimeout = 20_000
            conn.readTimeout = 75_000
            conn.requestMethod = "POST"
            conn.doOutput = true
            conn.useCaches = false
            conn.setRequestProperty("Content-Type", "application/json")
            conn.setRequestProperty("Accept", "application/json")
            if (token.isNotEmpty()) {
                require(Regex("[A-Za-z0-9_-]{43}").matches(token))
                conn.setRequestProperty("Authorization", "Bearer $token")
            }
            val bytes = data.toString().toByteArray(Charsets.UTF_8)
            require(bytes.size <= 4096)
            conn.setFixedLengthStreamingMode(bytes.size)
            conn.outputStream.use { it.write(bytes) }
            val status = conn.responseCode
            if (status !in 200..299) return@withContext Reply(status, JSONObject())
            require(conn.contentType?.substringBefore(";") == "application/json")
            val out = ByteArrayOutputStream()
            conn.inputStream.use { input ->
                val buffer = ByteArray(4096)
                while (true) {
                    val n = input.read(buffer)
                    if (n < 0) break
                    require(out.size() + n <= 512 * 1024)
                    out.write(buffer, 0, n)
                }
            }
            Reply(status, JSONObject(out.toString("UTF-8")))
        } finally {
            conn.disconnect()
        }
    }
}
