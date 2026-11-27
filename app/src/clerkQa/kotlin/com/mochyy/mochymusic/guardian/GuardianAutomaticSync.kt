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

/** Process/session-only consent; no background scheduler, credential persistence,
 * implicit first backup, automatic restore, deletion or retry after a conflict. */
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
        val stillCurrent: () -> Boolean
    )
    private val lock = Any()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val state = MutableStateFlow(Status.DISABLED)
    val status = state.asStateFlow()
    private var generation = 0L
    private var configuration: Configuration? = null
    private var job: Job? = null

    suspend fun enable(account: String, cloud: Port, stillCurrent: () -> Boolean): Boolean =
        withContext(Dispatchers.IO) {
            val started = synchronized(lock) {
                check(configuration == null && job?.isCompleted != false)
                generation
            }
            check(stillCurrent())
            val baseline = cloud.prepareAutomatic(account)
            synchronized(lock) {
                if (generation != started || !stillCurrent() || configuration != null) return@synchronized false
                configuration = Configuration(account, cloud, baseline, stillCurrent)
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
                    synchronized(lock) {
                        if (configuration === selected) {
                            if (selected.stillCurrent()) {
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
                } catch (_: Exception) {
                    synchronized(lock) {
                        if (configuration === selected) {
                            configuration = null
                            state.value = Status.REVIEW_REQUIRED
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
