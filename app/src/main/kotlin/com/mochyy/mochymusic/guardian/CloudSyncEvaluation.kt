package com.mochyy.mochymusic.guardian

/** Derives the sync decision from actual snapshots, not a caller-asserted
 * additive flag or an untrusted remote digest. No I/O or implicit consent. */
internal object CloudSyncEvaluation {
    data class Evaluation(val account: String, val action: CloudSyncPolicy.Action, val revision: Long, val localDigest: String)

    fun evaluate(account: String, enabled: Boolean, baseline: CloudSyncPolicy.Baseline?,
                 remoteRevision: Long, remoteBody: Map<String, Any?>?, localBody: Map<String, Any?>,
                 excludedEntries: Int): Evaluation {
        val local = CloudMetadata.parse(localBody)
        val remote = remoteBody?.let { CloudMetadata.parse(it) }
        val digest = local.digest()
        val action = CloudSyncPolicy.decide(account, enabled, baseline,
            CloudSyncPolicy.Remote(remoteRevision, remote?.digest()), digest, excludedEntries,
            remote != null && local.additiveTo(remote))
        return Evaluation(account, action, remoteRevision, digest)
    }

    /** Called only after a successful CAS write with the exact evaluated body.
     * No baseline advance on conflict, missing response, or wrong revision. */
    fun confirmed(account: String, evaluation: Evaluation, acknowledgedRevision: Long): CloudSyncPolicy.Baseline {
        require(account.matches(Regex("[a-f0-9]{32}")))
        require(account == evaluation.account)
        require(evaluation.action == CloudSyncPolicy.Action.UPLOAD)
        require(evaluation.revision in 1 until Long.MAX_VALUE && acknowledgedRevision == evaluation.revision + 1)
        require(evaluation.localDigest.matches(Regex("[a-f0-9]{64}")))
        return CloudSyncPolicy.Baseline(account, acknowledgedRevision, evaluation.localDigest)
    }
}
