package com.mochyy.mochymusic.guardian

fun main() {
    val account = "a".repeat(32); val other = "b".repeat(32)
    val a = "a".repeat(11); val b = "b".repeat(11)
    fun body(vararg tracks: String) = mapOf("favorites" to tracks.toList(), "playlists" to emptyList<Any>(), "preferences" to emptyMap<String,Any>())
    val remote = body(a)
    val local = body(a,b)
    val baseline = CloudSyncPolicy.Baseline(account, 4, CloudMetadata.parse(remote).digest())
    fun plan(enabled: Boolean = true, previous: CloudSyncPolicy.Baseline? = baseline, revision: Long = 4,
             server: Map<String,Any?>? = remote, device: Map<String,Any?> = local, excluded: Int = 0) =
        CloudSyncEvaluation.evaluate(account,enabled,previous,revision,server,device,excluded)
    var checks = 0
    fun verify(value: Boolean) { check(value); checks++ }
    val upload = plan()
    verify(upload.action == CloudSyncPolicy.Action.UPLOAD)
    verify(CloudSyncEvaluation.confirmed(account,upload,5).digest == CloudMetadata.parse(local).digest())
    verify(runCatching { CloudSyncEvaluation.confirmed(other,upload,5) }.isFailure)
    verify(runCatching { CloudSyncEvaluation.confirmed(account,upload,4) }.isFailure)
    verify(plan(enabled=false).action == CloudSyncPolicy.Action.DISABLED)
    verify(plan(previous=null).action == CloudSyncPolicy.Action.REVIEW_FIRST_SYNC)
    verify(plan(previous=baseline.copy(account=other)).action == CloudSyncPolicy.Action.REVIEW_FIRST_SYNC)
    verify(plan(revision=5).action == CloudSyncPolicy.Action.REVIEW_REMOTE_CHANGE)
    verify(plan(server=body(b)).action == CloudSyncPolicy.Action.REVIEW_REMOTE_CHANGE)
    verify(plan(device=body()).action == CloudSyncPolicy.Action.REVIEW_DELETION)
    verify(plan(excluded=1).action == CloudSyncPolicy.Action.REVIEW_EXCLUSIONS)
    verify(plan(device=remote).action == CloudSyncPolicy.Action.CURRENT)
    verify(runCatching { CloudSyncEvaluation.confirmed(account,plan(device=remote),5) }.isFailure)
    verify(plan(previous=null,revision=0,server=null).action == CloudSyncPolicy.Action.REVIEW_FIRST_SYNC)
    verify(runCatching { plan(revision=0,server=remote) }.isFailure)
    println("Cloud sync evaluation: $checks checks passed")
}
