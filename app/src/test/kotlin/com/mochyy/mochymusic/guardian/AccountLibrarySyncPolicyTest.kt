package com.mochyy.mochymusic.guardian

import org.junit.Assert.assertEquals
import org.junit.Test

class AccountLibrarySyncPolicyTest {
    private val old = "a".repeat(64)
    private val next = "b".repeat(64)
    private val baseline = CloudSyncPolicy.Baseline("c".repeat(32), 8, old)
    private fun decide(revision: Long, remote: String, local: String, excluded: Int = 0, additive: Boolean = true) =
        AccountLibrarySyncPolicy.decide(baseline, revision, remote, local, excluded, additive)

    @Test fun unchangedIsCurrent() {
        assertEquals(AccountLibrarySyncPolicy.Action.CURRENT, decide(8, old, old))
    }
    @Test fun knownRevisionPermitsLocalEdit() {
        assertEquals(AccountLibrarySyncPolicy.Action.UPLOAD, decide(8, old, next))
    }
    @Test fun destructiveSnapshotRequiresReview() {
        assertEquals(AccountLibrarySyncPolicy.Action.REVIEW, decide(8, old, next, additive = false))
    }
    @Test fun incompleteSnapshotNeverUploads() {
        assertEquals(AccountLibrarySyncPolicy.Action.REVIEW, decide(8, old, next, 1))
    }
    @Test fun changedRemoteRequiresReview() {
        assertEquals(AccountLibrarySyncPolicy.Action.REVIEW, decide(9, next, old))
    }
    @Test fun exactLostResponseMayBeAcknowledged() {
        assertEquals(AccountLibrarySyncPolicy.Action.ALREADY_SAVED, decide(9, next, next))
    }
    @Test fun multipleUnseenRevisionsRequireReview() {
        assertEquals(AccountLibrarySyncPolicy.Action.REVIEW, decide(10, next, next))
    }
}
