package com.mochyy.mochymusic.guardian

import com.mochyy.mochymusic.db.MusicDatabase
import org.json.JSONObject
import org.json.JSONArray

/** Explicit first backup only. No automatic upload, overwrite or restore.
 * Local storage is shared; consent must establish the user's ownership.
 */
internal class GuardianQaCloud(
    private val database: MusicDatabase,
    private val client: GuardianAccountClient,
    private val isCurrent: () -> Boolean
) {
    data class FirstBackup(val account: String, val preview: GuardianCloudSnapshot.Preview)
    data class UpdatePreview(val account: String, val revision: Long, val remoteDigest: String, val local: GuardianCloudSnapshot.Preview)
    data class RestorePreview(val account: String, val revision: Long, val library: CloudRestorePlan.Library, val plan: CloudRestorePlan.Plan)

    private suspend fun requireAccount(account: String, active: Boolean = false) {
        require(account.matches(Regex("[a-f0-9]{32}")))
        check(isCurrent())
        val status = client.request("status", emptyMap())
        check(isCurrent() && status.getString("account") == account)
        if (active) check(status.getString("status") == "active") { "Active membership required" }
    }

    suspend fun previewFirst(account: String): FirstBackup {
        requireAccount(account, active = true)
        val remote = client.request("cloud_read", emptyMap())
        check(remote.getLong("revision") == 0L && remote.isNull("library")) {
            "Existing backup must not be overwritten"
        }
        val local = GuardianCloudSnapshot.capture(database)
        check(isCurrent())
        return FirstBackup(account, local)
    }

    suspend fun confirmFirst(approved: FirstBackup, confirmed: Boolean): Long {
        require(confirmed)
        requireAccount(approved.account, active = true)
        val local = GuardianCloudSnapshot.capture(database)
        check(local == approved.preview && isCurrent()) { "Library changed; preview again" }
        // Compare-and-swap with revision zero prevents overwriting any existing backup,
        // including one created by a concurrent request after preview.
        val response = client.request("cloud_write", mapOf("revision" to 0L, "library" to local.body))
        check(isCurrent())
        return response.getLong("revision").also { check(it == 1L) }
    }

    suspend fun previewRestore(account: String): RestorePreview? {
        requireAccount(account)
        val remote = client.request("cloud_read", emptyMap())
        val revision = remote.getLong("revision")
        if (remote.isNull("library")) {
            check(revision == 0L)
            return null
        }
        require(revision > 0L)
        val library = GuardianCloudRestore.parse(remote.getJSONObject("library"))
        val plan = GuardianCloudRestore.preview(database, library)
        check(isCurrent())
        return RestorePreview(account, revision, library, plan)
    }

    suspend fun confirmRestore(approved: RestorePreview, confirmed: Boolean) {
        require(confirmed && approved.plan.ready)
        requireAccount(approved.account, active = true)
        val remote = client.request("cloud_read", emptyMap())
        check(remote.getLong("revision") == approved.revision && !remote.isNull("library"))
        val library = GuardianCloudRestore.parse(remote.getJSONObject("library"))
        check(library == approved.library && isCurrent()) { "Backup changed; preview again" }
        GuardianCloudRestore.apply(database, library, approved.plan, confirmed = true, stillCurrent = isCurrent)
    }

    private fun convert(value: Any?): Any? = when (value) {
        null, JSONObject.NULL -> null
        is JSONObject -> value.keys().asSequence().associateWith { convert(value.get(it)) }
        is JSONArray -> List(value.length()) { convert(value.get(it)) }
        is String, is Boolean, is Int, is Long -> value
        else -> throw IllegalArgumentException("Invalid backup metadata")
    }
    private fun remoteBody(remote: JSONObject): Map<String, Any?> =
        remote.getJSONObject("library").let { obj -> obj.keys().asSequence().associateWith { convert(obj.get(it)) } }

    /** Manual update only. Existing remote metadata is a strict lower bound. */
    suspend fun previewUpdate(account: String): UpdatePreview {
        requireAccount(account, active = true)
        val remote = client.request("cloud_read", emptyMap())
        val revision = remote.getLong("revision")
        require(revision > 0L && !remote.isNull("library"))
        val remoteMetadata = CloudMetadata.parse(remoteBody(remote))
        val local = GuardianCloudSnapshot.capture(database)
        val localMetadata = CloudMetadata.parse(local.body)
        check(local.excludedEntries == 0 && localMetadata.additiveTo(remoteMetadata)) {
            "Review library conflicts before backup"
        }
        check(localMetadata.digest() != remoteMetadata.digest()) { "Backup already current" }
        check(isCurrent())
        return UpdatePreview(account, revision, remoteMetadata.digest(), local)
    }

    suspend fun confirmUpdate(approved: UpdatePreview, confirmed: Boolean): Long {
        require(confirmed)
        val current = previewUpdate(approved.account)
        check(current == approved && isCurrent()) { "Library or backup changed; preview again" }
        val response = client.request("cloud_write",
            mapOf("revision" to approved.revision, "library" to approved.local.body))
        check(isCurrent())
        return response.getLong("revision").also { check(it == approved.revision + 1) }
    }
}
