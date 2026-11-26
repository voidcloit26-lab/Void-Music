package com.mochyy.mochymusic.guardian

/** A conservative metadata sync decision. The adapter must persist baseline
 * only after a confirmed upload/restore and bind it to the current account.
 * Automatic deletion, conflict merging and first uploads require review.
 */
internal object CloudSyncPolicy {
    private val accountPattern = Regex("[a-f0-9]{32}")
    private val digestPattern = Regex("[a-f0-9]{64}")
    data class Baseline(val account: String, val revision: Long, val digest: String)
    data class Remote(val revision: Long, val digest: String?)
    enum class Action { DISABLED, REVIEW_FIRST_SYNC, REVIEW_REMOTE_CHANGE, REVIEW_DELETION,
        REVIEW_EXCLUSIONS, UPLOAD, CURRENT }

    fun decide(account: String, enabled: Boolean, baseline: Baseline?, remote: Remote,
               localDigest: String, excludedEntries: Int, additiveOnly: Boolean): Action {
        require(accountPattern.matches(account) && digestPattern.matches(localDigest))
        require(remote.revision >= 0 && (remote.revision == 0L) == (remote.digest == null))
        require(remote.digest == null || digestPattern.matches(remote.digest))
        require(excludedEntries >= 0)
        if (!enabled) return Action.DISABLED
        if (baseline == null || baseline.account != account) return Action.REVIEW_FIRST_SYNC
        require(baseline.revision > 0 && digestPattern.matches(baseline.digest))
        if (remote.revision != baseline.revision || remote.digest != baseline.digest) return Action.REVIEW_REMOTE_CHANGE
        if (localDigest == baseline.digest) return Action.CURRENT
        if (excludedEntries != 0) return Action.REVIEW_EXCLUSIONS
        if (!additiveOnly) return Action.REVIEW_DELETION
        return Action.UPLOAD
    }
}
