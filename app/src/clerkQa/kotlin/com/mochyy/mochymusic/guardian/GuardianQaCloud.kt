package com.mochyy.mochymusic.guardian

import com.mochyy.mochymusic.db.MusicDatabase

/** Explicit first backup only. No automatic upload, overwrite or restore.
 * Local storage is shared; consent must establish the user's ownership.
 */
internal class GuardianQaCloud(
    private val database: MusicDatabase,
    private val client: GuardianAccountClient,
    private val isCurrent: () -> Boolean
) {
    data class FirstBackup(val account: String, val preview: GuardianCloudSnapshot.Preview)
    data class RestorePreview(val revision: Long, val plan: CloudRestorePlan.Plan)

    private suspend fun requireAccount(account: String) {
        require(account.matches(Regex("[a-f0-9]{32}")))
        check(isCurrent())
        val status = client.request("status", emptyMap())
        check(isCurrent() && status.getString("account") == account)
    }

    suspend fun previewFirst(account: String): FirstBackup {
        requireAccount(account)
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
        requireAccount(approved.account)
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
        val plan = GuardianCloudRestore.preview(database,
            GuardianCloudRestore.parse(remote.getJSONObject("library")))
        check(isCurrent())
        return RestorePreview(revision, plan)
    }
}
