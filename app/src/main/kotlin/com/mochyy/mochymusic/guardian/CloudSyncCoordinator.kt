package com.mochyy.mochymusic.guardian

import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/** One opt-in sync pass. The adapter must prove local library ownership, bind
 * transport to the same session, and atomically persist only acknowledged state.
 * No automatic retry, restore, delete, or first upload. */
internal class CloudSyncCoordinator(private val io: Port) {
    data class Binding(val account: String, val subject: String, val session: String)
    data class Remote(val revision: Long, val body: Map<String, Any?>?)
    data class Local(val owner: Binding, val body: Map<String, Any?>, val excluded: Int)
    interface Port {
        suspend fun current(): Binding?
        suspend fun enabled(binding: Binding): Boolean
        suspend fun baseline(binding: Binding): CloudSyncPolicy.Baseline?
        suspend fun capture(binding: Binding): Local?
        suspend fun read(binding: Binding): Remote
        suspend fun write(binding: Binding, revision: Long, body: Map<String, Any?>): Long
        // Adapter performs an atomic compare against the current binding before saving.
        suspend fun saveIfCurrent(binding: Binding, baseline: CloudSyncPolicy.Baseline): Boolean
    }
    enum class Result { DISABLED, ACCOUNT_CHANGED, REVIEW, CURRENT, UPLOADED }
    private val lock = Mutex()

    suspend fun sync(): Result = lock.withLock {
        val binding = io.current() ?: return@withLock Result.DISABLED
        if (!io.enabled(binding)) return@withLock Result.DISABLED
        val baseline = io.baseline(binding)
        if (baseline == null || baseline.account != binding.account) return@withLock Result.REVIEW
        val local = io.capture(binding) ?: return@withLock Result.REVIEW
        if (local.owner != binding || io.current() != binding) return@withLock Result.ACCOUNT_CHANGED
        // Snapshot nested mutable collections before evaluating and sending.
        val body = freeze(local.body)
        val remote = io.read(binding)
        if (io.current() != binding) return@withLock Result.ACCOUNT_CHANGED
        val evaluation = CloudSyncEvaluation.evaluate(binding.account, true, baseline,
            remote.revision, remote.body, body, local.excluded)
        when (evaluation.action) {
            CloudSyncPolicy.Action.CURRENT -> return@withLock Result.CURRENT
            CloudSyncPolicy.Action.UPLOAD -> Unit
            else -> return@withLock Result.REVIEW
        }
        if (io.current() != binding) return@withLock Result.ACCOUNT_CHANGED
        if (!io.enabled(binding)) return@withLock Result.DISABLED
        val ack = io.write(binding, evaluation.revision, body)
        val next = CloudSyncEvaluation.confirmed(binding.account, evaluation, ack)
        if (!io.saveIfCurrent(binding, next)) return@withLock Result.ACCOUNT_CHANGED
        Result.UPLOADED
    }

    private fun freeze(body: Map<String, Any?>): Map<String, Any?> = body.mapValues { copy(it.value) }
    private fun copy(value: Any?, depth: Int = 0): Any? {
        require(depth <= 8)
        return when (value) {
            null, is String, is Boolean, is Int, is Long -> value
            is List<*> -> value.map { copy(it, depth+1) }
            is Map<*, *> -> value.entries.associate { requireNotNull(it.key as? String) to copy(it.value, depth+1) }
            else -> throw IllegalArgumentException("Unsupported metadata")
        }
    }
}
