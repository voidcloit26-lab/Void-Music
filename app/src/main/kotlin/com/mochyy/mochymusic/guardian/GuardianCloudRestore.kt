package com.mochyy.mochymusic.guardian

import androidx.sqlite.db.SupportSQLiteDatabase
import com.mochyy.mochymusic.db.MusicDatabase
import com.mochyy.mochymusic.db.entities.PlaylistEntity
import com.mochyy.mochymusic.db.entities.PlaylistSongMap
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDateTime

/**
 * Explicit restore only. No deletion, provider sync, audio download or
 * destructive overwrite. Caller must bind the snapshot to the signed-in account,
 * obtain user consent and resolve missing metadata through authorized providers.
 */
internal object GuardianCloudRestore {
    private fun fields(obj: JSONObject): Set<String> = obj.keys().asSequence().toSet()
    private fun strings(array: JSONArray): List<String> {
        require(array.length() <= 1000)
        return List(array.length()) { requireNotNull(array.get(it) as? String) }
    }
    fun parse(library: JSONObject): CloudRestorePlan.Library {
        require(fields(library) == setOf("favorites", "playlists", "preferences"))
        val lists = library.getJSONArray("playlists")
        require(lists.length() <= 100)
        val result = CloudRestorePlan.Library(strings(library.getJSONArray("favorites")),
            List(lists.length()) { index ->
                val item = lists.getJSONObject(index)
                require(fields(item) == setOf("id", "name", "tracks"))
                CloudRestorePlan.Playlist(requireNotNull(item.get("id") as? String),
                    requireNotNull(item.get("name") as? String), strings(item.getJSONArray("tracks")))
            })
        CloudRestorePlan.validate(result)
        // Preferences intentionally remain separate from music metadata restoration.
        return result
    }

    private fun eligible(db: SupportSQLiteDatabase, ids: Set<String>): Set<String> {
        val result = mutableSetOf<String>()
        for (batch in ids.chunked(400)) {
            val slots = batch.joinToString(",") { "?" }
            db.query("SELECT id FROM song WHERE id IN ($slots) AND isLocal=0 AND isUploaded=0 AND localUri IS NULL",
                batch.map { it as Any? }.toTypedArray()).use { rows ->
                while (rows.moveToNext()) result.add(rows.getString(0))
            }
        }
        return result
    }

    private fun plan(db: SupportSQLiteDatabase, cloud: CloudRestorePlan.Library): CloudRestorePlan.Plan {
        CloudRestorePlan.validate(cloud)
        val ids = (cloud.favorites + cloud.playlists.flatMap { it.tracks }).toSet()
        val favorites = mutableSetOf<String>()
        db.query("SELECT id FROM song WHERE liked=1").use { rows ->
            while (rows.moveToNext()) favorites.add(rows.getString(0))
        }
        val playlists = mutableMapOf<String, CloudRestorePlan.Playlist?>()
        for (item in cloud.playlists) {
            db.query("SELECT name,browseId,isEditable FROM playlist WHERE id=?", arrayOf<Any?>(item.id)).use { row ->
                if (row.moveToFirst()) {
                    if (!row.isNull(1) || row.getInt(2) == 0) {
                        playlists[item.id] = null
                    } else {
                        val tracks = mutableListOf<String>()
                        db.query("SELECT songId FROM playlist_song_map WHERE playlistId=? ORDER BY position,id",
                            arrayOf<Any?>(item.id)).use { songs ->
                            while (songs.moveToNext()) tracks.add(songs.getString(0))
                        }
                        playlists[item.id] = CloudRestorePlan.Playlist(item.id, row.getString(0), tracks)
                    }
                }
            }
        }
        return CloudRestorePlan.build(cloud, favorites, playlists, eligible(db, ids))
    }

    suspend fun preview(database: MusicDatabase, cloud: CloudRestorePlan.Library): CloudRestorePlan.Plan =
        withContext(Dispatchers.IO) {
            val db = database.openHelper.writableDatabase
            db.beginTransactionNonExclusive()
            try {
                plan(db, cloud).also { db.setTransactionSuccessful() }
            } finally { db.endTransaction() }
        }

    /** Caller passes the exact plan approved by the user. Recompute under the
     * Room write transaction to reject concurrent changes before writing.
     */
    suspend fun apply(database: MusicDatabase, cloud: CloudRestorePlan.Library,
                      approved: CloudRestorePlan.Plan, confirmed: Boolean) {
        require(confirmed && approved.ready)
        database.withTransaction {
            val db = openHelper.writableDatabase
            val current = plan(db, cloud)
            check(current == approved && current.ready) { "Library changed; preview again" }
            val now = LocalDateTime.now()
            // Existing eligible songs only, and never remove current favorites.
            for (id in current.addFavorites) {
                // Room's time converter uses UTC epoch milliseconds.
                val epoch = now.toInstant(java.time.ZoneOffset.UTC).toEpochMilli()
                db.execSQL("UPDATE song SET liked=1,likedDate=? WHERE id=? AND liked=0", arrayOf<Any?>(epoch,id))
            }
            for (playlist in current.addPlaylists) {
                insert(PlaylistEntity(id=playlist.id, name=playlist.name, bookmarkedAt=now, isLocal=true))
                for ((position, id) in playlist.tracks.withIndex()) {
                    insert(PlaylistSongMap(playlistId=playlist.id, songId=id, position=position))
                }
            }
        }
    }
}
