package com.mochyy.mochymusic.guardian

import java.security.MessageDigest

/** Canonical request bytes shared with Guardian's Python V2 protocol. */
internal object AccountProofV2 {
    private val actions = mapOf(
        "register" to emptySet(), "recover" to setOf("recovery"),
        "register_with_code" to setOf("code"), "redeem_activation" to setOf("code"),
        "identity_role" to emptySet(), "register_owner" to emptySet(),
        "rotate_recovery" to emptySet(), "lease" to emptySet(),
        "status" to emptySet(), "redeem_free" to setOf("code"),
        "cloud_read" to emptySet(), "cloud_write" to setOf("revision", "library"),
        "cloud_clear" to setOf("revision")
    )
    private fun quote(value: String): String = buildString {
        append('"')
        value.forEach { c ->
            when (c) {
                '"' -> append("\\\"")
                '\\' -> append("\\\\")
                '\b' -> append("\\b")
                '\t' -> append("\\t")
                '\n' -> append("\\n")
                '\u000c' -> append("\\f")
                '\r' -> append("\\r")
                else -> if (c.code < 32 || c.code >= 127) {
                    append("\\u").append(c.code.toString(16).padStart(4, '0'))
                } else append(c)
            }
        }
        append('"')
    }

    private fun encode(value: Any?, depth: Int = 0): String {
        require(depth <= 12)
        return when (value) {
            null -> "null"
            is Boolean -> value.toString()
            is Int, is Long -> value.toString()
            is String -> quote(value)
            is List<*> -> value.joinToString(",", "[", "]") { encode(it, depth + 1) }
            is Map<*, *> -> {
                require(value.keys.all { it is String && it.all { c -> c.code < 127 } })
                value.entries.sortedBy { it.key as String }.joinToString(",", "{", "}") {
                    quote(it.key as String) + ":" + encode(it.value, depth + 1)
                }
            }
            else -> throw IllegalArgumentException("Unsupported JSON type")
        }
    }

    fun canonicalBody(action: String, body: Map<String, Any?>): String {
        require(actions[action] == body.keys)
        if ("revision" in body) {
            val revision = body["revision"]
            require(revision is Int || revision is Long)
            require((revision as Number).toLong() in 0 until Long.MAX_VALUE)
        }
        if ("recovery" in body) require((body["recovery"] as? String)?.length == 43)
        if ("code" in body) require((body["code"] as? String)?.length == 43)
        return encode(body).also { require(it.length <= 600 * 1024) }
    }

    fun message(nonce: String, fingerprint: String, sessionId: String, subject: String,
                action: String, body: Map<String, Any?>): ByteArray {
        require(Regex("[A-Za-z0-9_-]{43}").matches(nonce))
        require(Regex("[0-9a-f]{64}").matches(fingerprint))
        require(Regex("sess_[A-Za-z0-9]{1,120}").matches(sessionId))
        require(Regex("user_[A-Za-z0-9]{1,120}").matches(subject))
        val digest = MessageDigest.getInstance("SHA-256")
            .digest(canonicalBody(action, body).toByteArray(Charsets.US_ASCII))
            .joinToString("") { "%02x".format(it.toInt() and 255) }
        return "VOID-ACCOUNT-PROOF-v2\n$nonce\n$fingerprint\n$sessionId\n$subject\n$action\n$digest".toByteArray(Charsets.US_ASCII)
    }
}
