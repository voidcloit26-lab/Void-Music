package com.mochyy.mochymusic.guardian

import android.app.Activity
import android.content.Context
import android.content.Intent
import com.mochyy.mochymusic.BuildConfig

/**
 * Explicitly enabled in staging builds only until all entry points are audited.
 * An enforced build with missing/invalid configuration must remain locked.
 */
object GuardianGate {
    val enforced: Boolean get() = BuildConfig.VOID_GUARDIAN_ENFORCED

    fun isAllowed(context: Context): Boolean =
        !enforced || DeviceEntitlement.isActive(context.applicationContext, BuildConfig.VOID_GUARDIAN_PUBLIC_KEY)

    internal fun client(context: Context): GuardianClient? = runCatching {
        GuardianClient(context, BuildConfig.VOID_GUARDIAN_ORIGIN, BuildConfig.VOID_GUARDIAN_PUBLIC_KEY)
    }.getOrNull()

    /** Do not preserve or replay untrusted launch intents after activation. */
    fun redirectIfLocked(activity: Activity): Boolean {
        if (isAllowed(activity)) return false
        activity.startActivity(Intent(activity, GuardianActivationActivity::class.java))
        activity.finish()
        return true
    }
}
