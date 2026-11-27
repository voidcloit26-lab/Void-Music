package com.mochyy.mochymusic.guardian
import org.junit.Test

class AutomaticSyncPolicyTest {
    @Test fun additiveSyncRules() {
    val account = "a".repeat(32)
    val other = "b".repeat(32)
    val first = "abcdefghijk"
    val second = "lmnopqrstuv"
    fun snapshot(favorites: List<String> = listOf(first), tracks: List<String> = listOf(first), name: String = "Mix", prefs: Map<String, Any?> = mapOf("shuffle" to false)): Map<String, Any?> =
        mapOf("favorites" to favorites, "playlists" to listOf(mapOf("id" to "mix", "name" to name, "tracks" to tracks)), "preferences" to prefs)
    val remote = snapshot()
    val baseline = CloudSyncPolicy.Baseline(account, 7, CloudMetadata.parse(remote).digest())
    fun evaluate(local: Map<String, Any?>, enabled: Boolean = true, b: CloudSyncPolicy.Baseline? = baseline, revision: Long = 7, server: Map<String, Any?>? = remote, excluded: Int = 0) =
        CloudSyncEvaluation.evaluate(account, enabled, b, revision, server, local, excluded)
    val added = snapshot(listOf(first, second), listOf(first, second))
    check(evaluate(remote).action == CloudSyncPolicy.Action.CURRENT)
    check(evaluate(added).action == CloudSyncPolicy.Action.UPLOAD)
    check(evaluate(added, enabled = false).action == CloudSyncPolicy.Action.DISABLED)
    check(evaluate(added, b = null).action == CloudSyncPolicy.Action.REVIEW_FIRST_SYNC)
    check(evaluate(added, b = baseline.copy(account = other)).action == CloudSyncPolicy.Action.REVIEW_FIRST_SYNC)
    check(evaluate(added, revision = 8).action == CloudSyncPolicy.Action.REVIEW_REMOTE_CHANGE)
    check(evaluate(added, server = snapshot(name = "Changed")).action == CloudSyncPolicy.Action.REVIEW_REMOTE_CHANGE)
    check(evaluate(added, excluded = 1).action == CloudSyncPolicy.Action.REVIEW_EXCLUSIONS)
    check(evaluate(snapshot(favorites = emptyList())).action == CloudSyncPolicy.Action.REVIEW_DELETION)
    check(evaluate(snapshot(tracks = emptyList())).action == CloudSyncPolicy.Action.REVIEW_DELETION)
    check(evaluate(snapshot(name = "Renamed")).action == CloudSyncPolicy.Action.REVIEW_DELETION)
    check(evaluate(snapshot(tracks = listOf(second, first))).action == CloudSyncPolicy.Action.REVIEW_DELETION)
    check(evaluate(snapshot(prefs = mapOf("shuffle" to true))).action == CloudSyncPolicy.Action.REVIEW_DELETION)
    val upload = evaluate(added)
    check(CloudSyncEvaluation.confirmed(account, upload, 8) == CloudSyncPolicy.Baseline(account, 8, CloudMetadata.parse(added).digest()))
    check(runCatching { CloudSyncEvaluation.confirmed(account, upload, 9) }.isFailure)
    check(runCatching { CloudSyncEvaluation.confirmed(other, upload, 8) }.isFailure)
    check(runCatching { CloudSyncEvaluation.confirmed(account, evaluate(remote), 8) }.isFailure)
    check(runCatching { evaluate(snapshot(favorites = listOf(first, first))) }.isFailure)
    }

}
