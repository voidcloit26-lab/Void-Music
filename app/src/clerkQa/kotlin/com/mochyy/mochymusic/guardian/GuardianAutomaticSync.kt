package com.mochyy.mochymusic.guardian

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Account-scoped consent and acknowledged baselines are supplied by the runtime.
 * No background credential persistence, automatic deletion or retry after a conflict. */
internal object GuardianAutomaticSync {
    enum class Status { DISABLED, ENABLED, SYNCING, REVIEW_REQUIRED }
    interface Port {
        suspend fun prepareAutomatic(account: String): CloudSyncPolicy.Baseline
        suspend fun automaticPass(account: String, baseline: CloudSyncPolicy.Baseline): CloudSyncPolicy.Baseline
    }
    private data class Configuration(
        val account: String,
        val cloud: Port,
        val baseline: CloudSyncPolicy.Baseline,
        val stillCurrent: () -> Boolean,
        val onBaseline: (CloudSyncPolicy.Baseline) -> Unit,
        val onReview: () -> Unit
    )
    private val lock = Any()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val state = MutableStateFlow(Status.DISABLED)
    val status = state.asStateFlow()
    private var generation = 0L
    private var configuration: Configuration? = null
    private var job: Job? = null

    suspend fun enable(account: String, cloud: Port, stillCurrent: () -> Boolean,
                       resume: CloudSyncPolicy.Baseline? = null,
                       onBaseline: (CloudSyncPolicy.Baseline) -> Unit = {},
                       onReview: () -> Unit = {}): Boolean =
        withContext(Dispatchers.IO) {
            val started = synchronized(lock) {
                check(configuration == null && job?.isCompleted != false)
                generation
            }
            check(stillCurrent())
            val baseline = resume ?: cloud.prepareAutomatic(account)
            require(baseline.account == account && baseline.revision in 1 until Long.MAX_VALUE &&
                baseline.digest.matches(Regex("[a-f0-9]{64}")))
            synchronized(lock) {
                if (generation != started || !stillCurrent() || configuration != null) return@synchronized false
                onBaseline(baseline)
                configuration = Configuration(account, cloud, baseline, stillCurrent, onBaseline, onReview)
                state.value = Status.ENABLED
                true
            }
        }

    fun disable() {
        synchronized(lock) {
            generation++
            configuration = null
            job?.cancel()
            // A cancelled blocking transport may still be unwinding. Retain its job
            // until completion so a subsequent session cannot overlap it.
            state.value = Status.DISABLED
        }
    }

    /** Called only from the existing successful online membership refresh. */
    fun schedule(account: String) {
        synchronized(lock) {
            val selected = configuration ?: return
            if (selected.account != account || job?.isCompleted == false) return
            val next = scope.launch(start = CoroutineStart.LAZY) {
                try {
                    check(selected.stillCurrent())
                    val updated = selected.cloud.automaticPass(account, selected.baseline)
                    check(updated.account == account && updated.digest.matches(Regex("[a-f0-9]{64}")))
                    check(updated == selected.baseline || updated.revision == selected.baseline.revision + 1)
                    synchronized(lock) {
                        if (configuration === selected) {
                            if (selected.stillCurrent()) {
                                selected.onBaseline(updated)
                                configuration = selected.copy(baseline = updated)
                                state.value = Status.ENABLED
                            } else {
                                configuration = null
                                state.value = Status.DISABLED
                            }
                        }
                    }
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    synchronized(lock) {
                        if (configuration === selected) {
                            val retryable = e is java.io.IOException ||
                                (e is GuardianAccountClient.RequestFailed && (e.status == 429 || e.status in 500..599))
                            if (retryable && selected.stillCurrent()) {
                                // The next successful membership refresh can retry safely.
                                // CAS and digest checks still reject ambiguous/conflicting writes.
                                state.value = Status.ENABLED
                            } else {
                                configuration = null
                                runCatching { selected.onReview() }
                                state.value = Status.REVIEW_REQUIRED
                            }
                        }
                    }
                }
            }
            job = next
            state.value = Status.SYNCING
            next.start()
        }
    }
}
