package com.mochyy.mochymusic.guardian

import java.security.MessageDigest

/** Read-only export/erasure preview follows the existing server's accepted
 * identifier grammar, including historical IDs that cannot be restored locally.
 * Never require a valid local library or an active membership to export data. */
internal object CloudRemoteData {
    data class Snapshot(val digest: String, val favorites: Int, val playlists: Int, val json: String)
    private val id = Regex("[A-Za-z0-9_-]{1,128}")

    fun inspect(revision: Long, body: Map<String, Any?>): Snapshot {
        require(revision in 1 until Long.MAX_VALUE)
        require(body.keys == setOf("favorites", "playlists", "preferences"))
        fun tracks(value: Any?): List<*> {
            val list = requireNotNull(value as? List<*>)
            require(list.size <= 1000 && list.all { it is String && id.matches(it) })
            require(list.distinct().size == list.size)
            return list
        }
        val favorites = tracks(body["favorites"])
        val lists = requireNotNull(body["playlists"] as? List<*>)
        require(lists.size <= 100)
        val ids = mutableSetOf<String>()
        for (entry in lists) {
            val list = requireNotNull(entry as? Map<*, *>)
            require(list.keys == setOf("id", "name", "tracks"))
            val key = requireNotNull(list["id"] as? String)
            require(id.matches(key) && ids.add(key))
            val name = requireNotNull(list["name"] as? String)
            require(name.isNotEmpty() && name.codePointCount(0, name.length) <= 120 && name.none { it.code < 32 })
            tracks(list["tracks"])
        }
        val prefs = requireNotNull(body["preferences"] as? Map<*, *>)
        for ((key, value) in prefs) when (key) {
            "theme" -> require(value in setOf("system", "light", "dark"))
            "repeat" -> require(value in setOf("off", "one", "all"))
            "shuffle" -> require(value is Boolean)
            else -> error("Unsupported cloud preference")
        }
        val json = AccountProofV2.canonicalBody("cloud_write", mapOf("revision" to revision, "library" to body))
        val digest = MessageDigest.getInstance("SHA-256").digest(json.toByteArray(Charsets.US_ASCII))
            .joinToString("") { "%02x".format(it.toInt() and 255) }
        return Snapshot(digest, favorites.size, lists.size, json)
    }
}
