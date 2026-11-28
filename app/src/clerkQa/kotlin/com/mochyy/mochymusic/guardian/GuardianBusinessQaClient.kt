package com.mochyy.mochymusic.guardian

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.net.URL
import javax.net.ssl.HttpsURLConnection

/** Owner-only QA client. Uses the same Clerk session, not an embedded password. */
internal class GuardianBusinessQaClient(
    private val expectedSubject: String,
    private val expectedSession: String
) {
    private val lock = Mutex()
    private val origin = "https://void-guardian-v2-business-stage.onrender.com"
    private val allowed = setOf("summary","member","price","state","audit","codes/create","codes/list","codes/cancel","codes/history")
    private suspend fun checked() = ClerkQaBridge.currentSession().also {
        check(it.subject == expectedSubject && it.sessionId == expectedSession)
        require(it.token.length in 1..8192 && Regex("[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+").matches(it.token))
    }
    suspend fun request(action: String, data: JSONObject = JSONObject()): JSONObject = lock.withLock {
        withContext(Dispatchers.IO) {
            require(action in allowed)
            val auth = checked()
            val body = data.toString().toByteArray(Charsets.UTF_8)
            require(body.size in 1..4096)
            val conn = URL("$origin/owner/v2/$action").openConnection() as HttpsURLConnection
            try {
                conn.instanceFollowRedirects = false
                conn.connectTimeout = 15000
                conn.readTimeout = 25000
                conn.requestMethod = "POST"
                conn.doOutput = true
                conn.useCaches = false
                conn.setRequestProperty("Authorization", "Bearer ${auth.token}")
                conn.setRequestProperty("Content-Type", "application/json")
                conn.setRequestProperty("Accept", "application/json")
                conn.setFixedLengthStreamingMode(body.size)
                conn.outputStream.use { it.write(body) }
                val status = conn.responseCode
                if (status != 200) throw GuardianAccountClient.RequestFailed(status)
                require(conn.contentType?.substringBefore(';')?.trim()?.lowercase() == "application/json")
                val out = ByteArrayOutputStream()
                conn.inputStream.use { input ->
                    val buffer = ByteArray(4096)
                    while (true) {
                        val n = input.read(buffer)
                        if (n < 0) break
                        require(out.size() + n <= 512*1024)
                        out.write(buffer,0,n)
                    }
                }
                checked()
                JSONObject(out.toString("UTF-8"))
            } finally { conn.disconnect() }
        }
    }
}
