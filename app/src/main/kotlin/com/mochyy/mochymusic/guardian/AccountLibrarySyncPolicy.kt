package com.mochyy.mochymusic.guardian

/** Consent is established separately against a fully matched account snapshot.
 * Only a known remote revision can be replaced with a complete local snapshot. */
internal object AccountLibrarySyncPolicy {
    enum class Action { CURRENT, ALREADY_SAVED, UPLOAD, REVIEW }
    fun decide(baseline: CloudSyncPolicy.Baseline, revision: Long,
               remoteDigest: String, localDigest: String, excluded: Int): Action {
        val digest = Regex("[a-f0-9]{64}")
        require(baseline.account.matches(Regex("[a-f0-9]{32}")))
        require(baseline.revision in 1 until Long.MAX_VALUE && revision in 1 until Long.MAX_VALUE)
        require(digest.matches(baseline.digest) && digest.matches(remoteDigest) && digest.matches(localDigest))
        require(excluded >= 0)
        if (excluded != 0) return Action.REVIEW
        if (revision == baseline.revision && remoteDigest == baseline.digest) {
            return if (localDigest == remoteDigest) Action.CURRENT else Action.UPLOAD
        }
        // A lost response is safely reconciled only if the current complete
        // local snapshot is exactly the one now stored on the server.
        if (revision == baseline.revision + 1 && remoteDigest == localDigest)
            return Action.ALREADY_SAVED
        return Action.REVIEW
    }
}
