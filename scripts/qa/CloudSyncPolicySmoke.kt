package com.mochyy.mochymusic.guardian

fun main() {
    val a = "a".repeat(32); val b = "b".repeat(32)
    val x = "c".repeat(64); val y = "d".repeat(64)
    val base = CloudSyncPolicy.Baseline(a, 1, x)
    val remote = CloudSyncPolicy.Remote(1, x)
    fun decide(account: String = a, enabled: Boolean = true, baseline: CloudSyncPolicy.Baseline? = base,
               r: CloudSyncPolicy.Remote = remote, local: String = y, excluded: Int = 0, additive: Boolean = true) =
        CloudSyncPolicy.decide(account, enabled, baseline, r, local, excluded, additive)
    check(decide(enabled = false) == CloudSyncPolicy.Action.DISABLED)
    check(decide(baseline = null) == CloudSyncPolicy.Action.REVIEW_FIRST_SYNC)
    check(decide(account = b) == CloudSyncPolicy.Action.REVIEW_FIRST_SYNC)
    check(decide(r = CloudSyncPolicy.Remote(2, x)) == CloudSyncPolicy.Action.REVIEW_REMOTE_CHANGE)
    check(decide(r = CloudSyncPolicy.Remote(1, y)) == CloudSyncPolicy.Action.REVIEW_REMOTE_CHANGE)
    check(decide(r = CloudSyncPolicy.Remote(0, null)) == CloudSyncPolicy.Action.REVIEW_REMOTE_CHANGE)
    check(decide(local = x) == CloudSyncPolicy.Action.CURRENT)
    check(decide(excluded = 1) == CloudSyncPolicy.Action.REVIEW_EXCLUSIONS)
    check(decide(additive = false) == CloudSyncPolicy.Action.REVIEW_DELETION)
    check(decide() == CloudSyncPolicy.Action.UPLOAD)
    check(runCatching { decide(r = CloudSyncPolicy.Remote(0, x)) }.isFailure)
    println("PASS: 11 cloud sync policy checks")
}
