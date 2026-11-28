package com.mochyy.mochymusic.guardian

/** Versioned extension to the current favorites/playlist format. History is
 * opt-in separately: null means not included, not an empty history.
 * Only public provider identifiers and bounded playback metadata are allowed. */
internal object ExtendedLibraryV1 {
    const val MAX_ALBUMS = 1000
    const val MAX_ARTISTS = 1000
    const val MAX_HISTORY = 5000
    const val MAX_PLAY_MS = 86_400_000L
    private val album = Regex("MPREb[A-Za-z0-9_-]{1,64}")
    private val artist = Regex("UC[A-Za-z0-9_-]{22}")
    private val song = Regex("[A-Za-z0-9_-]{11}")
    data class Play(val songId: String, val timestampMs: Long, val playedMs: Long)
    data class Snapshot(val albums: List<String>, val artists: List<String>, val history: List<Play>?)

    fun publicAlbum(id: String) = album.matches(id)
    fun publicArtist(id: String) = artist.matches(id)
    fun publicSong(id: String) = song.matches(id)
    fun validPlay(play: Play): Boolean = publicSong(play.songId) &&
        play.timestampMs in 1L..253402300799999L && play.playedMs in 1L..MAX_PLAY_MS

    fun normalize(snapshot: Snapshot): Snapshot {
        require(snapshot.albums.size <= MAX_ALBUMS && snapshot.albums.all(::publicAlbum))
        require(snapshot.artists.size <= MAX_ARTISTS && snapshot.artists.all(::publicArtist))
        require(snapshot.albums.distinct().size == snapshot.albums.size)
        require(snapshot.artists.distinct().size == snapshot.artists.size)
        val history = snapshot.history?.let { entries ->
            require(entries.size <= MAX_HISTORY && entries.all(::validPlay))
            require(entries.distinct().size == entries.size)
            entries.sortedWith(compareBy<Play> { it.timestampMs }.thenBy { it.songId }.thenBy { it.playedMs })
        }
        return Snapshot(snapshot.albums.sorted(), snapshot.artists.sorted(), history)
    }
}
