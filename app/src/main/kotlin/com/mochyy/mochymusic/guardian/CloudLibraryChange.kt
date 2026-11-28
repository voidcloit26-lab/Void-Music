package com.mochyy.mochymusic.guardian

/** A reviewed replacement of eligible cloud metadata, never a local deletion.
 * Count removals and changed playlists separately from newly created ones. */
internal data class CloudLibraryChange(
    val addedFavorites: Int,
    val removedFavorites: Int,
    val addedPlaylists: Int,
    val removedPlaylists: Int,
    val changedPlaylists: Int,
) {
    val removesOrChanges: Boolean
        get() = removedFavorites > 0 || removedPlaylists > 0 || changedPlaylists > 0

    companion object {
        fun compare(previous: Map<String, Any?>, next: Map<String, Any?>): CloudLibraryChange {
            CloudMetadata.parse(previous)
            CloudMetadata.parse(next)
            require(previous["preferences"] == next["preferences"]) { "Review playback settings separately" }
            fun favorites(body: Map<String, Any?>) = (body["favorites"] as List<*>).toSet()
            fun playlists(body: Map<String, Any?>) = (body["playlists"] as List<*>)
                .map { it as Map<*, *> }.associateBy { it["id"] }
            val before = favorites(previous)
            val after = favorites(next)
            val oldLists = playlists(previous)
            val newLists = playlists(next)
            return CloudLibraryChange(
                (after - before).size,
                (before - after).size,
                (newLists.keys - oldLists.keys).size,
                (oldLists.keys - newLists.keys).size,
                oldLists.keys.intersect(newLists.keys).count { oldLists[it] != newLists[it] },
            )
        }
    }
}
