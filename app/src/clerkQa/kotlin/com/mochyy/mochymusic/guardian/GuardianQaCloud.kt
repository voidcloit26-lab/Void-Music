package com.mochyy.mochymusic.guardian

import android.content.Context
import androidx.datastore.preferences.core.edit
import com.mochyy.mochymusic.constants.RepeatModeKey
import com.mochyy.mochymusic.constants.ShuffleModeKey
import com.mochyy.mochymusic.constants.RememberShuffleAndRepeatKey
import com.mochyy.mochymusic.utils.dataStore
import kotlinx.coroutines.flow.first
import com.mochyy.mochymusic.db.MusicDatabase
import org.json.JSONObject
import org.json.JSONArray

/** Explicit first backup only. No automatic upload, overwrite or restore.
 * Local storage is shared; consent must establish the user's ownership.
 */
internal class GuardianQaCloud(
    context: Context,
    private val database: MusicDatabase,
    private val client: GuardianAccountClient,
    private val ownsLibrary: (String) -> Boolean,
    private val isCurrent: () -> Boolean
) : GuardianAutomaticSync.Port {
    private val settings = context.applicationContext.dataStore
    data class UpgradeBackup(val account: String, val revision: Long, val snapshot: GuardianCloudSnapshot.Preview)
    data class UpgradeReceipt(val revision: Long, val recovery: String)

    suspend fun previewUpgradeBackup(account: String): UpgradeBackup {
        requireAccount(account, active = true)
        val remote = client.request("cloud_read", emptyMap())
        val revision = remote.getLong("revision")
        require(revision >= 0L && (remote.isNull("library") == (revision == 0L)))
        val preferences = if (revision == 0L) emptyMap() else prefsOf(remoteBody(remote))
        val snapshot = GuardianCloudSnapshot.capture(database, preferences)
        check(isCurrent() && ownsLibrary(account))
        return UpgradeBackup(account, revision, snapshot)
    }

    suspend fun confirmUpgradeBackup(approved: UpgradeBackup): UpgradeReceipt {
        requireAccount(approved.account, active = true)
        check(previewUpgradeBackup(approved.account) == approved) { "Library changed; review again" }
        check(isCurrent() && ownsLibrary(approved.account))
        val reply = client.request("backup_for_upgrade", mapOf("revision" to approved.revision, "library" to approved.snapshot.body))
        check(isCurrent() && ownsLibrary(approved.account))
        val revision = reply.getLong("revision")
        val recovery = reply.getString("recovery")
        require(revision > 0L && revision in approved.revision..(approved.revision + 1))
        require(Regex("[A-Za-z0-9_-]{43}").matches(recovery))
        return UpgradeReceipt(revision, recovery)
    }

    data class FirstBackup(val account: String, val preview: GuardianCloudSnapshot.Preview)
    data class UpdatePreview(val account: String, val revision: Long, val remoteDigest: String, val local: GuardianCloudSnapshot.Preview)
    data class RestorePreview(val account: String, val revision: Long, val library: CloudRestorePlan.Library, val plan: CloudRestorePlan.Plan)

    private suspend fun requireAccount(account: String, active: Boolean = false) {
        require(account.matches(Regex("[a-f0-9]{32}")))
        check(isCurrent() && ownsLibrary(account)) { "Local library owner mismatch" }
        val status = client.request("status", emptyMap())
        check(isCurrent() && ownsLibrary(account) && status.getString("account") == account)
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
        val existing = remoteBody(remote)
        val remoteMetadata = CloudMetadata.parse(existing)
        // Preserve validated remote preferences unchanged during a music-only update.
        // The device preferences are shared; do not upload or apply them automatically.
        val rawPreferences = requireNotNull(existing["preferences"] as? Map<*, *>)
        val remotePreferences = rawPreferences.entries.associate { (key, value) ->
            requireNotNull(key as? String) to value
        }
        val local = GuardianCloudSnapshot.capture(database, preferences = remotePreferences)
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

    data class PreferencePreview(val account: String, val revision: Long, val digest: String,
        val local: GuardianPlaybackPreferences.Saved, val remote: GuardianPlaybackPreferences.Saved?)

    private suspend fun savedPlayback(): GuardianPlaybackPreferences.Saved {
        val prefs = settings.data.first()
        return GuardianPlaybackPreferences.capture(prefs[RepeatModeKey] ?: 0, prefs[ShuffleModeKey] ?: false)
    }

    private fun prefsOf(body: Map<String, Any?>): Map<String, Any?> =
        requireNotNull(body["preferences"] as? Map<*, *>).entries.associate { (key, value) ->
            requireNotNull(key as? String) to value
        }

    suspend fun previewPreferences(account: String): PreferencePreview {
        requireAccount(account, active = true)
        val remote = client.request("cloud_read", emptyMap())
        val revision = remote.getLong("revision")
        require(revision > 0L && !remote.isNull("library")) { "Create a library backup first" }
        val body = remoteBody(remote)
        val digest = CloudMetadata.parse(body).digest()
        val local = savedPlayback()
        check(isCurrent() && ownsLibrary(account))
        return PreferencePreview(account, revision, digest, local,
            GuardianPlaybackPreferences.read(prefsOf(body)))
    }

    suspend fun savePreferences(approved: PreferencePreview, confirmed: Boolean): Long {
        require(confirmed)
        check(previewPreferences(approved.account) == approved) { "Settings or backup changed; preview again" }
        val remote = client.request("cloud_read", emptyMap())
        check(remote.getLong("revision") == approved.revision && !remote.isNull("library"))
        val body = remoteBody(remote)
        check(CloudMetadata.parse(body).digest() == approved.digest)
        val next = body + ("preferences" to GuardianPlaybackPreferences.merge(prefsOf(body), approved.local))
        CloudMetadata.parse(next)
        check(isCurrent() && ownsLibrary(approved.account) && savedPlayback() == approved.local)
        val response = client.request("cloud_write", mapOf("revision" to approved.revision, "library" to next))
        check(isCurrent() && ownsLibrary(approved.account))
        return response.getLong("revision").also { check(it == approved.revision + 1) }
    }

    suspend fun restorePreferences(approved: PreferencePreview, confirmed: Boolean) {
        require(confirmed)
        val remote = requireNotNull(approved.remote)
        check(previewPreferences(approved.account) == approved) { "Settings or backup changed; preview again" }
        settings.edit { prefs ->
            check(isCurrent() && ownsLibrary(approved.account))
            check(GuardianPlaybackPreferences.capture(prefs[RepeatModeKey] ?: 0, prefs[ShuffleModeKey] ?: false) == approved.local)
            prefs[RepeatModeKey] = remote.repeatMode()
            prefs[ShuffleModeKey] = remote.shuffle
            prefs[RememberShuffleAndRepeatKey] = true
            check(isCurrent() && ownsLibrary(approved.account))
        }
    }

    /** Opt-in only after an exact, fully eligible local/remote match.
     * No implicit initial upload, restore, deletion or preference changes. */
    override suspend fun prepareAutomatic(account: String): CloudSyncPolicy.Baseline {
        requireAccount(account, active = true)
        val remote = client.request("cloud_read", emptyMap())
        val revision = remote.getLong("revision")
        require(revision in 1 until Long.MAX_VALUE && !remote.isNull("library")) { "Review a manual backup first" }
        val body = remoteBody(remote)
        val digest = CloudMetadata.parse(body).digest()
        val local = GuardianCloudSnapshot.capture(database, preferences = prefsOf(body))
        check(local.excludedEntries == 0 && CloudMetadata.parse(local.body).digest() == digest) {
            "Local and cloud libraries must match before enabling sync"
        }
        check(isCurrent() && ownsLibrary(account))
        return CloudSyncPolicy.Baseline(account, revision, digest)
    }

    override suspend fun automaticPass(account: String, baseline: CloudSyncPolicy.Baseline): CloudSyncPolicy.Baseline {
        requireAccount(account, active = true)
        check(baseline.account == account)
        val remote = client.request("cloud_read", emptyMap())
        val revision = remote.getLong("revision")
        require(revision in 1 until Long.MAX_VALUE && !remote.isNull("library"))
        val body = remoteBody(remote)
        val local = GuardianCloudSnapshot.capture(database, preferences = prefsOf(body))
        val evaluation = CloudSyncEvaluation.evaluate(account, true, baseline, revision, body,
            local.body, local.excludedEntries)
        check(isCurrent() && ownsLibrary(account))
        return when (evaluation.action) {
            CloudSyncPolicy.Action.CURRENT -> baseline
            CloudSyncPolicy.Action.UPLOAD -> {
                // Reject a concurrent local mutation before issuing a single CAS write.
                check(GuardianCloudSnapshot.capture(database, preferences = prefsOf(body)) == local)
                check(isCurrent() && ownsLibrary(account))
                val response = client.request("cloud_write", mapOf("revision" to revision, "library" to local.body))
                check(isCurrent() && ownsLibrary(account))
                CloudSyncEvaluation.confirmed(account, evaluation, response.getLong("revision"))
            }
            else -> error("Library changed; manual review required")
        }
    }
}
