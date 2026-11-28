package com.mochyy.mochymusic.guardian

import com.mochyy.mochymusic.db.MusicDatabase
import org.json.JSONArray
import org.json.JSONObject

/** Explicit, reviewed extended-metadata requests. No automatic upload or
 * restore. Keep this adapter separate from V2 automatic playlist backup. */
internal class GuardianExtendedLibraryCloud(
    private val database: MusicDatabase,
    private val client: GuardianAccountClient,
    private val ownsLibrary: (String) -> Boolean,
    private val isCurrent: () -> Boolean,
) {
    data class Remote(val account: String, val revision: Long, val snapshot: ExtendedLibraryV1.Snapshot?)
    data class WritePreview(val remote: Remote, val local: GuardianExtendedLibrarySnapshot.Preview,
                            val includesHistory: Boolean)
    enum class ClearScope { HISTORY_ONLY, ALL_EXTENDED_METADATA }
    data class ClearPreview(val remote: Remote, val scope: ClearScope)

    private suspend fun requireAccount(account: String, active: Boolean = false, local: Boolean = false) {
        require(account.matches(Regex("[a-f0-9]{32}")))
        check(isCurrent() && (!local || ownsLibrary(account)))
        val status = client.request("status", emptyMap())
        check(isCurrent() && status.getString("account") == account && (!local || ownsLibrary(account)))
        if (active) check(status.getString("status") == "active")
    }

    private fun convert(value: Any?): Any? = when (value) {
        null, JSONObject.NULL -> null
        is JSONObject -> value.keys().asSequence().associateWith { convert(value.get(it)) }
        is JSONArray -> List(value.length()) { convert(value.get(it)) }
        is String, is Boolean, is Int, is Long -> value
        else -> error("Invalid extended metadata")
    }

    private suspend fun read(account: String): Remote {
        val response = client.request("extended_read", emptyMap())
        check(isCurrent())
        require(response.keys().asSequence().toSet() == setOf("revision", "library"))
        val revision = response.getLong("revision")
        require(revision in 0 until Long.MAX_VALUE)
        check(response.isNull("library") == (revision == 0L))
        val snapshot = if (revision == 0L) null else {
            val body = response.getJSONObject("library")
            ExtendedLibraryV1.parse(body.keys().asSequence().associateWith { convert(body.get(it)) })
        }
        return Remote(account, revision, snapshot)
    }

    suspend fun inspect(account: String): Remote {
        requireAccount(account)
        return read(account)
    }

    suspend fun previewWrite(account: String, includeHistory: Boolean): WritePreview {
        requireAccount(account, active = true, local = true)
        val remote = read(account)
        val local = GuardianExtendedLibrarySnapshot.capture(database, includeHistory) {
            isCurrent() && ownsLibrary(account)
        }
        // A partial capture cannot silently replace a complete remote snapshot.
        check(local.excludedAlbums == 0 && local.excludedArtists == 0 &&
            (!includeHistory || local.excludedHistory == 0)) { "Review excluded metadata before uploading" }
        check(isCurrent() && ownsLibrary(account))
        AccountProofV2.canonicalBody("extended_write",
            mapOf("revision" to remote.revision, "library" to ExtendedLibraryV1.body(local.snapshot)))
        return WritePreview(remote, local, includeHistory)
    }

    suspend fun confirmWrite(approved: WritePreview, confirmed: Boolean): Long {
        require(confirmed)
        val account = approved.remote.account
        check(previewWrite(account, approved.includesHistory) == approved) { "Library changed; review again" }
        check(isCurrent() && ownsLibrary(account))
        val response = client.request("extended_write", mapOf(
            "revision" to approved.remote.revision,
            "library" to ExtendedLibraryV1.body(approved.local.snapshot)))
        check(isCurrent() && ownsLibrary(account))
        require(response.keys().asSequence().toSet() == setOf("revision"))
        return response.getLong("revision").also {
            check(it > 0 && it in approved.remote.revision..(approved.remote.revision + 1))
        }
    }

    suspend fun previewClear(account: String, scope: ClearScope): ClearPreview? {
        val remote = inspect(account)
        if (remote.snapshot == null) return null
        if (scope == ClearScope.HISTORY_ONLY && remote.snapshot.history == null) return null
        return ClearPreview(remote, scope)
    }

    suspend fun confirmClear(approved: ClearPreview, confirmed: Boolean): Long {
        require(confirmed)
        check(previewClear(approved.remote.account, approved.scope) == approved && isCurrent()) {
            "Cloud metadata changed; review again"
        }
        val action = when (approved.scope) {
            ClearScope.HISTORY_ONLY -> "extended_history_clear"
            ClearScope.ALL_EXTENDED_METADATA -> "extended_clear"
        }
        val response = client.request(action, mapOf("revision" to approved.remote.revision))
        check(isCurrent())
        require(response.keys().asSequence().toSet() == setOf("revision"))
        return response.getLong("revision").also { check(it == approved.remote.revision + 1) }
    }
}
