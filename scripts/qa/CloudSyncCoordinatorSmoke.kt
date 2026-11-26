package com.mochyy.mochymusic.guardian

import kotlinx.coroutines.runBlocking

fun main() = runBlocking {
    val a = CloudSyncCoordinator.Binding("a".repeat(32), "user_a", "sess_a")
    val b = CloudSyncCoordinator.Binding("b".repeat(32), "user_b", "sess_b")
    fun body(vararg ids: String): Map<String, Any?> = mapOf("favorites" to ids.toList(), "playlists" to emptyList<Any>(), "preferences" to emptyMap<String,Any>())
    val old = body("a".repeat(11))
    val added = body("a".repeat(11),"b".repeat(11))
    class Fake : CloudSyncCoordinator.Port {
        var account = a
        var consent = true
        var base: CloudSyncPolicy.Baseline? = CloudSyncPolicy.Baseline(a.account, 4, CloudMetadata.parse(old).digest())
        var local: CloudSyncCoordinator.Local? = CloudSyncCoordinator.Local(a,added,0)
        var remote = CloudSyncCoordinator.Remote(4,old)
        var switchOnRead = false
        var switchOnWrite = false
        var loseResponse = false
        var ack = 5L
        var writes = 0
        var saves = 0
        override suspend fun current() = account
        override suspend fun enabled(binding: CloudSyncCoordinator.Binding) = consent
        override suspend fun baseline(binding: CloudSyncCoordinator.Binding) = base
        override suspend fun capture(binding: CloudSyncCoordinator.Binding) = local
        override suspend fun read(binding: CloudSyncCoordinator.Binding): CloudSyncCoordinator.Remote {
            if (switchOnRead) account = b
            return remote
        }
        override suspend fun write(binding: CloudSyncCoordinator.Binding, revision: Long, body: Map<String,Any?>): Long {
            check(binding == a && revision == 4L && body == added)
            writes++
            if (switchOnWrite) account = b
            if (loseResponse) error("Response lost")
            return ack
        }
        override suspend fun saveIfCurrent(binding: CloudSyncCoordinator.Binding, baseline: CloudSyncPolicy.Baseline): Boolean {
            if (binding != account) return false
            saves++; base = baseline; return true
        }
    }
    var checks = 0
    suspend fun test(setup: Fake.()->Unit, expected: CloudSyncCoordinator.Result, writes: Int=0, saves: Int=0) {
        val f = Fake().apply(setup)
        check(CloudSyncCoordinator(f).sync() == expected && f.writes == writes && f.saves == saves)
        checks++
    }
    test({}, CloudSyncCoordinator.Result.UPLOADED,1,1)
    test({consent=false},CloudSyncCoordinator.Result.DISABLED)
    test({base=null},CloudSyncCoordinator.Result.REVIEW)
    test({local=null},CloudSyncCoordinator.Result.REVIEW)
    test({local=local!!.copy(owner=b)},CloudSyncCoordinator.Result.ACCOUNT_CHANGED)
    test({switchOnRead=true},CloudSyncCoordinator.Result.ACCOUNT_CHANGED)
    test({switchOnWrite=true},CloudSyncCoordinator.Result.ACCOUNT_CHANGED,1)
    test({remote=remote.copy(revision=5)},CloudSyncCoordinator.Result.REVIEW)
    test({local=local!!.copy(excluded=1)},CloudSyncCoordinator.Result.REVIEW)
    test({local=local!!.copy(body=old)},CloudSyncCoordinator.Result.CURRENT)
    for (setup in listOf<Fake.()->Unit>({ack=4},{loseResponse=true})) {
        val f=Fake().apply(setup)
        check(runCatching { CloudSyncCoordinator(f).sync() }.isFailure && f.writes==1 && f.saves==0)
        checks++
    }
    println("Cloud sync coordinator: $checks checks passed")
}
