package com.mochyy.mochymusic.guardian

import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.first

fun main() = runBlocking {
    val sync = GuardianAutomaticSync
    val account = "a".repeat(32)
    val other = "b".repeat(32)
    val base = CloudSyncPolicy.Baseline(account, 1, "a".repeat(64))
    val calls = AtomicInteger(0)
    val started = CompletableDeferred<Unit>()
    val release = CompletableDeferred<Unit>()
    val port = object : GuardianAutomaticSync.Port {
        override suspend fun prepareAutomatic(account: String) = base
        override suspend fun automaticPass(account: String, baseline: CloudSyncPolicy.Baseline): CloudSyncPolicy.Baseline {
            check(account == base.account)
            return when (calls.incrementAndGet()) {
                1 -> { check(baseline == base); started.complete(Unit); release.await(); base.copy(revision = 2) }
                else -> { check(baseline.revision == 2L); error("Conflict") }
            }
        }
    }
    try {
        sync.disable()
        check(sync.status.value == GuardianAutomaticSync.Status.DISABLED)
        check(runCatching { sync.enable(account, port) { false } }.isFailure)
        check(runCatching { sync.enable(other, port) { true } }.isFailure)
        check(sync.enable(account, port) { true })
        check(sync.status.value == GuardianAutomaticSync.Status.ENABLED)
        sync.schedule(other)
        check(sync.status.value == GuardianAutomaticSync.Status.ENABLED)
        sync.schedule(account)
        withTimeout(5000) { started.await() }
        check(sync.status.value == GuardianAutomaticSync.Status.SYNCING)
        repeat(10) { sync.schedule(account) }
        check(calls.get() == 1)
        release.complete(Unit)
        withTimeout(5000) { sync.status.first { it == GuardianAutomaticSync.Status.ENABLED } }
        withTimeout(5000) { while (sync.status.value == GuardianAutomaticSync.Status.ENABLED) { sync.schedule(account); delay(5) } }
        withTimeout(5000) { sync.status.first { it == GuardianAutomaticSync.Status.REVIEW_REQUIRED } }
        check(calls.get() == 2)
        sync.schedule(account)
        check(sync.status.value == GuardianAutomaticSync.Status.REVIEW_REQUIRED)
        sync.disable()
        check(sync.status.value == GuardianAutomaticSync.Status.DISABLED)
        println("PASS: automatic sync lifecycle; consent, owner, single-flight, baseline, conflict pause, disable")
    } finally { sync.disable(); release.complete(Unit) }
}
