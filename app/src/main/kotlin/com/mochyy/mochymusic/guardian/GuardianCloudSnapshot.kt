package com.mochyy.mochymusic.guardian

import com.mochyy.mochymusic.db.MusicDatabase
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Read-only preview of the deliberately limited V2 metadata backup.
 * No database migration, file transfer, provider request or automatic upload.
 * Require explicit consent before sending; show exclusions and size errors.
 */
internal object GuardianCloudSnapshot {
    private val trackId = Regex("[A-Za-z0-9_-]{11}")
    private val playlistId = Regex("[A-Za-z0-9_-]{1,128}")
    data class Preview(val body: Map<String, Any?>, val excludedEntries: Int)

    suspend fun capture(database: MusicDatabase, preferences: Map<String, Any?> = emptyMap()): Preview =
        withContext(Dispatchers.IO) {
            require(preferences.keys.all { it in setOf("theme", "repeat", "shuffle") })
            require(!preferences.containsKey("theme") || preferences["theme"] in listOf("system","light","dark"))
            require(!preferences.containsKey("repeat") || preferences["repeat"] in listOf("off","one","all"))
            require(!preferences.containsKey("shuffle") || preferences["shuffle"] is Boolean)
            val db = database.openHelper.writableDatabase
            var excluded = 0
            val favorites = linkedSetOf<String>()
            val playlists = mutableListOf<Map<String, Any?>>()
            db.beginTransactionNonExclusive()
            try {
                db.query("SELECT id,isLocal,isUploaded,localUri FROM song WHERE liked=1 ORDER BY id").use { cursor ->
                    while (cursor.moveToNext()) {
                        val id = cursor.getString(0)
                        if (cursor.getInt(1)!=0 || cursor.getInt(2)!=0 || !cursor.isNull(3) || !trackId.matches(id)) excluded++
                        else favorites.add(id)
                        require(favorites.size <= 1000) { "Cloud favorite limit exceeded" }
                    }
                }
                // Only independent editable playlists, never provider-managed playlists.
                db.query("SELECT id,name,browseId,isEditable FROM playlist WHERE bookmarkedAt IS NOT NULL ORDER BY id").use { cursor ->
                    while (cursor.moveToNext()) {
                        val id = cursor.getString(0)
                        val name = cursor.getString(1)
                        if (!cursor.isNull(2) || cursor.getInt(3)==0 || !playlistId.matches(id) ||
                            id in listOf("LP_LIKED","LP_DOWNLOADED") || name.length !in 1..120 ||
                            name.any { it.code < 32 }) {
                            excluded++
                            continue
                        }
                        val tracks = linkedSetOf<String>()
                        db.query("SELECT s.id,s.isLocal,s.isUploaded,s.localUri FROM playlist_song_map m JOIN song s ON s.id=m.songId WHERE m.playlistId=? ORDER BY m.position,m.id", arrayOf<Any?>(id)).use { songs ->
                            while (songs.moveToNext()) {
                                val track = songs.getString(0)
                                if (songs.getInt(1)!=0 || songs.getInt(2)!=0 || !songs.isNull(3) ||
                                    !trackId.matches(track) || !tracks.add(track)) excluded++
                                require(tracks.size <= 1000) { "Cloud playlist track limit exceeded" }
                            }
                        }
                        playlists.add(mapOf("id" to id, "name" to name, "tracks" to tracks.toList()))
                        require(playlists.size <= 100) { "Cloud playlist limit exceeded" }
                    }
                }
                db.setTransactionSuccessful()
            } finally {
                db.endTransaction()
            }
            val body = mapOf("favorites" to favorites.toList(),"playlists" to playlists.toList(),
                "preferences" to preferences.toMap())
            // Keep a safety margin; Guardian validates its own 512 KiB limit.
            require(AccountProofV2.canonicalBody("cloud_write",mapOf("revision" to 0L,"library" to body)).length <= 512 * 1024)
            Preview(body, excluded)
        }
}
