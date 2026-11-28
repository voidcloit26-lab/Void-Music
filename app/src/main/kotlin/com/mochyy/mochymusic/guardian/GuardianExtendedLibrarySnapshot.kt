package com.mochyy.mochymusic.guardian

import com.mochyy.mochymusic.db.MusicDatabase
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/** Read-only, account-bound capture for the future extended metadata transport.
 * No upload, local mutation or provider action. History is separately opt-in.
 * Never silently truncate an oversized library. */
internal object GuardianExtendedLibrarySnapshot {
    data class Preview(val snapshot: ExtendedLibraryV1.Snapshot, val excludedAlbums: Int,
                       val excludedArtists: Int, val excludedHistory: Int)

    suspend fun capture(database: MusicDatabase, includeHistory: Boolean,
                        stillOwnsLibrary: () -> Boolean): Preview = withContext(Dispatchers.IO) {
        check(stillOwnsLibrary())
        val db = database.openHelper.writableDatabase
        val albums = mutableListOf<String>()
        val artists = mutableListOf<String>()
        val history = if (includeHistory) linkedSetOf<ExtendedLibraryV1.Play>() else null
        var excludedAlbums = 0
        var excludedArtists = 0
        var excludedHistory = 0
        db.beginTransactionNonExclusive()
        try {
            db.query("SELECT id,isLocal,isUploaded FROM album WHERE bookmarkedAt IS NOT NULL ORDER BY id").use { cursor ->
                while (cursor.moveToNext()) {
                    check(stillOwnsLibrary())
                    val id = cursor.getString(0)
                    if (cursor.getInt(1) != 0 || cursor.getInt(2) != 0 || !ExtendedLibraryV1.publicAlbum(id)) excludedAlbums++
                    else albums.add(id)
                    require(albums.size <= ExtendedLibraryV1.MAX_ALBUMS) { "Saved album backup limit exceeded" }
                }
            }
            db.query("SELECT id,isLocal FROM artist WHERE bookmarkedAt IS NOT NULL ORDER BY id").use { cursor ->
                while (cursor.moveToNext()) {
                    check(stillOwnsLibrary())
                    val id = cursor.getString(0)
                    if (cursor.getInt(1) != 0 || !ExtendedLibraryV1.publicArtist(id)) excludedArtists++
                    else artists.add(id)
                    require(artists.size <= ExtendedLibraryV1.MAX_ARTISTS) { "Saved artist backup limit exceeded" }
                }
            }
            if (history != null) {
                db.query("SELECT e.songId,e.timestamp,e.playTime,s.isLocal,s.isUploaded,s.localUri FROM event e JOIN song s ON s.id=e.songId ORDER BY e.timestamp,e.id").use { cursor ->
                    while (cursor.moveToNext()) {
                        check(stillOwnsLibrary())
                        val item = ExtendedLibraryV1.Play(cursor.getString(0), cursor.getLong(1), cursor.getLong(2))
                        if (cursor.getInt(3) != 0 || cursor.getInt(4) != 0 || !cursor.isNull(5) ||
                            !ExtendedLibraryV1.validPlay(item) || !history.add(item)) excludedHistory++
                        require(history.size <= ExtendedLibraryV1.MAX_HISTORY) { "Listening history backup limit exceeded" }
                    }
                }
            }
            check(stillOwnsLibrary())
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
        Preview(ExtendedLibraryV1.normalize(ExtendedLibraryV1.Snapshot(albums, artists, history?.toList())),
            excludedAlbums, excludedArtists, excludedHistory)
    }
}
