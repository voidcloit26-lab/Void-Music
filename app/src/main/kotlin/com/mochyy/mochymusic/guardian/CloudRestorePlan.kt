package com.mochyy.mochymusic.guardian

/** Pure, non-destructive restore planning. No network or database writes. */
internal object CloudRestorePlan {
    data class Playlist(val id: String, val name: String, val tracks: List<String>)
    data class Library(val favorites: List<String>, val playlists: List<Playlist>)
    data class Append(val playlistId: String, val existingCount: Int, val tracks: List<String>)
    data class Plan(val addFavorites: List<String>, val addPlaylists: List<Playlist>,
                    val missingTracks: Set<String>, val conflictingPlaylists: Set<String>,
                    val appendTracks: List<Append> = emptyList()) {
        val ready: Boolean get() = missingTracks.isEmpty() && conflictingPlaylists.isEmpty()
    }
    private val trackId = Regex("[A-Za-z0-9_-]{11}")
    private val playlistId = Regex("[A-Za-z0-9_-]{1,128}")
    private val reserved = setOf("LP_LIKED", "LP_DOWNLOADED")

    private fun validateTracks(tracks: List<String>) {
        require(tracks.size <= 1000 && tracks.all(trackId::matches) && tracks.distinct().size == tracks.size)
    }
    fun validate(library: Library) {
        validateTracks(library.favorites)
        require(library.playlists.size <= 100 && library.playlists.map { it.id }.distinct().size == library.playlists.size)
        for (playlist in library.playlists) {
            require(playlistId.matches(playlist.id) && playlist.id !in reserved)
            require(playlist.name.length in 1..120 && playlist.name.none { it.code < 32 })
            validateTracks(playlist.tracks)
        }
    }
    fun build(cloud: Library, localFavorites: Set<String>, localPlaylists: Map<String, Playlist?>,
              eligibleTracks: Set<String>): Plan {
        validate(cloud)
        // A null local entry is a reserved, provider-managed or otherwise non-restorable playlist.
        val missing = (cloud.favorites + cloud.playlists.flatMap { it.tracks }).filterNot { it in eligibleTracks }.toSet()
        val conflicts = mutableSetOf<String>()
        val append = mutableListOf<Append>()
        for (remote in cloud.playlists) {
            if (!localPlaylists.containsKey(remote.id)) continue
            val local = localPlaylists[remote.id]
            when {
                local == null || local.name != remote.name -> conflicts.add(remote.id)
                local.tracks.take(remote.tracks.size) == remote.tracks -> Unit // local is equal or newer
                remote.tracks.take(local.tracks.size) == local.tracks ->
                    append.add(Append(remote.id, local.tracks.size, remote.tracks.drop(local.tracks.size)))
                else -> conflicts.add(remote.id) // reorder, rename, divergent history
            }
        }
        return Plan(cloud.favorites.filterNot { it in localFavorites },
            cloud.playlists.filterNot { localPlaylists.containsKey(it.id) }, missing, conflicts, append)
    }
}
