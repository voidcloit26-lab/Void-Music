package com.mochyy.mochymusic.guardian

/** Only saved playback preferences, never identity, tokens, or local paths. */
internal object GuardianPlaybackPreferences {
    data class Saved(val repeat: String, val shuffle: Boolean) {
        init { require(repeat in setOf("off", "one", "all")) }
        fun body(): Map<String, Any?> = mapOf("repeat" to repeat, "shuffle" to shuffle)
        fun repeatMode(): Int = when (repeat) { "off" -> 0; "one" -> 1; else -> 2 }
    }
    fun capture(repeat: Int, shuffle: Boolean): Saved =
        Saved(when (repeat) { 0 -> "off"; 1 -> "one"; 2 -> "all"; else -> error("Invalid repeat mode") }, shuffle)
    fun read(remote: Map<String, Any?>): Saved? {
        require(remote.keys.all { it in setOf("theme", "repeat", "shuffle") })
        if (!remote.containsKey("repeat") || !remote.containsKey("shuffle")) return null
        return Saved(requireNotNull(remote["repeat"] as? String), requireNotNull(remote["shuffle"] as? Boolean))
    }
    fun merge(remote: Map<String, Any?>, saved: Saved): Map<String, Any?> {
        require(remote.keys.all { it in setOf("theme", "repeat", "shuffle") })
        return remote + saved.body()
    }
}
