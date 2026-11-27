package com.mochyy.mochymusic.guardian

import android.app.Activity
import android.content.Context
import android.content.Intent
import com.mochyy.mochymusic.BuildConfig
import android.os.SystemClock
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

/**
 * Explicitly enabled in staging builds only until all entry points are audited.
 * An enforced build with missing/invalid configuration must remain locked.
 */
object GuardianGate {
    val v2Enforced: Boolean get() = BuildConfig.VOID_GUARDIAN_V2_ENFORCED
    val enforced: Boolean get() = BuildConfig.VOID_GUARDIAN_ENFORCED || v2Enforced
    private val checkLock = Mutex()
    private var nextCheckAt = 0L
    private val revision = MutableStateFlow(0L)
    internal val changes = revision.asStateFlow()

    internal fun changed() { revision.update { it + 1 } }

    /**
     * Active UI and playback share one network budget. No background job is
     * scheduled outside the active process. Temporary errors preserve the receipt.
     */
    suspend fun watch(context: Context, onLocked: () -> Unit) {
        if (!enforced) return
        val app = context.applicationContext
        while (true) {
            if (!withContext(Dispatchers.IO) { isAllowed(app) }) {
                onLocked()
                return
            }
            checkLock.withLock {
                val now = SystemClock.elapsedRealtime()
                if (now >= nextCheckAt && !com.mochyy.mochymusic.utils.OfflineMode.isOn) {
                    nextCheckAt = now + 60_000L
                    val active = if (v2Enforced) GuardianV2Runtime.refresh(app) else client(app)?.refresh() == GuardianClient.Outcome.Active
                    if (active) {
                        nextCheckAt = SystemClock.elapsedRealtime() + 15 * 60_000L
                    }
                }
            }
            if (!withContext(Dispatchers.IO) { isAllowed(app) }) {
                onLocked()
                return
            }
            delay(5_000L)
        }
    }

    fun isAllowed(context: Context): Boolean =
        if (v2Enforced) GuardianV2Runtime.allowed(context.applicationContext)
        else !enforced || DeviceEntitlement.isActive(context.applicationContext, BuildConfig.VOID_GUARDIAN_PUBLIC_KEY)

    internal fun client(context: Context): GuardianClient? = runCatching {
        GuardianClient(context, BuildConfig.VOID_GUARDIAN_ORIGIN, BuildConfig.VOID_GUARDIAN_PUBLIC_KEY)
    }.getOrNull()

    /** Do not preserve or replay untrusted launch intents after activation. */
    fun redirectIfLocked(activity: Activity): Boolean {
        if (isAllowed(activity)) return false
        activity.startActivity(Intent(activity, if (v2Enforced) ClerkQaActivity::class.java else GuardianActivationActivity::class.java))
        activity.finish()
        return true
    }
}
