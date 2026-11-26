package com.mochyy.mochymusic.guardian

import java.security.MessageDigest

/** Conservative metadata comparison. Never treats removal, rename, reorder or
 * preference changes as an automatic additive upload. No network or audio. */
internal class CloudMetadata private constructor(
    private val favorites: List<String>,
    private val playlists: List<Playlist>,
    private val preferences: Map<String, String>,
) {
    private data class Playlist(val id: String, val name: String, val tracks: List<String>)

    fun digest(): String {
        val hash = MessageDigest.getInstance("SHA-256")
        fun field(value: String) {
            // UTF-8 length framing prevents delimiter ambiguity.
            val bytes = value.toByteArray(Charsets.UTF_8)
            hash.update(bytes.size.toString().toByteArray(Charsets.US_ASCII))
            hash.update(58.toByte())
            hash.update(bytes)
        }
        field("void-cloud-metadata-v1")
        field(favorites.size.toString())
        favorites.forEach { field(it) }
        field(playlists.size.toString())
        playlists.forEach { p ->
            field(p.id); field(p.name); field(p.tracks.size.toString())
            p.tracks.forEach { field(it) }
        }
        field(preferences.size.toString())
        preferences.toSortedMap().forEach { (k,v) -> field(k); field(v) }
        return hash.digest().joinToString("") { "%02x".format(it.toInt() and 255) }
    }

    fun additiveTo(previous: CloudMetadata): Boolean {
        if (preferences != previous.preferences || !favorites.containsAll(previous.favorites)) return false
        val current = playlists.associateBy { it.id }
        return previous.playlists.all { old ->
            val next = current[old.id] ?: return@all false
            next.name == old.name && next.tracks.take(old.tracks.size) == old.tracks
        }
    }

    companion object {
        private val trackId = Regex("[A-Za-z0-9_-]{11}")
        private val listId = Regex("[A-Za-z0-9_-]{1,128}")
        private fun tracks(value: Any?): List<String> {
            val list = requireNotNull(value as? List<*>)
            require(list.size <= 1000)
            val result = list.map { requireNotNull(it as? String).also { id -> require(trackId.matches(id)) } }
            require(result.distinct().size == result.size)
            return result
        }
        fun parse(body: Map<String, Any?>): CloudMetadata {
            require(body.keys == setOf("favorites", "playlists", "preferences"))
            val lists = requireNotNull(body["playlists"] as? List<*>)
            require(lists.size <= 100)
            val playlists = lists.map {
                val p = requireNotNull(it as? Map<*, *>)
                require(p.keys == setOf("id", "name", "tracks"))
                val id = requireNotNull(p["id"] as? String)
                val name = requireNotNull(p["name"] as? String)
                require(listId.matches(id) && id !in setOf("LP_LIKED", "LP_DOWNLOADED"))
                require(name.length in 1..120 && name.none { c -> c.code < 32 })
                // Reject unpaired surrogates rather than hash replacement characters.
                require(Charsets.UTF_8.newEncoder().canEncode(name))
                Playlist(id, name, tracks(p["tracks"]))
            }.sortedBy { it.id }
            require(playlists.map { it.id }.distinct().size == playlists.size)
            val raw = requireNotNull(body["preferences"] as? Map<*, *>)
            val prefs = raw.entries.associate { (k,v) ->
                val key = requireNotNull(k as? String)
                val value = when (key) {
                    "theme" -> requireNotNull(v as? String).also { require(it in setOf("system","light","dark")) }
                    "repeat" -> requireNotNull(v as? String).also { require(it in setOf("off","one","all")) }
                    "shuffle" -> requireNotNull(v as? Boolean).toString()
                    else -> throw IllegalArgumentException("Unsupported preference")
                }
                key to value
            }
            return CloudMetadata(tracks(body["favorites"]).sorted(), playlists, prefs)
        }
    }
}
